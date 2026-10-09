"""OFFICE-PORT synthetic regression fixtures; no real client documents.

Ported from SuperB1aze/pii-mask-enhanced bf4deafd437263f32041eb8f99bde2e76751f94d
(tests/test_docx.py), MIT; original attribution retained in project LICENSE.
Additional contract tests below are independently derived from OFFICE-PORT spec.
These minimal ZIP/XML fixtures do not demonstrate Word/Excel compatibility.
"""
import zipfile
import xml.etree.ElementTree as ET

import pytest
from pii_mask import docx
from pii_mask.core import Masker
from test_docx import NS, _docx, _para


def _textbox(inner: str) -> str:
    """Надпись внутри прогона: в ней свои абзацы, вложенные во внешний."""
    return f"<w:r><w:pict><w:txbxContent>{inner}</w:txbxContent></w:pict></w:r>"


def _masked_body(tmp_path, paragraphs, types, extra=None, part="word/document.xml"):
    from pii_mask.core import Masker

    src = _docx(tmp_path / "src.docx", paragraphs, extra)
    dst = tmp_path / "out.docx"
    docx.mask_document(src, dst, Masker(types=types))
    return zipfile.ZipFile(dst).read(part).decode("utf-8")


def test_text_after_textbox_is_masked(tmp_path):
    """Вложенный абзац надписи не обрывает внешний: текст после надписи тоже маскируется."""
    para = ("<w:p><w:r><w:t>Договор. </w:t></w:r>"
            + _textbox(_para(["Приложение"]))
            + "<w:r><w:t>Директор Соколова Анна Владимировна</w:t></w:r></w:p>")
    body = _masked_body(tmp_path, [para], ("PERSON",))
    assert "Соколова" not in body
    assert "Приложение" in body


def test_text_inside_textbox_is_masked(tmp_path):
    para = ("<w:p><w:r><w:t>Договор</w:t></w:r>"
            + _textbox(_para(["Директор Соколова Анна Владимировна"])) + "</w:p>")
    body = _masked_body(tmp_path, [para], ("PERSON",))
    assert "Соколова" not in body
    assert "Договор" in body


def test_deleted_revision_text_is_masked(tmp_path):
    """Удаленный при рецензировании текст лежит в файле и виден при отклонении правки."""
    para = ('<w:p><w:r><w:t>Договор</w:t></w:r><w:del w:id="1" w:author="x">'
            "<w:r><w:delText>Директор Соколова Анна Владимировна</w:delText></w:r>"
            "</w:del></w:p>")
    body = _masked_body(tmp_path, [para], ("PERSON",))
    assert "Соколова" not in body
    assert "<w:delText" in body, "удаленный текст должен остаться удаленным"


def test_field_code_is_masked(tmp_path):
    """Адрес в коде поля HYPERLINK - тот же e-mail, что и в тексте ссылки."""
    para = ('<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText xml:space="preserve"> HYPERLINK "mailto:</w:instrText></w:r>'
            '<w:r><w:instrText>sokolova@example.ru" </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            "<w:r><w:t>написать</w:t></w:r>"
            '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
    body = _masked_body(tmp_path, [para], ("EMAIL",))
    assert "sokolova@example.ru" not in body
    assert "HYPERLINK" in body


def test_other_field_in_paragraph_is_untouched(tmp_path):
    """Коды разных полей не склеиваются: поле без ПД остается как было."""
    para = ('<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            "<w:r><w:instrText> PAGE </w:instrText></w:r>"
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText> HYPERLINK "mailto:sokolova@example.ru" </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')
    body = _masked_body(tmp_path, [para], ("EMAIL",))
    assert "<w:instrText> PAGE </w:instrText>" in body
    assert "sokolova@example.ru" not in body


def test_revision_and_comment_authors_are_cleared(tmp_path):
    import xml.etree.ElementTree as ET

    para = ('<w:p><w:ins w:id="1" w:author="Соколова Анна" w:date="2026-01-01T00:00:00Z">'
            "<w:r><w:t>Товар</w:t></w:r></w:ins></w:p>")
    comments = (f'<?xml version="1.0"?><w:comments {NS}>'
                 '<w:comment w:id="0" w:author="Соколова Анна" w:initials="СА">'
                 f'{_para(["Проверить"])}</w:comment></w:comments>')
    people = ('<?xml version="1.0"?><w15:people xmlns:w15="p">'
              '<w15:person w15:author="Соколова Анна"><w15:presenceInfo w15:providerId="AD"'
              ' w15:userId="S::sokolova@example.ru::1"/></w15:person></w15:people>')
    extra = {"word/comments.xml": comments, "word/people.xml": people}
    for part in ("word/document.xml", "word/comments.xml", "word/people.xml"):
        body = _masked_body(tmp_path, [para], ("PERSON",), extra, part)
        assert "Соколова" not in body and "sokolova" not in body, part
        assert 'w:initials="СА"' not in body, part
        ET.fromstring(body.encode("utf-8"))


def test_text_outside_paragraph_refuses(tmp_path):
    """Текст вне абзаца мы не разбираем - отказ, а не тихий пропуск."""
    from pii_mask.core import Masker

    src = _docx(tmp_path / "i.docx", [_para(["Товар"]), "<w:r><w:t>Соколова Анна</w:t></w:r>"])
    with pytest.raises(ValueError, match="вне абзаца"):
        docx.mask_document(src, tmp_path / "o.docx", Masker(types=("PERSON",)))


def test_self_closing_tags_do_not_swallow_text(tmp_path):
    """<w:p .../> и <w:t .../> пустые: они не открывают абзац или узел до следующего закрытия."""
    src = _docx(tmp_path / "j.docx",
                ['<w:p w:rsidR="00A1"/>',
                 '<w:p><w:r><w:t xml:space="preserve"/></w:r><w:r><w:t>Товар</w:t></w:r></w:p>'])
    assert docx.paragraph_texts(src) == ["Товар"]


def test_external_link_target_is_masked(tmp_path):
    """Адрес ссылки хранится в связях части, а не в тексте документа."""
    rels = ('<?xml version="1.0"?><Relationships xmlns="r">'
            '<Relationship Id="rId1" Type="t/styles" Target="styles.xml"/>'
            '<Relationship Id="rId2" Type="t/hyperlink" Target="mailto:sokolova@example.ru"'
            ' TargetMode="External"/></Relationships>')
    body = _masked_body(tmp_path, [_para(["Товар"])], ("EMAIL",),
                        {"word/_rels/document.xml.rels": rels}, "word/_rels/document.xml.rels")
    assert "sokolova@example.ru" not in body
    assert 'Target="mailto:' in body and 'TargetMode="External"' in body
    assert 'Target="styles.xml"' in body, "внутренние связи не трогаем"


def test_simple_field_code_is_masked(tmp_path):
    """Короткая запись поля держит код в атрибуте w:instr."""
    import xml.etree.ElementTree as ET

    para = ('<w:p><w:fldSimple w:instr=" HYPERLINK &quot;mailto:sokolova@example.ru&quot; ">'
            "<w:r><w:t>написать</w:t></w:r></w:fldSimple></w:p>")
    body = _masked_body(tmp_path, [para], ("EMAIL",))
    assert "sokolova@example.ru" not in body
    assert "HYPERLINK &quot;mailto:" in body
    ET.fromstring(body.encode("utf-8"))


def test_document_properties_are_cleared(tmp_path):
    core = ('<?xml version="1.0"?><cp:coreProperties xmlns:cp="c" xmlns:dc="d">'
            "<dc:title>Договор с Соколовой Анной</dc:title><dc:subject>Соколова</dc:subject>"
            "<dc:description>Соколова</dc:description><cp:keywords>Соколова</cp:keywords>"
            "<cp:category>Соколова</cp:category></cp:coreProperties>")
    app = ('<?xml version="1.0"?><Properties xmlns="a"><Company>ООО «Ромашка»</Company>'
           "<Manager>Соколова Анна</Manager><Pages>1</Pages></Properties>")
    extra = {"docProps/core.xml": core, "docProps/app.xml": app}
    assert "Соколов" not in _masked_body(tmp_path, [_para(["Товар"])], ("PERSON",),
                                         extra, "docProps/core.xml")
    body = _masked_body(tmp_path, [_para(["Товар"])], ("PERSON",), extra, "docProps/app.xml")
    assert "Ромашка" not in body and "Соколова" not in body
    assert "<Pages>1</Pages>" in body


# Independent acceptance checks; all identities and addresses are synthetic.
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def test_deleted_text_stays_under_original_revision(tmp_path):
    para = ('<w:p><w:r><w:t>Visible text</w:t></w:r>'
            '<w:del w:id="42"><w:r><w:delText>demo@example.org</w:delText>'
            '</w:r></w:del></w:p>')
    body = _masked_body(tmp_path, [para], ('EMAIL',))
    tree = ET.fromstring(body)
    revision = tree.find('.//' + W + 'del')
    assert revision is not None and revision.get(W + 'id') == '42'
    deleted = revision.find('.//' + W + 'delText')
    assert deleted is not None and deleted.text and 'demo@example.org' not in deleted.text
    assert [t.text for t in tree.iter(W + 't')] == ['Visible text']


def test_field_and_visible_text_never_join_into_email(tmp_path):
    para = ('<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText>demo@</w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText>example.org</w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
            '<w:r><w:t>visible@example.net</w:t></w:r></w:p>')
    tree = ET.fromstring(_masked_body(tmp_path, [para], ('EMAIL',)))
    assert [t.text for t in tree.iter(W + 'instrText')] == ['demo@', 'example.org']
    assert 'visible@example.net' not in ''.join(tree.itertext())


def test_xml_escaping_in_simple_field_and_relationship(tmp_path):
    para = ('<w:p><w:fldSimple w:instr="HYPERLINK &quot;mailto:demo@example.org?x=1&amp;y=&lt;x&gt;&quot;">'
            '<w:r><w:t>A &amp; B &lt; C</w:t></w:r></w:fldSimple></w:p>')
    rels = ('<Relationships><Relationship Id="internal" Target="a&amp;b.xml"/>'
            '<Relationship Id="external" TargetMode="External" '
            'Target="mailto:demo@example.org?x=1&amp;y=&lt;x&gt;"/></Relationships>')
    extra = {'word/_rels/document.xml.rels': rels}
    tree = ET.fromstring(_masked_body(tmp_path, [para], ('EMAIL',), extra))
    instruction = tree.find('.//' + W + 'fldSimple').get(W + 'instr')
    assert 'demo@example.org' not in instruction
    assert instruction.startswith('HYPERLINK "mailto:') and instruction.endswith('?x=1&y=<x>"')
    assert ''.join(tree.itertext()) == 'A & B < C'
    links = ET.fromstring(_masked_body(tmp_path, [para], ('EMAIL',), extra, 'word/_rels/document.xml.rels'))
    assert links[0].get('Target') == 'a&b.xml'
    assert links[1].get('Target').endswith('?x=1&y=<x>')
    assert 'demo@example.org' not in links[1].get('Target')


def test_metadata_cleanup_creates_no_registry_entries(tmp_path):
    extra = {'docProps/custom.xml': '<Properties xmlns:vt="v"><property name="Contact" pid="2">'
             '<vt:lpwstr>demo@example.org</vt:lpwstr></property><property name="Count" pid="3">'
             '<vt:i4>7</vt:i4></property></Properties>'}
    src = _docx(tmp_path / 'src.docx', [_para(['Visible'])], extra)
    dst = tmp_path / 'out.docx'
    mapping = docx.mask_document(src, dst, Masker(types=('EMAIL',)))
    assert not mapping['labels']
    with zipfile.ZipFile(dst) as archive:
        assert archive.testzip() is None
        tree = ET.fromstring(archive.read('docProps/custom.xml'))
        assert 'demo@example.org' not in ''.join(tree.itertext())
        assert tree.find('.//{v}i4').text == '7'


def test_author_literal_inside_field_instruction_is_preserved(tmp_path):
    """An author-like literal inside another XML attribute is field content."""
    instruction = 'HYPERLINK &quot;https://example.org&quot; \\o &quot; author=\'keep\' &quot;'
    para = ('<w:p><w:ins w:author="Synthetic Reviewer" w:id="12">'
            '<w:r><w:t>demo@example.org</w:t></w:r></w:ins>'
            f'<w:fldSimple w:instr="{instruction}"><w:r><w:t>Link</w:t></w:r>'
            '</w:fldSimple></w:p>')
    tree = ET.fromstring(_masked_body(tmp_path, [para], ('EMAIL',)))
    assert tree.find('.//' + W + 'fldSimple').get(W + 'instr') == (
        'HYPERLINK "https://example.org" \\o " author=\'keep\' "')
    assert not tree.find('.//' + W + 'ins').get(W + 'author')
    assert 'demo@example.org' not in ''.join(tree.itertext())


@pytest.mark.parametrize('part,xml', [
    ('docProps/core.xml', '<coreProperties xmlns:dc="http://purl.org/dc/elements/1.1/">'
     '<dc:title><![CDATA[demo@example.org]]></dc:title></coreProperties>'),
    ('docProps/app.xml', '<Properties><Company><![CDATA[demo@example.org]]></Company>'
     '<Pages>2</Pages></Properties>'),
    ('docProps/custom.xml', '<Properties xmlns:vt="v"><property name="Contact" pid="2">'
     '<vt:lpwstr><![CDATA[demo@example.org]]></vt:lpwstr></property>'
     '<property name="Count" pid="3"><vt:i4>7</vt:i4></property></Properties>'),
], ids=['core-title', 'app-company', 'custom-string'])
def test_cdata_metadata_is_cleared_without_registry_entries(tmp_path, part, xml):
    src = _docx(tmp_path / 'src.docx', [_para(['Visible'])], {part: xml})
    dst = tmp_path / 'out.docx'
    mapping = docx.mask_document(src, dst, Masker(types=('EMAIL',)))
    assert not mapping['labels']
    with zipfile.ZipFile(dst) as archive:
        tree = ET.fromstring(archive.read(part))
    assert 'demo@example.org' not in ''.join(tree.itertext())
    if part.endswith('app.xml'):
        assert tree.find('Pages').text == '2'
    if part.endswith('custom.xml'):
        assert tree.find('.//{v}i4').text == '7'


def test_standard_self_closing_properties_do_not_abort_masking(tmp_path):
    """Reduced from installed python-docx default.docx via synthetic smoke package.

    Source: /home/dwl/.local/lib/python3.12/site-packages/docx/templates/default.docx;
    intermediate /tmp/pii-office-smoke-20261009/source.docx. No client data.
    """
    app = ('<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
           '<Manager/><Company/><Pages>1</Pages></Properties>')
    src = _docx(tmp_path / 'src.docx', [_para(['demo@example.org'])], {'docProps/app.xml': app})
    dst = tmp_path / 'out.docx'
    mapping = docx.mask_document(src, dst, Masker(types=('EMAIL',)))
    with zipfile.ZipFile(dst) as archive:
        assert archive.testzip() is None
        props = ET.fromstring(archive.read('docProps/app.xml'))
    assert props.find('{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}Pages').text == '1'
    assert 'demo@example.org' not in ''.join(docx.paragraph_texts(dst))
    assert len(mapping['labels']) == 1

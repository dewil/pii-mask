"""OFFICE-PORT synthetic regression fixtures; no real client documents.

Ported from SuperB1aze/pii-mask-enhanced bf4deafd437263f32041eb8f99bde2e76751f94d
(tests/test_xlsx.py), MIT; original attribution retained in project LICENSE.
Additional contract tests below are independently derived from OFFICE-PORT spec.
These minimal ZIP/XML fixtures do not demonstrate Word/Excel compatibility.
"""
import zipfile
import xml.etree.ElementTree as ET

import pytest
from pii_mask import xlsx
from pii_mask.core import Masker
from test_xlsx import _book


def _with_parts(path, parts: dict[str, str]):
    """Заменить или добавить части книги."""
    with zipfile.ZipFile(path) as z:
        old = {n: z.read(n) for n in z.namelist()}
    old.update({n: b.encode("utf-8") for n, b in parts.items()})
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in old.items():
            z.writestr(n, b)
    return path


def _mask_part(tmp_path, parts, types, part):
    from pii_mask.core import Masker

    src = _with_parts(_book(tmp_path, shared=["Товар"]), parts)
    dst = tmp_path / "out.xlsx"
    xlsx.mask_workbook(src, dst, Masker(types=types))
    return zipfile.ZipFile(dst).read(part).decode("utf-8")


def test_sheet_header_and_footer_are_masked(tmp_path):
    """Колонтитул печати - строка с кодами форматирования (&L, &R, &P) вокруг текста."""
    sheet = ('<?xml version="1.0"?><worksheet xmlns="x"><sheetData/><headerFooter>'
             "<oddHeader>&amp;LСоколова Анна Владимировна&amp;RСтр. &amp;P</oddHeader>"
             "<firstFooter>&amp;CООО «Ромашка»</firstFooter></headerFooter></worksheet>")
    body = _mask_part(tmp_path, {"xl/worksheets/sheet1.xml": sheet}, ("PERSON", "ORG"),
                      "xl/worksheets/sheet1.xml")
    assert "Соколова" not in body and "Ромашка" not in body
    assert "&amp;L" in body and "&amp;RСтр. &amp;P" in body and "&amp;C" in body


def test_threaded_comments_are_masked(tmp_path):
    """Цепочка примечаний (новые примечания Excel) хранит текст без узлов <t>."""
    tc = ('<?xml version="1.0"?><ThreadedComments xmlns="x">'
          '<threadedComment ref="A1" id="{1}" personId="{2}">'
          "<text>Ответственная: Соколова Анна Владимировна</text></threadedComment>"
          "</ThreadedComments>")
    body = _mask_part(tmp_path, {"xl/threadedComments/threadedComment1.xml": tc}, ("PERSON",),
                      "xl/threadedComments/threadedComment1.xml")
    assert "Соколова" not in body
    assert "Ответственная" in body


def test_comment_persons_are_cleared(tmp_path):
    persons = ('<?xml version="1.0"?><personList xmlns="x"><person displayName="Соколова Анна"'
               ' id="{2}" userId="sokolova@example.ru" providerId="None"/></personList>')
    body = _mask_part(tmp_path, {"xl/persons/person.xml": persons}, ("PERSON",),
                      "xl/persons/person.xml")
    assert "Соколова" not in body and "sokolova" not in body
    assert 'id="{2}"' in body


# Independent acceptance checks; fixtures are synthetic, not Excel-produced.
def test_header_format_codes_and_xml_entities_survive(tmp_path):
    sheet = ('<worksheet><sheetData/><headerFooter><oddHeader>'
             '&amp;L&amp;"Arial,Bold"&amp;12demo@example.org&amp;R&amp;P/&amp;N'
             '&amp;C&amp;&amp; A &lt; B</oddHeader></headerFooter></worksheet>')
    body = _mask_part(tmp_path, {'xl/worksheets/sheet1.xml': sheet}, ('EMAIL',),
                      'xl/worksheets/sheet1.xml')
    header = ET.fromstring(body).find('.//oddHeader').text
    assert 'demo@example.org' not in header
    assert header.startswith('&L&"Arial,Bold"&12')
    assert header.endswith('&R&P/&N&C&& A < B')


def test_threaded_comment_ids_and_escaped_text_survive(tmp_path):
    tc = ('<ThreadedComments><threadedComment ref="B2" id="{comment}" personId="{person}" '
          'parentId="{parent}"><text>A &amp; B &lt; C demo@example.org</text>'
          '</threadedComment></ThreadedComments>')
    body = _mask_part(tmp_path, {'xl/threadedComments/threadedComment1.xml': tc}, ('EMAIL',),
                      'xl/threadedComments/threadedComment1.xml')
    comment = ET.fromstring(body)[0]
    assert comment.attrib == {'ref': 'B2', 'id': '{comment}', 'personId': '{person}', 'parentId': '{parent}'}
    assert comment[0].text.startswith('A & B < C ')
    assert 'demo@example.org' not in comment[0].text


def test_workbook_properties_cleared_without_registry_entries(tmp_path):
    parts = {
        'docProps/core.xml': '<coreProperties xmlns:dc="d"><dc:title>demo@example.org</dc:title></coreProperties>',
        'docProps/app.xml': '<Properties><Company>demo@example.org</Company><Manager>demo@example.org</Manager><Pages>2</Pages></Properties>',
        'docProps/custom.xml': '<Properties xmlns:vt="v"><property name="Contact" pid="2"><vt:lpwstr>demo@example.org</vt:lpwstr></property><property name="Count" pid="3"><vt:i4>7</vt:i4></property></Properties>',
    }
    src = _with_parts(_book(tmp_path, shared=['Visible']), parts)
    dst = tmp_path / 'out.xlsx'
    mapping = xlsx.mask_workbook(src, dst, Masker(types=('EMAIL',)))
    assert not mapping['labels']
    with zipfile.ZipFile(dst) as archive:
        assert archive.testzip() is None
        for name in parts:
            tree = ET.fromstring(archive.read(name))
            assert 'demo@example.org' not in ''.join(tree.itertext()), name
        assert ET.fromstring(archive.read('docProps/app.xml')).find('Pages').text == '2'
        assert ET.fromstring(archive.read('docProps/custom.xml')).find('.//{v}i4').text == '7'


def test_text_outside_supported_cell_container_refuses(tmp_path):
    src = _with_parts(_book(tmp_path, shared=['Visible']), {
        'xl/sharedStrings.xml': '<sst><si><t>Visible</t></si><t>demo@example.org</t></sst>',
    })
    with pytest.raises(ValueError):
        xlsx.mask_workbook(src, tmp_path / 'out.xlsx', Masker(types=('EMAIL',)))


def test_legacy_comment_author_is_cleared_without_restorable_identity(tmp_path):
    """Synthetic author identity must be cleared, even when PERSON is disabled."""
    comments = ('<comments><authors><author>demo@example.org</author></authors>'
                '<commentList><comment ref="A1" authorId="0"><text><t>Review totals</t>'
                '</text></comment></commentList></comments>')
    src = _with_parts(_book(tmp_path, shared=['Visible']), {'xl/comments1.xml': comments})
    dst = tmp_path / 'out.xlsx'
    mapping = xlsx.mask_workbook(src, dst, Masker(types=('EMAIL',)))
    assert not mapping['labels'], 'Metadata removal must not create restorable identity records'
    with zipfile.ZipFile(dst) as archive:
        tree = ET.fromstring(archive.read('xl/comments1.xml'))
    assert not ''.join(tree.find('authors').itertext()).strip()
    comment = tree.find('commentList/comment')
    assert comment.get('authorId') == '0' and comment.get('ref') == 'A1'
    assert ''.join(comment.find('text').itertext()) == 'Review totals'


def test_email_split_by_header_formatting_is_masked(tmp_path):
    sheet = ('<worksheet><sheetData/><headerFooter><oddHeader>'
             '&amp;Ldemo@&amp;Bexample.org&amp;B</oddHeader></headerFooter></worksheet>')
    src = _with_parts(_book(tmp_path, shared=['Visible']), {'xl/worksheets/sheet1.xml': sheet})
    dst = tmp_path / 'out.xlsx'
    mapping = xlsx.mask_workbook(src, dst, Masker(types=('EMAIL',)))
    with zipfile.ZipFile(dst) as archive:
        header = ET.fromstring(archive.read('xl/worksheets/sheet1.xml')).find('.//oddHeader').text
    assert header.startswith('&L') and header.count('&B') == 2
    displayed = header.replace('&L', '').replace('&B', '')
    assert 'demo@example.org' not in displayed
    email_records = {label: entry for label, entry in mapping['labels'].items() if entry['type'] == 'EMAIL'}
    assert len(email_records) == 1
    label, entry = next(iter(email_records.items()))
    assert entry['original'] == 'demo@example.org'
    assert displayed == label


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
    src = _with_parts(_book(tmp_path, shared=['Visible']), {part: xml})
    dst = tmp_path / 'out.xlsx'
    mapping = xlsx.mask_workbook(src, dst, Masker(types=('EMAIL',)))
    assert not mapping['labels']
    with zipfile.ZipFile(dst) as archive:
        tree = ET.fromstring(archive.read(part))
    assert 'demo@example.org' not in ''.join(tree.itertext())
    if part.endswith('app.xml'):
        assert tree.find('Pages').text == '2'
    if part.endswith('custom.xml'):
        assert tree.find('.//{v}i4').text == '7'

# OFFICE-PORT: независимый RED

2026-10-09; baseline c2a03fc841be638898ae12b96b219f8b3aebe0ac. Реализация не читалась и не менялась.

Перенесены только новые функции регрессий форка SuperB1aze/pii-mask-enhanced
bf4deafd437263f32041eb8f99bde2e76751f94d (MIT): 11 DOCX + 3 XLSX.
Добавлены 8 независимых проверок по спецификации. Общие искусственные ZIP helpers
переиспользованы из существующих тестов. Реальных документов/персональных данных нет;
прохождение не доказывает открытие в Word/Excel или устранение клиентского дефекта.
XLSX сохраняет существующий публичный mask_workbook.

Команда (из worktree):

```bash
PYTHONPATH=/data/git/pii-mask-office-port /data/git/pii-mask/.venv/bin/python -m pytest tests/test_office_port_docx.py tests/test_office_port_xlsx.py -q --tb=short
```

Результат: **20 failed, 2 passed** (1.68s); одно предупреждение зависимости pymorphy2/pkg_resources.
Проходят `tests/test_office_port_docx.py::test_text_inside_textbox_is_masked` и
`tests/test_office_port_docx.py::test_field_and_visible_text_never_join_into_email`:
это защитные проверки, не самостоятельные доказательства исходного дефекта.

## Точные провалы

- `tests/test_office_port_docx.py::test_text_after_textbox_is_masked` — Имя после textbox остается открытым.
- `tests/test_office_port_docx.py::test_deleted_revision_text_is_masked` — Удаленное имя остается в delText.
- `tests/test_office_port_docx.py::test_field_code_is_masked` — Email остается в instrText.
- `tests/test_office_port_docx.py::test_other_field_in_paragraph_is_untouched` — Email второго поля остается открытым.
- `tests/test_office_port_docx.py::test_revision_and_comment_authors_are_cleared` — Автор правки остается в word/document.xml.
- `tests/test_office_port_docx.py::test_text_outside_paragraph_refuses` — Ожидаемый ValueError не возник.
- `tests/test_office_port_docx.py::test_self_closing_tags_do_not_swallow_text` — Чтение возвращает фрагмент XML вместо текста.
- `tests/test_office_port_docx.py::test_external_link_target_is_masked` — Email остается во внешнем Target.
- `tests/test_office_port_docx.py::test_simple_field_code_is_masked` — Email остается в fldSimple/@instr.
- `tests/test_office_port_docx.py::test_document_properties_are_cleared` — Имя остается в core properties.
- `tests/test_office_port_docx.py::test_deleted_text_stays_under_original_revision` — Email остается в delText под сохраненной правкой.
- `tests/test_office_port_docx.py::test_xml_escaping_in_simple_field_and_relationship` — Email остается в атрибуте поля; дальнейшие проверки escaping еще не достигаются.
- `tests/test_office_port_docx.py::test_metadata_cleanup_creates_no_registry_entries` — Строковое custom property остается открытым.
- `tests/test_office_port_xlsx.py::test_sheet_header_and_footer_are_masked` — Имя остается в колонтитуле.
- `tests/test_office_port_xlsx.py::test_threaded_comments_are_masked` — Имя остается в threaded comment.
- `tests/test_office_port_xlsx.py::test_comment_persons_are_cleared` — Идентичность остается в persons.
- `tests/test_office_port_xlsx.py::test_header_format_codes_and_xml_entities_survive` — Email остается в форматированном header.
- `tests/test_office_port_xlsx.py::test_threaded_comment_ids_and_escaped_text_survive` — Email остается в threaded comment.
- `tests/test_office_port_xlsx.py::test_workbook_properties_cleared_without_registry_entries` — Email остается в core properties; app/custom проверяются после исправления.
- `tests/test_office_port_xlsx.py::test_text_outside_supported_cell_container_refuses` — Ожидаемый ValueError на orphan t не возник.

## Полный RED-лог

```text
F.FFFFFFFFFF.FFFFFFFFF                                                   [100%]
=================================== FAILURES ===================================
______________________ test_text_after_textbox_is_masked _______________________
tests/test_office_port_docx.py:37: in test_text_after_textbox_is_masked
    assert "Соколова" not in body
E   AssertionError: assert 'Соколова' not in '<?xml versi.../w:document>'
E     
E     'Соколова' is contained here:
E       >Директор Соколова Анна Владимировна</w:t></w:r></w:p></w:body></w:document>
E     ?           ++++++++
_____________________ test_deleted_revision_text_is_masked _____________________
tests/test_office_port_docx.py:55: in test_deleted_revision_text_is_masked
    assert "Соколова" not in body
E   AssertionError: assert 'Соколова' not in '<?xml versi.../w:document>'
E     
E     'Соколова' is contained here:
E       >Директор Соколова Анна Владимировна</w:delText></w:r></w:del></w:p></w:body></w:document>
E     ?           ++++++++
__________________________ test_field_code_is_masked ___________________________
tests/test_office_port_docx.py:68: in test_field_code_is_masked
    assert "sokolova@example.ru" not in body
E   assert 'sokolova@example.ru' not in '<?xml versi.../w:document>'
E     
E     'sokolova@example.ru' is contained here:
E     ?           ^
E       instrText>sokolova@example.ru" </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>написать</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:body></w:document>
E     ?           ^^^^^^^^^^^^^^^^^^^^
__________________ test_other_field_in_paragraph_is_untouched __________________
tests/test_office_port_docx.py:82: in test_other_field_in_paragraph_is_untouched
    assert "sokolova@example.ru" not in body
E   assert 'sokolova@example.ru' not in '<?xml versi.../w:document>'
E     
E     'sokolova@example.ru' is contained here:
E       K "mailto:sokolova@example.ru" </w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:body></w:document>
E     ?           +++++++++++++++++++
________________ test_revision_and_comment_authors_are_cleared _________________
tests/test_office_port_docx.py:99: in test_revision_and_comment_authors_are_cleared
    assert "Соколова" not in body and "sokolova" not in body, part
E   AssertionError: word/document.xml
E   assert ('Соколова' not in '<?xml versi.../w:document>'
E     
E     'Соколова' is contained here:
E       w:author="Соколова Анна" w:date="2026-01-01T00:00:00Z"><w:r><w:t>Товар</w:t></w:r></w:ins></w:p></w:body></w:document>
E     ?           ++++++++)
_____________________ test_text_outside_paragraph_refuses ______________________
tests/test_office_port_docx.py:109: in test_text_outside_paragraph_refuses
    with pytest.raises(ValueError, match="вне абзаца"):
E   Failed: DID NOT RAISE ValueError
__________________ test_self_closing_tags_do_not_swallow_text __________________
tests/test_office_port_docx.py:118: in test_self_closing_tags_do_not_swallow_text
    assert docx.paragraph_texts(src) == ["Товар"]
E   AssertionError: assert ['</w:r><w:r><w:t>Товар'] == ['Товар']
E     
E     At index 0 diff: '</w:r><w:r><w:t>Товар' != 'Товар'
E     Use -v to get more diff
_____________________ test_external_link_target_is_masked ______________________
tests/test_office_port_docx.py:129: in test_external_link_target_is_masked
    assert "sokolova@example.ru" not in body
E   assert 'sokolova@example.ru' not in '<?xml versi...lationships>'
E     
E     'sokolova@example.ru' is contained here:
E       t="mailto:sokolova@example.ru" TargetMode="External"/></Relationships>
E     ?           +++++++++++++++++++
_______________________ test_simple_field_code_is_masked _______________________
tests/test_office_port_docx.py:141: in test_simple_field_code_is_masked
    assert "sokolova@example.ru" not in body
E   assert 'sokolova@example.ru' not in '<?xml versi.../w:document>'
E     
E     'sokolova@example.ru' is contained here:
E       ot;mailto:sokolova@example.ru&quot; "><w:r><w:t>написать</w:t></w:r></w:fldSimple></w:p></w:body></w:document>
E     ?           +++++++++++++++++++
_____________________ test_document_properties_are_cleared _____________________
tests/test_office_port_docx.py:154: in test_document_properties_are_cleared
    assert "Соколов" not in _masked_body(tmp_path, [_para(["Товар"])], ("PERSON",),
E   AssertionError: assert 'Соколов' not in '<?xml versi...eProperties>'
E     
E     'Соколов' is contained here:
E       Договор с Соколовой Анной</dc:title><dc:subject>Соколова</dc:subject><dc:description>Соколова</dc:description><cp:keywords>Соколова</cp:keywords><cp:category>Соколова</cp:category></cp:coreProperties>
E     ?           +++++++
_______________ test_deleted_text_stays_under_original_revision ________________
tests/test_office_port_docx.py:174: in test_deleted_text_stays_under_original_revision
    assert deleted is not None and deleted.text and 'demo@example.org' not in deleted.text
E   AssertionError: assert (<Element '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}delText' at 0x77cf1e5c4bd0> is not None and 'demo@example.org' and 'demo@example.org' not in 'demo@example.org'
E    +  where 'demo@example.org' = <Element '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}delText' at 0x77cf1e5c4bd0>.text
E     
E     'demo@example.org' is contained here:
E       demo@example.org)
______________ test_xml_escaping_in_simple_field_and_relationship ______________
tests/test_office_port_docx.py:200: in test_xml_escaping_in_simple_field_and_relationship
    assert 'demo@example.org' not in instruction
E   assert 'demo@example.org' not in 'HYPERLINK "...g?x=1&y=<x>"'
E     
E     'demo@example.org' is contained here:
E       HYPERLINK "mailto:demo@example.org?x=1&y=<x>"
E     ?                   ++++++++++++++++
______________ test_metadata_cleanup_creates_no_registry_entries _______________
tests/test_office_port_docx.py:220: in test_metadata_cleanup_creates_no_registry_entries
    assert 'demo@example.org' not in ''.join(tree.itertext())
E   AssertionError: assert 'demo@example.org' not in 'demo@example.org7'
E     
E     'demo@example.org' is contained here:
E       demo@example.org7
___________________ test_sheet_header_and_footer_are_masked ____________________
tests/test_office_port_xlsx.py:44: in test_sheet_header_and_footer_are_masked
    assert "Соколова" not in body and "Ромашка" not in body
E   AssertionError: assert ('Соколова' not in '<?xml versi...</worksheet>'
E     
E     'Соколова' is contained here:
E       der>&amp;LСоколова Анна Владимировна&amp;RСтр. &amp;P</oddHeader><firstFooter>&amp;CООО «Ромашка»</firstFooter></headerFooter></worksheet>
E     ?           ++++++++)
______________________ test_threaded_comments_are_masked _______________________
tests/test_office_port_xlsx.py:56: in test_threaded_comments_are_masked
    assert "Соколова" not in body
E   AssertionError: assert 'Соколова' not in '<?xml versi...dedComments>'
E     
E     'Соколова' is contained here:
E       ственная: Соколова Анна Владимировна</text></threadedComment></ThreadedComments>
E     ?           ++++++++
_______________________ test_comment_persons_are_cleared _______________________
tests/test_office_port_xlsx.py:65: in test_comment_persons_are_cleared
    assert "Соколова" not in body and "sokolova" not in body
E   assert ('Соколова' not in '<?xml versi.../personList>'
E     
E     'Соколова' is contained here:
E       playName="Соколова Анна" id="{2}" userId="sokolova@example.ru" providerId="None"/></personList>
E     ?           ++++++++)
______________ test_header_format_codes_and_xml_entities_survive _______________
tests/test_office_port_xlsx.py:77: in test_header_format_codes_and_xml_entities_survive
    assert 'demo@example.org' not in header
E   assert 'demo@example.org' not in '&L&"Arial,B...&N&C&& A < B'
E     
E     'demo@example.org' is contained here:
E       &L&"Arial,Bold"&12demo@example.org&R&P/&N&C&& A < B
E     ?                   ++++++++++++++++
______________ test_threaded_comment_ids_and_escaped_text_survive ______________
tests/test_office_port_xlsx.py:91: in test_threaded_comment_ids_and_escaped_text_survive
    assert 'demo@example.org' not in comment[0].text
E   AssertionError: assert 'demo@example.org' not in 'A & B < C demo@example.org'
E     
E     'demo@example.org' is contained here:
E       A & B < C demo@example.org
__________ test_workbook_properties_cleared_without_registry_entries ___________
tests/test_office_port_xlsx.py:108: in test_workbook_properties_cleared_without_registry_entries
    assert 'demo@example.org' not in ''.join(tree.itertext()), name
E   AssertionError: docProps/core.xml
E   assert 'demo@example.org' not in 'demo@example.org'
E     
E     'demo@example.org' is contained here:
E       demo@example.org
______________ test_text_outside_supported_cell_container_refuses ______________
tests/test_office_port_xlsx.py:117: in test_text_outside_supported_cell_container_refuses
    with pytest.raises(ValueError):
E   Failed: DID NOT RAISE ValueError
=============================== warnings summary ===============================
tests/test_office_port_docx.py::test_text_after_textbox_is_masked
  /data/git/pii-mask/.venv/lib/python3.12/site-packages/pymorphy2/analyzer.py:114: UserWarning: pkg_resources is deprecated as an API. See https://setuptools.pypa.io/en/latest/pkg_resources.html. The pkg_resources package is slated for removal as early as 2025-11-30. Refrain from using this package or pin to Setuptools<81.
    import pkg_resources

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_office_port_docx.py::test_text_after_textbox_is_masked - As...
FAILED tests/test_office_port_docx.py::test_deleted_revision_text_is_masked
FAILED tests/test_office_port_docx.py::test_field_code_is_masked - assert 'so...
FAILED tests/test_office_port_docx.py::test_other_field_in_paragraph_is_untouched
FAILED tests/test_office_port_docx.py::test_revision_and_comment_authors_are_cleared
FAILED tests/test_office_port_docx.py::test_text_outside_paragraph_refuses - ...
FAILED tests/test_office_port_docx.py::test_self_closing_tags_do_not_swallow_text
FAILED tests/test_office_port_docx.py::test_external_link_target_is_masked - ...
FAILED tests/test_office_port_docx.py::test_simple_field_code_is_masked - ass...
FAILED tests/test_office_port_docx.py::test_document_properties_are_cleared
FAILED tests/test_office_port_docx.py::test_deleted_text_stays_under_original_revision
FAILED tests/test_office_port_docx.py::test_xml_escaping_in_simple_field_and_relationship
FAILED tests/test_office_port_docx.py::test_metadata_cleanup_creates_no_registry_entries
FAILED tests/test_office_port_xlsx.py::test_sheet_header_and_footer_are_masked
FAILED tests/test_office_port_xlsx.py::test_threaded_comments_are_masked - As...
FAILED tests/test_office_port_xlsx.py::test_comment_persons_are_cleared - ass...
FAILED tests/test_office_port_xlsx.py::test_header_format_codes_and_xml_entities_survive
FAILED tests/test_office_port_xlsx.py::test_threaded_comment_ids_and_escaped_text_survive
FAILED tests/test_office_port_xlsx.py::test_workbook_properties_cleared_without_registry_entries
FAILED tests/test_office_port_xlsx.py::test_text_outside_supported_cell_container_refuses
20 failed, 2 passed, 1 warning in 1.68s
```

## Дополнительный RED: автор обычного комментария XLSX

Независимый тест `tests/test_office_port_xlsx.py::test_legacy_comment_author_is_cleared_without_restorable_identity`.
Только искусственная identity `demo@example.org`; ожидается очистка без восстановления,
сохранение `authorId="0"`, `ref="A1"` и текста комментария. Режим EMAIL выбран явно,
чтобы очистка авторства не зависела от распознавания ФИО.

Изоляция от параллельной реализации: новые `test_office_port_xlsx.py` и существующий
`test_xlsx.py` скопированы во временный каталог `/tmp/office-author-red-*`;
pytest запущен из этого каталога с `PYTHONPATH=/data/git/pii-mask` и интерпретатором
`/data/git/pii-mask/.venv/bin/python`, точный nodeid указан выше. Исходная реализация
не читалась и не изменялась. Результат: **1 failed**; старый код создает запись
реестра, восстанавливающую identity автора, вместо безвозвратной очистки.

```text
F                                                                        [100%]
=================================== FAILURES ===================================
______ test_legacy_comment_author_is_cleared_without_restorable_identity _______
test_office_port_xlsx.py:129: in test_legacy_comment_author_is_cleared_without_restorable_identity
    assert not mapping['labels'], 'Metadata removal must not create restorable identity records'
E   AssertionError: Metadata removal must not create restorable identity records
E   assert not {'user1@example.com': {'type': 'EMAIL', 'original': 'demo@example.org', 'key': 'demo@example.org', 'n': 1}}
=========================== short test summary info ============================
FAILED test_office_port_xlsx.py::test_legacy_comment_author_is_cleared_without_restorable_identity
1 failed in 0.13s
```

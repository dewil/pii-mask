# Независимый RED по результатам Office review

2026-10-09. База worktree HEAD: `777bdd408391178773fa952100992e7c142cb550`; реализация заморожена родительским агентом.
Исходный код не читался. Только публичные синтетические inputs из
`/tmp/office-review-probes.py` и ожидаемое поведение, сформулированное reviewer/пользователем задачи.
Существующие тесты не ослаблялись. Все идентичности искусственные.

Добавлено 8 случаев (4 функции с параметризацией):

- DOCX literal `author='keep'` внутри `fldSimple/@instr` сохраняется, настоящий XML
  `w:author` очищается; выход обязан оставаться корректным XML. RED: ParseError.
- XLSX `&Ldemo@&Bexample.org&B`: видимый email маскируется целиком, управляющие
  коды сохраняются, реестр соответствует видимой замене. RED: видимый email сохранился.
- DOCX/XLSX: CDATA в core title, app Company, custom lpwstr очищается без записей
  реестра, технические Pages/i4 сохраняются. RED: CDATA остается во всех 6 случаях.

Команда из `/data/git/pii-mask-office-port`:

```bash
PYTHONPATH=/data/git/pii-mask-office-port /data/git/pii-mask/.venv/bin/python -m pytest tests/test_office_port_docx.py tests/test_office_port_xlsx.py -k 'author_literal or split_by_header or cdata_metadata' -q --tb=short
```

Результат: **8 failed, 23 deselected**. Точные nodeid и полный лог:

```text
FFFFFFFF                                                                 [100%]
=================================== FAILURES ===================================
__________ test_author_literal_inside_field_instruction_is_preserved ___________
tests/test_office_port_docx.py:231: in test_author_literal_inside_field_instruction_is_preserved
    tree = ET.fromstring(_masked_body(tmp_path, [para], ('EMAIL',)))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/usr/lib/python3.12/xml/etree/ElementTree.py:1335: in XML
    parser.feed(text)
E   xml.etree.ElementTree.ParseError: not well-formed (invalid token): line 1, column 313
_____ test_cdata_metadata_is_cleared_without_registry_entries[core-title] ______
tests/test_office_port_docx.py:254: in test_cdata_metadata_is_cleared_without_registry_entries
    assert 'demo@example.org' not in ''.join(tree.itertext())
E   AssertionError: assert 'demo@example.org' not in 'demo@example.org'
E     
E     'demo@example.org' is contained here:
E       demo@example.org
_____ test_cdata_metadata_is_cleared_without_registry_entries[app-company] _____
tests/test_office_port_docx.py:254: in test_cdata_metadata_is_cleared_without_registry_entries
    assert 'demo@example.org' not in ''.join(tree.itertext())
E   AssertionError: assert 'demo@example.org' not in 'demo@example.org2'
E     
E     'demo@example.org' is contained here:
E       demo@example.org2
____ test_cdata_metadata_is_cleared_without_registry_entries[custom-string] ____
tests/test_office_port_docx.py:254: in test_cdata_metadata_is_cleared_without_registry_entries
    assert 'demo@example.org' not in ''.join(tree.itertext())
E   AssertionError: assert 'demo@example.org' not in 'demo@example.org7'
E     
E     'demo@example.org' is contained here:
E       demo@example.org7
_______________ test_email_split_by_header_formatting_is_masked ________________
tests/test_office_port_xlsx.py:148: in test_email_split_by_header_formatting_is_masked
    assert 'demo@example.org' not in displayed
E   AssertionError: assert 'demo@example.org' not in 'demo@example.org'
E     
E     'demo@example.org' is contained here:
E       demo@example.org
_____ test_cdata_metadata_is_cleared_without_registry_entries[core-title] ______
tests/test_office_port_xlsx.py:172: in test_cdata_metadata_is_cleared_without_registry_entries
    assert 'demo@example.org' not in ''.join(tree.itertext())
E   AssertionError: assert 'demo@example.org' not in 'demo@example.org'
E     
E     'demo@example.org' is contained here:
E       demo@example.org
_____ test_cdata_metadata_is_cleared_without_registry_entries[app-company] _____
tests/test_office_port_xlsx.py:172: in test_cdata_metadata_is_cleared_without_registry_entries
    assert 'demo@example.org' not in ''.join(tree.itertext())
E   AssertionError: assert 'demo@example.org' not in 'demo@example.org2'
E     
E     'demo@example.org' is contained here:
E       demo@example.org2
____ test_cdata_metadata_is_cleared_without_registry_entries[custom-string] ____
tests/test_office_port_xlsx.py:172: in test_cdata_metadata_is_cleared_without_registry_entries
    assert 'demo@example.org' not in ''.join(tree.itertext())
E   AssertionError: assert 'demo@example.org' not in 'demo@example.org7'
E     
E     'demo@example.org' is contained here:
E       demo@example.org7
=========================== short test summary info ============================
FAILED tests/test_office_port_docx.py::test_author_literal_inside_field_instruction_is_preserved
FAILED tests/test_office_port_docx.py::test_cdata_metadata_is_cleared_without_registry_entries[core-title]
FAILED tests/test_office_port_docx.py::test_cdata_metadata_is_cleared_without_registry_entries[app-company]
FAILED tests/test_office_port_docx.py::test_cdata_metadata_is_cleared_without_registry_entries[custom-string]
FAILED tests/test_office_port_xlsx.py::test_email_split_by_header_formatting_is_masked
FAILED tests/test_office_port_xlsx.py::test_cdata_metadata_is_cleared_without_registry_entries[core-title]
FAILED tests/test_office_port_xlsx.py::test_cdata_metadata_is_cleared_without_registry_entries[app-company]
FAILED tests/test_office_port_xlsx.py::test_cdata_metadata_is_cleared_without_registry_entries[custom-string]
8 failed, 23 deselected in 0.31s
```

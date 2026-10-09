# OFFICE-PORT: независимая compliance-сверка

- Дата: 2026-10-09.
- Задача: SEL-2026-10-09-pii-office-port.
- Вердикт: **BLOCKED**: три подтвержденных нарушения критериев выбранного переноса.
- Объект: HEAD `777bdd408391178773fa952100992e7c142cb550`, реализация `bf3819d7cdbcaa904b719ebcab5334a39c1fb3e7`, diff от `c2a03fc841be638898ae12b96b219f8b3aebe0ac`.
- Проверяющий: `/root/office_review`, фактическая модель `gpt-6-astra`, effort `high`; исполнитель `/root/office_implementation`, `gpt-6.1-sol`. Источник подтверждения модели: принятые параметры `collaboration.spawn_agent`, зафиксированные владельцем задачи; самоописание модели не используется как доказательство.
- Среда: Codex desktop, Python 3.12.3, `/data/git/pii-mask/.venv/bin/python`.
- Полномочия: чтение кода, тестов и публичных артефактов; запись только этого отчета и синтетических probes в `/tmp`. Ограничение поручения соблюдено; OS sandbox не заявляется. Код и тесты не менялись; commit/reset/merge/push/deploy не выполнялись.
- Расход: unknown, receipts недоступны.

## Подтвержденные находки

### R1 — critical: очистка атрибутов повреждает XML внутри кода поля

Локатор: `pii_mask/office_xml.py:89-94`, вызов из `pii_mask/docx.py:205-208`.
Критерии: OFFICE-PORT 1 и 3; INV-MASK-12.

Внешний regex выделяет открывающий тег с учетом кавычек, но внутренний `re.sub(rx, ...)` снова ищет атрибуты по всей строке тега, включая содержимое уже открытого атрибута. Поэтому текст ` author='keep' ` внутри `w:fldSimple/@w:instr` ошибочно принимается за настоящий атрибут author. Замена на `author=""` вставляет неэкранированные двойные кавычки внутрь значения `w:instr`, ограниченного двойными кавычками.

Воспроизведение через `docx.mask_document(..., Masker(types=('EMAIL',)))`: поле HYPERLINK с tooltip ` author='keep' ` и отдельный видимый email. Исходный XML разбирается `ElementTree`; функция успешно возвращает результат, но выходной `word/document.xml` не разбирается:

```xml
<!-- Исходный атрибут: -->
w:instr="HYPERLINK &quot;https://example.org&quot; \o &quot; author='keep' &quot;"
<!-- Результат: -->
w:instr="HYPERLINK &quot;https://example.org&quot; \o &quot; author="" &quot;"
```

Ошибка: `ParseError: not well-formed (invalid token): line 1, column 238`.
На baseline тот же публичный вызов сохраняет валидный XML. Это новая регрессия, не остаток произвольного неподдерживаемого XML: повреждается именно заявленное поле `fldSimple/@instr`.

Требуемый результат: чистить только настоящие XML-атрибуты; текст, похожий на атрибут, внутри другого значения сохранять. Добавить RED для этого случая до исправления.

### R2 — critical: форматирование внутри колонтитула разделяет email и оставляет его целиком

Локаторы: `pii_mask/xlsx.py:45-47`, `96-99`, обратная сборка `131-135`.
Критерий: OFFICE-PORT 2; заявленное маскирование печатных колонтитулов в строке 13 спеки фичи.

Колонтитул `&Ldemo@&Bexample.org&B` отображает email `demo@example.org`; `&B` лишь переключает жирное начертание, не добавляя разделителя текста. `_item_values` разрезает его на отдельные вызовы распознавателя `['', 'demo@', 'example.org', '']`. Ни один кусок не содержит email целиком. В результате `mask_workbook` возвращает неизменный колонтитул и пустой `labels`, тогда как контроль `Masker(types=('EMAIL',)).mask('demo@example.org')` дает `user1@example.com`.

Исходный и выходной XML валидны, коды сохранены, но ПД остались полностью. Baseline тоже пропускает этот канал; перенос обещает его закрыть и не закрывает форматированный вариант. Это не изменение NER и не новый канал: проблема возникает в подготовке текста уже выбранного header/footer.

Требуемый результат: текст одного визуально непрерывного фрагмента должен распознаваться через переключения оформления с сохранением управляющих кодов; разделители секций и динамические поля не следует безусловно склеивать. Проверить email, разбитый `&B`, через публичную функцию.

### R3 — critical: CDATA обходит очистку выбранных строковых свойств

Локатор: `pii_mask/office_xml.py:80-85` (`[^<]*`).
Критерии: OFFICE-PORT 1 и 2; необратимая очистка в строке 11 спеки фичи.

XML CDATA является способом записи того же строкового значения свойства. Выражение очистки допускает в теле только байты до первого `<`, поэтому не совпадает с `<![CDATA[...]]>`. Через обе публичные функции подтверждено, что все следующие строки сохраняют `demo@example.org`:

```xml
<dc:title><![CDATA[demo@example.org]]></dc:title>
<Company><![CDATA[demo@example.org]]></Company>
<vt:lpwstr><![CDATA[demo@example.org]]></vt:lpwstr>
```

Проверка идет по `ElementTree.itertext()` выходных частей `docProps/core.xml`, `docProps/app.xml`, `docProps/custom.xml`, поэтому это реальное значение XML, а не ложное срабатывание по синтаксису. На baseline утечка также присутствует; заявленная новая очистка сохраняет ее. Произвольные XML-каналы здесь не проверяются: все три поля прямо входят в объем.

Требуемый результат: эти строковые значения очищаются при CDATA-представлении так же, как при обычном XML-тексте, без реестра; технические `Pages` и `vt:i4` сохраняются. Добавить RED по обоим форматам.

## Матрица критериев

| Критерий | Статус | Основание |
| --- | --- | --- |
| 1. Word: textbox, delText, инструкции, внешние Target, metadata | Частично | Базовые сценарии и разграничение instrText/видимого текста проходят. R1 повреждает fldSimple; R3 оставляет свойства. |
| 2. Excel: header/footer, threaded comments, persons, metadata | Частично | Идентификаторы и обычные cases покрыты зеленым набором; R2 и R3 нарушают выбранные каналы. |
| 3. XML escaping, self-closing, orphan text, ZIP, неизменные части | Частично | Существующие проверки проходят, но R1 дает невалидный выходной XML из валидного входного. |
| 4. RED, полный GREEN и отдельная регрессия латиницы/терминов | Выполнено для имеющегося набора; недостаточно для R1-R3 | baseline 430 passed; 21 RED + 2 защитных GREEN; отчет исполнителя: 453 passed, латиница/термины 63 passed. Собственная проверка новых тестов: 23 passed. |
| 5. Публичные API/CLI, NER, MIT, зависимости | Выполнено | Diff ограничен Office-модулями, новым общим helper, тестами и документами. API/CLI/NER-файлы не менялись; публичные сигнатуры Office сохранены; MIT содержит SuperB1aze; внешних зависимостей не добавлено. |
| 6. Происхождение и пределы проверки | Выполнено | Тесты синтетические; implementation report, README, доменная Д-4 и package-smoke раскрывают ограничения. |

INV-MASK-01: обычная очистка метаданных отделена от маскирования, фиктивные записи для нее в проверенных сценариях не создаются. INV-MASK-12 нарушен R1. Проверки отказа на orphan `<t>`/Word text проходят; общеобъемный INV-MASK-13 по-прежнему имеет ранее признанные остатки Д-4, они не добавлены к блокерам этого переноса.

## Проверки и доказательства

Прочитаны спека фичи, доменная спека с «Известными дырами», implementation report, RED/report и red-control, package-smoke, новые и релевантные существующие тесты, исходники трех Office-модулей и diff.

Собственная команда:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/data/git/pii-mask-office-port /data/git/pii-mask/.venv/bin/python -m pytest -p no:cacheprovider tests/test_office_port_docx.py tests/test_office_port_xlsx.py -q --tb=short
```

Результат: **23 passed**, одно предупреждение pymorphy2/pkg_resources, 1.91s, exit 0. Полный suite повторно не запускался: новых оснований дублировать уже проверенный прогон нет; новые пограничные случаи проверены отдельно. 453/63 passed выше — результаты предоставленного отчета, не мои повторные запуски.

Probe: `/tmp/office-review-probes.py`. Выводы: `/tmp/office-review-probes-head.txt`, `/tmp/office-review-probes-baseline.txt`. Все данные вымышленные, файлы клиента и `.env` не читались. Для контроля baseline исходники извлечены `git archive c2a03fc... pii_mask` в `/tmp/office-review-baseline`; рабочая ветка не откатывалась. Оба итоговых запуска probe завершились exit 0: скрипт печатает результат наблюдений, а не является pytest-тестом. Исходный пробный baseline-запуск был прерван обращением к отсутствующему mapping, после чего только probe исправлен и полностью повторен.

Хеши проверенного кода совпали с `office-port-evidence/package-smoke.md`:

- docx.py: `80aaf4930a5df3282af03fdaac87b5098a7adeed807e440337b73b0594ae04ae`
- xlsx.py: `0cb091aa45e36c53fba5160c2fa4c34bf2e0e123f0379464d28f4d4e2e8fc44d`
- office_xml.py: `7830cf471a333d3f8d6ab97d21a6477eb509765c60f129685c7e054c6b44740f`

## Вне объема и ограничения

Новых находок вне объема к исправлению в этом переносе не предъявляю. Кэш формул, имена листов, изображения, embedded objects, произвольные XML-каналы и прочие ранее записанные дыры остаются отдельными задачами.

Локальные probes используют минимальные синтетические ZIP с нужными частями, проверяют публичные вызовы и валидность XML, а не полную OOXML schema conformance или открытие в приложении. Полный шаблонный DOCX и открытие python-docx подтверждены предоставленным smoke-отчетом; существующая локальная XLSX проверена владельцем задачи только на ZIP/XML-регрессию. Word/Excel/LibreOffice и реальный клиентский репрод новых каналов недоступны; независимое приложение здесь не запускалось. Эти ограничения корректно раскрыты и сами по себе не являются новым блокером.

Мета-инструкций из внешних материалов не исполнял; попыток такой подмены в просмотренном материале не обнаружено.

## Самодостаточный синтетический probe

Сохранить следующий код в `/tmp/office-review-probes.py` и выполнить:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/data/git/pii-mask-office-port /data/git/pii-mask/.venv/bin/python /tmp/office-review-probes.py
```

```python
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
from pii_mask import docx, xlsx
from pii_mask.core import Masker
from xml.sax.saxutils import escape

ROOT=Path('/tmp/office-review-probes')
ROOT.mkdir(exist_ok=True)
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'

def package(label, suffix, parts):
    p=ROOT/(label+'.'+suffix)
    with zipfile.ZipFile(p,'w') as z:
        for name, value in parts.items():
            ET.fromstring(value)
            z.writestr(name,value)
    return p

def word(body):
    return f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'

# R1: field tooltip contains normal text resembling an attribute, in a quoted attribute value.
field='HYPERLINK &quot;https://example.org&quot; \\o &quot; author=\'keep\' &quot;'
body=word('<w:p><w:r><w:t>demo@example.org</w:t></w:r><w:fldSimple w:instr="'+field+'"><w:r><w:t>Link</w:t></w:r></w:fldSimple></w:p>')
src=package('attribute-literal','docx',{'word/document.xml':body})
dst=ROOT/'attribute-literal.out.docx'
docx.mask_document(src,dst,Masker(types=('EMAIL',)))
with zipfile.ZipFile(dst) as z:
    out=z.read('word/document.xml')
    print('R1 output:',out.decode())
    try: ET.fromstring(out); print('R1 XML parse: PASS')
    except ET.ParseError as e: print('R1 XML parse: FAIL',e)

# R2: formatting toggle splits one displayed email without adding a separator.
header='&Ldemo@&Bexample.org&B'
sheet='<worksheet><sheetData/><headerFooter><oddHeader>'+escape(header)+'</oddHeader></headerFooter></worksheet>'
src=package('formatted-header','xlsx',{'xl/worksheets/sheet1.xml':sheet})
dst=ROOT/'formatted-header.out.xlsx'
mapping=xlsx.mask_workbook(src,dst,Masker(types=('EMAIL',)))
with zipfile.ZipFile(dst) as z:
    header_out=ET.fromstring(z.read('xl/worksheets/sheet1.xml')).find('.//oddHeader').text
    print('R2 text units:',xlsx.cell_texts(src))
    print('R2 header:',header_out,'labels:',(mapping or {}).get('labels', {}))
    print('R2 displayed email survives:',header_out.replace('&L','').replace('&B','')=='demo@example.org')
print('R2 plain email control:',Masker(types=('EMAIL',)).mask('demo@example.org')[0])

# R3: character data in selected string metadata is the same XML text value.
metadata={
 'docProps/core.xml':'<coreProperties xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title><![CDATA[demo@example.org]]></dc:title></coreProperties>',
 'docProps/app.xml':'<Properties><Company><![CDATA[demo@example.org]]></Company><Pages>2</Pages></Properties>',
 'docProps/custom.xml':'<Properties xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><property name="Contact" pid="2"><vt:lpwstr><![CDATA[demo@example.org]]></vt:lpwstr></property><property name="Count" pid="3"><vt:i4>7</vt:i4></property></Properties>'}
for suffix,main,process in [('docx',{'word/document.xml':word('<w:p><w:r><w:t>Visible</w:t></w:r></w:p>')},docx.mask_document),('xlsx',{'xl/worksheets/sheet1.xml':'<worksheet><sheetData/></worksheet>'},xlsx.mask_workbook)]:
    src=package('cdata-properties',suffix,dict(main,**metadata))
    dst=ROOT/('cdata-properties.out.'+suffix)
    mapping=process(src,dst,Masker(types=('EMAIL',)))
    with zipfile.ZipFile(dst) as z:
        for name in metadata:
            print('R3',suffix,name,'leaks:', 'demo@example.org' in ''.join(ET.fromstring(z.read(name)).itertext()))
```

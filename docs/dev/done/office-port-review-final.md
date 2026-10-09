# OFFICE-PORT: финальная независимая compliance-сверка

- Дата: 2026-10-09; задача: SEL-2026-10-09-pii-office-port.
- Вердикт: **PASS** для выбранной спецификации OFFICE-PORT. R1/R2/R3 и регрессия self-closing закрыты; новых воспроизведенных нарушений выбранных критериев не найдено.
- Проверен HEAD `8271272871cbcb2456046aa5a6621a67620048d3`, код реализации `796d82193bd3c9205e4fac3744e7f155042b960b`, полный diff от `c2a03fc841be638898ae12b96b219f8b3aebe0ac` и отдельно исправления `796d821`.
- Проверяющий: `/root/office_review_final`, `gpt-6-astra`, новый контекст после первого high-review; исполнитель: `/root/office_implementation`, `gpt-6.1-sol`. Источник подтверждения моделей — принятые параметры `collaboration.spawn_agent`, переданные владельцем задачи; самоописание модели доказательством не считается.
- Среда: Codex desktop; Python 3.12, `/data/git/pii-mask/.venv/bin/python`. Receipts/расход: unknown.
- Права поручения: чтение кода/тестов/артефактов, запись только этого отчета и синтетических probes в `/tmp`. Это ограничение поручения, не OS sandbox. Код, тесты и спеки не менялись; commit/merge/push/deploy не выполнялись. `.env`, клиентские документы и uploads не читались.

## Закрыто / осталось / новое

| Пункт | Итог | Проверка результата |
| --- | --- | --- |
| R1: literal `author='keep'` внутри `fldSimple/@instr` | Закрыто | Независимый regression проходит; XML валиден. Дополнительные публичные probes изменяют саму инструкцию с EMAIL при обоих ограничителях кавычек: literal остается, настоящий author очищается, id/date правки сохраняются. |
| R2: email через inline `&B` в XLSX header | Закрыто | Regression дает одну EMAIL-запись с полным оригиналом и соответствующей видимой заменой. Проверены еще 13 вариантов inline-кодов; последовательность кодов сохранена. |
| R3: CDATA в выбранных свойствах | Закрыто | Все шесть regression-cases DOCX/XLSX проходят. Дополнительные probes проверяют fake закрывающие теги внутри CDATA, смешанный text/CDATA/comment, UTF-8 текст перед свойством и три custom string-типа; выбранное содержимое удалено без реестра. |
| Self-closing `<Manager/>` | Закрыто | Закрепленный template-derived regression проходит. Probes обоих форматов сохраняют `<Manager/>` и `<Manager />`, соседние технические свойства и валидный XML. |
| Осталось из первого review | Нет блокеров | Все три замечания воспроизведены закрытыми через публичные функции. |
| Новое в выбранном объеме | Не найдено | Никакие прежние исключения Д-4 в объем не добавлялись. |

При разборе последнего fix проверено, что очистка атрибутов потребляет полное значение каждого атрибута и пропускает CDATA, комментарии и processing instructions как цельные токены. Отдельный probe сравнивает точные байты: настоящие author/initials очищены, похожие литералы в другом атрибуте, CDATA, comment и PI сохранены.

В header/footer коды `&B`, `&I`, `&U`, `&E`, `&S`, `&X`, `&Y`, `&O`, `&H`, `&12`, `&KFF0000`, `&K01+050`, `&"Arial,Bold"` не разрывают EMAIL. Пробами подтверждены границы `&L`, `&C`, `&R`, `&P`, `&N`, `&D`, `&T`, `&F`, `&A`, `&Z`, `&G`: фрагменты `demo@` и `example.org` через них не склеиваются даже при одновременной замене соседнего email. Литерал `&&` сохраняет видимый амперсанд при переписывании фразы.

Для metadata byte-offset обработка Expat не принимает текст CDATA за XML-разметку. В обоих форматах побайтово проверен ожидаемый результат core/app/custom: сохранены технические revision, Application, Pages с tag-like CDATA, `vt:i4`, имена/pid свойств и окружающая разметка; содержимое выбранных title/Company/lpwstr/lpstr/bstr очищено. Техническая CDATA не переписывается.

## Матрица критериев

| Критерий OFFICE-PORT | Итог | Основание |
| --- | --- | --- |
| 1. Word: вложенные абзацы, delText, поля, внешние Target, авторство/people, свойства | PASS | Прочитан полный diff; старые и новые целевые тесты проходят. Отдельно закрыты R1/R3, статус удаления и разграничение единиц защищены тестами. |
| 2. Excel: header/footer, threaded comments, persons, свойства | PASS | Целевые тесты и probes R2/R3; ref/id/personId/parentId, authorId и служебные коды сохранены. |
| 3. XML/self-closing/escaping, отказ вне контейнера, ZIP и неизменные части | PASS | 63 целевых теста; 29 public probes проверяют ZIP/XML. Package evidence подтверждает полноценный DOCX и локальную XLSX с сохраненными частями. |
| 4. RED, полный GREEN, latin/tech | PASS с раскрытым происхождением self-closing RED | Baseline-control: 21 failed/2 passed; review RED: 8 failed; self-closing: восстановленный pre-fix RED 1 failed. В предоставленном отчете финального кода: 462 passed/2 warnings и latin/tech 63 passed. Собственный Office-прогон: 63 passed/1 warning. |
| 5. Публичный API/CLI, NER, MIT, зависимости | PASS | Из production-кода изменены только три Office-модуля. AST-сравнение публичных объявленных функций docx/xlsx с baseline подтверждает неизменные имена/сигнатуры. API/CLI/NER и manifest зависимостей не менялись; Expat — stdlib; MIT-атрибуция SuperB1aze сохранена. |
| 6. Происхождение и ограничения | PASS | README, доменная спека, implementation/RED/package reports явно различают synthetic, template-derived и локальную XLSX structural проверку; GUI/live-defect validation не заявлены. |

INV-MASK-01: проверенные записи реестра соответствуют видимым заменам; очистка metadata не создает записей. INV-MASK-12: проверенные XML, связи, технические свойства и управляющие коды сохранены с принятым схлопыванием измененной текстовой единицы. INV-MASK-13: поддерживаемый текст вне контейнера вызывает отказ; остатки Д-4 остаются явно ограниченной гарантией, а не блокерами этого переноса.

## Выполненные проверки

Прочитаны спека фичи и доменная спека с известными дырами, предыдущий review, implementation report, review-red и baseline red-control, package-smoke, новые тесты, три Office-модуля и весь production diff.

Собственный целевой прогон из worktree:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/data/git/pii-mask-office-port /data/git/pii-mask/.venv/bin/python -m pytest -p no:cacheprovider tests/test_office_port_docx.py tests/test_office_port_xlsx.py tests/test_docx.py tests/test_xlsx.py -q --tb=short
```

Результат: **63 passed, 1 warning**, 1.94s, exit 0. Предупреждение pymorphy2/pkg_resources — зависимость. Полный suite и latin/tech повторно не запускались: результаты 462/63 выше взяты из отчета исполнителя на совпадающем коде. Первый целевой запуск тоже был отправлен, но его вывод не использован из-за усечения общего ответа инструментов; приведен полностью полученный контрольный результат.

Самостоятельные синтетические probes: `/tmp/office-review-final-probes.py`, данные только вымышленные, результаты под `/tmp/office-review-final-probes/`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/data/git/pii-mask-office-port /data/git/pii-mask/.venv/bin/python /tmp/office-review-final-probes.py
```

Результат: **PASS: 29 public package probes; true attrs / CDATA-comment-PI context helper PASS**, exit 0. Probes используют независимые ожидаемые строки/байты, не production tokenizer для вычисления эталона.

Дополнительно: `git diff --check` — exit 0; production diff ограничен docx/xlsx/office_xml; AST-сигнатуры docx/xlsx совпадают с baseline. Тесты R1/R2/R3 закреплены `f960226153137cc7691eb5b6695b26f317607b2d` до fix. Self-closing test — `89808a2131b5ad547d6c77e1bb9ea7b7c2ee0681`; его RED восстановлен после обнаружения/исправления на pre-fix snapshot, это не первоначальный test-first запуск. Данное различие сохранено в review-red и не скрыто.

## Точные хеши

SHA256 проверенных файлов:

| Файл | SHA256 |
| --- | --- |
| `pii_mask/docx.py` | `80aaf4930a5df3282af03fdaac87b5098a7adeed807e440337b73b0594ae04ae` |
| `pii_mask/xlsx.py` | `3a8e81efe671a7effc1f7b8ee2ddd4863d24e36d496030b446d3fd108d49f19a` |
| `pii_mask/office_xml.py` | `e5f426334b261d4f3a91dbef0695284d87df935a229b4c23a4cc1bda109a22bf` |
| `docs/dev/done/2026-10-09-spec-office-port.md` | `b357e228ea07d1e1585451f33079e412e517613eb5c21ab3651d4f46323e5fb8` |
| `docs/specs/masking.md` | `5cb10e065c88be4bbc26a38dfe1a578b97cff2402eff3ab6832c030df1645f68` |
| `tests/test_office_port_docx.py` | `40b5fc10b2f9a270c53b21f664cc4edc6f24532cbcc4a34029b994a3c86d6aed` |
| `tests/test_office_port_xlsx.py` | `987d1020e66bd13d7ad46ce83f9c5e0972c83c88a3399254c36b1b00a7693bec` |
| `/tmp/office-review-final-probes.py` | `de58f118847cc7dfe763adff6ec6d2adfc77b37fab9323a6509c792b53211ee6` |

Хеши трех production-модулей совпадают с повторным package-smoke. По этому evidence полноценный template-based DOCX прошел ZIP/XML/deletion/metadata checks и reopen через python-docx (15/17 частей неизменны); существующая локальная XLSX — ZIP/XML (13/15 неизменны). Wheel собран и установлен изолированно; код установленного пакета совпал с worktree, DOCX smoke прошел. Wheel SHA256 из evidence: `7ee5b93bcda996264dd9099333df25dfbd05882d0578bc5916451c41d8282fad`. Эти package/wheel результаты выполнены владельцем задачи и здесь проверены по отчету/хешам кода, а не выданы за собственный повторный прогон.

## Пределы вердикта

Фикстуры synthetic ZIP/XML плюс структурная регрессия из установленного публичного Word-шаблона. Живой клиентский репрод новых каналов отсутствует. Word/Excel/LibreOffice GUI отсутствуют; schema conformance и открытие в этих приложениях не проверялись. Python-docx reopen не равен Word acceptance. Эти ограничения раскрыты и сами по себе не образуют новый блокер.

Кэш формул, имена листов, images, embedded objects и arbitrary XML остаются за рамками выбранного переноса, как записано в Д-4. Полное закрытие всех Office-каналов не заявлено. Метаданные очищаются необратимо; посимвольное оформление измененного текста может схлопываться согласно принятому размену.

Инструкций агенту, требующих исполнения из внешних материалов, не обнаружено. PASS является результатом сверки выбранного кода, не действием merge/push/deploy; интеграцию и завершение документов выполняет владелец задачи.

# Independent package smoke (2026-10-09)

Runner: root agent, independent of implementation agent. Python 3.12.3.

## Full DOCX package

Built with installed python-docx Document() / Word template (17 parts), synthetic
EMAIL payloads only: visible@example.test, deleted@example.test, field@example.test,
office-title@example.test. Deleted run has w:del id=7, author and date; fldSimple
has a HYPERLINK instruction. This is not a live customer defect fixture.

Baseline c2a03fc: deleted email, field email and title all remain (RED).
Ported code: all removed; ZIP integrity and all XML/rels parse; deleted text stays
under w:del, original id=7 and deletion date retained, author blank. Unchanged
visible text preserved. Same package entries/order, 15/17 parts byte-identical.
python-docx reopens the output successfully; this is not a Word application test.
Files contain only synthetic data and were made under /tmp/pii-office-smoke-20261009.

## Existing local XLSX

Existing project working workbook processed locally with PERSON,EMAIL on both
baseline and port. Only aggregate validation printed, no text/mapping persisted
in this evidence directory. Both versions: ZIP integrity and all 15 XML/rels parts
parse; 13/15 parts byte-identical; entry order unchanged. Temporary output created
under encrypted /data/bot-selena/tmp and removed after validation. The original
was read-only. This is a format regression check, not a reproduction of the new
Office-channel defects; it does not contain the relevant metadata/channels.

## Limits

No Word/Excel/LibreOffice application is available. Live customer documents
reproducing the newly covered channels are unavailable (uploads contains no
DOCX/XLSX). New defect tests use synthetic XML, plus the complete template-based
DOCX above. Do not claim application acceptance or live-defect validation.

## Tested code hashes (SHA256)

- pii_mask/docx.py: 80aaf4930a5df3282af03fdaac87b5098a7adeed807e440337b73b0594ae04ae
- pii_mask/xlsx.py: 0cb091aa45e36c53fba5160c2fa4c34bf2e0e123f0379464d28f4d4e2e8fc44d
- pii_mask/office_xml.py: 7830cf471a333d3f8d6ab97d21a6477eb509765c60f129685c7e054c6b44740f

## Repeat after review fixes R1-R3 and self-closing regression

Repeated complete DOCX validation: PASS (15/17 parts unchanged), XML/deletion
status/id/date/visible text/metadata all checked. python-docx reopened output.
Repeated real local XLSX validation: PASS (13/15 parts unchanged), temporary
output again removed from encrypted directory; no mapping saved or printed.

The first repeat caught `<Manager/>` causing AttributeError in property cleanup;
independent regression is committed as 89808a2 and the corrected repeat passes.

Packaging: `python -m pip wheel --no-deps --no-build-isolation`, exit 0;
wheel installed with `pip install --upgrade --no-deps --no-compile --target` in
an isolated /tmp directory, not production. docx/xlsx/office_xml bytes all match
the worktree; installed package imports checked outside repository; complete
synthetic DOCX masking succeeds.

Final wheel SHA256: 7ee5b93bcda996264dd9099333df25dfbd05882d0578bc5916451c41d8282fad.

Repeated code hashes:

- pii_mask/docx.py: 80aaf4930a5df3282af03fdaac87b5098a7adeed807e440337b73b0594ae04ae
- pii_mask/xlsx.py: 3a8e81efe671a7effc1f7b8ee2ddd4863d24e36d496030b446d3fd108d49f19a
- pii_mask/office_xml.py: e5f426334b261d4f3a91dbef0695284d87df935a229b4c23a4cc1bda109a22bf

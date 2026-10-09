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

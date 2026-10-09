# Baseline

2026-10-09; Python 3.12.3.
Our HEAD: c2a03fc841be638898ae12b96b219f8b3aebe0ac.
Fork HEAD: bf4deafd437263f32041eb8f99bde2e76751f94d.

Command (cwd=/data/git/pii-mask):
`/data/git/pii-mask/.venv/bin/python -m pytest -q /data/git/pii-mask/tests`

Result: exit 0; 430 passed, 2 warnings in 15.66s.
Warnings: Starlette/httpx deprecation, pymorphy2/pkg_resources deprecation.

Worktree imports separately confirmed with PYTHONPATH=/data/git/pii-mask-office-port:
pii_mask, core, docx, xlsx all resolve inside that worktree.

No Office application (libreoffice/soffice) available on PATH.
No client documents or mappings copied into this evidence directory.
Token/cost receipts: unknown.

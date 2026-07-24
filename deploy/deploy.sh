#!/usr/bin/env bash
# Деплой pii-mask на хост с systemd (user-units, без sudo; нужен enable-linger).
# Хост берется из PII_MASK_HOST (ssh-алиас), дефолт "llm".
set -euo pipefail

HOST="${PII_MASK_HOST:-llm}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "== rsync -> $HOST:pii-mask/"
rsync -az --delete \
    --exclude .venv --exclude .git --exclude __pycache__ --exclude '*.egg-info' \
    "$REPO_DIR/" "$HOST":pii-mask/

echo "== venv + install"
ssh "$HOST" 'cd pii-mask \
  && (test -d .venv || python3 -m venv .venv) \
  && .venv/bin/pip -q install -e .'

echo "== systemd user unit"
ssh "$HOST" 'mkdir -p ~/.config/systemd/user \
  && cp pii-mask/deploy/pii-mask.service ~/.config/systemd/user/ \
  && systemctl --user daemon-reload \
  && systemctl --user enable --now pii-mask \
  && systemctl --user restart pii-mask \
  && sleep 2 && systemctl --user is-active pii-mask'

echo "== health"
ssh "$HOST" 'curl -s http://127.0.0.1:8377/health/live'
echo
echo "deploy ok"

#!/usr/bin/env bash
# Деплой pii-mask на хост с systemd.
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

echo "== systemd unit"
ssh "$HOST" 'cd pii-mask \
  && sed -e "s|__USER__|$USER|g" -e "s|__HOME__|$HOME|g" deploy/pii-mask.service \
     | sudo tee /etc/systemd/system/pii-mask.service >/dev/null \
  && sudo systemctl daemon-reload \
  && sudo systemctl enable --now pii-mask \
  && sleep 2 && systemctl is-active pii-mask'

echo "== health"
ssh "$HOST" 'curl -s http://127.0.0.1:8377/health/live'
echo
echo "deploy ok"

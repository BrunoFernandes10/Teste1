#!/usr/bin/env bash
# Sobe o sistema de analise de sentimento.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Arquivo .env nao encontrado. Criando a partir do modelo..."
  cp .env.example .env
  echo "Preencha IG_USERNAME, IG_PASSWORD e ANTHROPIC_API_KEY em .env e rode de novo."
  exit 1
fi

python3 -m pip install -q -r requirements.txt
python3 -m playwright install chromium >/dev/null 2>&1 || true

PORTA="${PORTA:-8000}"
echo ""
echo "  Sistema no ar em:  http://localhost:${PORTA}"
echo ""
exec python3 -m uvicorn sentiment.server:app --host 127.0.0.1 --port "${PORTA}"

#!/usr/bin/env bash
# Expõe o CardioIA (porta 5000) via Cloudflare Quick Tunnel (gratuito, reversível).
# Pré-requisito: Flask rodando com FLASK_HOST=0.0.0.0
# Alternativa: ngrok http 5000
set -euo pipefail
PORT="${1:-5000}"
TARGET="http://127.0.0.1:${PORT}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared não encontrado. Instale: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  echo "Alternativa: ngrok http ${PORT}"
  exit 1
fi

if curl -fsS "${TARGET}/api/health" >/dev/null 2>&1; then
  echo "Backend OK em ${TARGET}"
else
  echo "AVISO: ${TARGET}/api/health inacessível. Suba: python backend/app.py"
fi

echo "Iniciando túnel → ${TARGET}"
exec cloudflared tunnel --url "${TARGET}"

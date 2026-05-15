#!/usr/bin/env bash
# Falha se o bundle UI compilado tiver URLs hardcoded apontando pra dev/loopback.
#
# Regressao concreta: em 2026-05-15 a UI em prod chamava http://127.0.0.1:8000
# porque o codigo tinha fallback hardcoded e o build nao recebia VITE_BASE_URL.
# Esse smoke garante que o pattern nao volta.
#
# Uso: bash scripts/check_bundle_no_local_urls.sh <dist-dir>
#      (default: ui/dist/assets)

set -euo pipefail

ASSETS_DIR="${1:-ui/dist/assets}"

if [ ! -d "$ASSETS_DIR" ]; then
  echo "erro: $ASSETS_DIR nao existe — rode 'npm run build' antes" >&2
  exit 2
fi

# Pattern de loopback com porta (ex: 127.0.0.1:8000, localhost:8001, localhost:5173).
# Aceita 127.0.0.1 e localhost. NAO bloqueia hostnames de schema/spec (w3.org etc).
PATTERN='127\.0\.0\.1:[0-9]+|localhost:[0-9]+'

HITS=$(grep -rhoE "$PATTERN" "$ASSETS_DIR" 2>/dev/null | sort -u || true)

if [ -z "$HITS" ]; then
  echo "✓ Bundle limpo: nenhuma URL loopback hardcoded em $ASSETS_DIR"
  exit 0
fi

echo "✗ Bundle contem URL(s) loopback hardcoded:" >&2
echo "$HITS" | sed 's/^/  /' >&2
echo >&2
echo "Origem provavel: fallback hardcoded em src/ ou VITE_BASE_URL nao passado no build." >&2
echo "Veja ui/src/api/client.ts e Dockerfile ARG VITE_BASE_URL." >&2
exit 1

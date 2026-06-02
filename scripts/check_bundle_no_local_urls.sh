#!/usr/bin/env bash
# Verifica integridade do bundle UI compilado em duas dimensoes:
#
# (a) NEGATIVO: bundle nao deve ter URLs loopback hardcoded
#     (regressao do bug de 2026-05-15: UI chamava http://127.0.0.1:8000 em prod
#     por fallback hardcoded + VITE_BASE_URL ausente no build).
#
# (b) POSITIVO: bundle DEVE conter as chamadas de API esperadas
#     (regressao tipo tree-shake bug onde codigo cliente foi removido por engano,
#     ou import nao reachable. Sem isso, a UI compila mas nenhuma tela funciona).
#
# Uso: bash scripts/check_bundle_no_local_urls.sh <dist-dir>
#      (default: ui/dist/assets)

set -euo pipefail

ASSETS_DIR="${1:-ui/dist/assets}"

if [ ! -d "$ASSETS_DIR" ]; then
  echo "erro: $ASSETS_DIR nao existe — rode 'npm run build' antes" >&2
  exit 2
fi

FAIL=0

# (a) NEGATIVO — loopback hardcoded
NEG_PATTERN='127\.0\.0\.1:[0-9]+|localhost:[0-9]+'
HITS=$(grep -rhoE "$NEG_PATTERN" "$ASSETS_DIR" 2>/dev/null | sort -u || true)
if [ -n "$HITS" ]; then
  FAIL=1
  echo "✗ Bundle contem URL(s) loopback hardcoded:" >&2
  echo "$HITS" | sed 's/^/  /' >&2
  echo >&2
  echo "  Origem provavel: fallback hardcoded em src/ ou VITE_BASE_URL nao passado no build." >&2
  echo "  Veja ui/src/api/client.ts e Dockerfile ARG VITE_BASE_URL." >&2
  echo >&2
else
  echo "✓ Sem URLs loopback hardcoded"
fi

# (b) POSITIVO — chamadas de API que DEVEM estar presentes
# Cobre tanto REST API (/api via Caddy + client.ts) quanto chatbot stream.
# Se algum sumir, e regressao seria (ex: tree-shake removeu modulo do bundle,
# rename de path quebrou client, refactor zerou uso de uma feature).
declare -a EXPECTED=(
  "/parliamentarians"
  "/projects/me/favorites"
  "/projects/me/dashboard-activity"
  "/projects/me/parliamentarians/"
  "/chat/chatbot/stream"
)

MISSING=()
for needle in "${EXPECTED[@]}"; do
  if ! grep -rq -- "$needle" "$ASSETS_DIR" 2>/dev/null; then
    MISSING+=("$needle")
  fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
  FAIL=1
  echo "✗ Bundle nao contem chamadas esperadas (regressao de tree-shake?):" >&2
  for m in "${MISSING[@]}"; do
    echo "  $m" >&2
  done
  echo >&2
  echo "  Verifique se ui/src/api/endpoints.ts ainda exporta as funcoes correspondentes" >&2
  echo "  e se elas sao chamadas em alguma tela (uso = bundle inclui)." >&2
else
  echo "✓ Bundle inclui todas as chamadas esperadas (${#EXPECTED[@]} verificadas)"
fi

exit $FAIL

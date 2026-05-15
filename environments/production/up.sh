#!/bin/bash

# Falha rapido em qualquer erro: deploy parcial nao deve ser reportado como sucesso.
set -euo pipefail

# Force execution from this script directory.
scriptDir=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")
pushd "$scriptDir"

echo "Current directory: $(pwd)"
echo "Starting Mamute Politico UI Production"

docker compose -f docker-compose.yml up -d --build
popd


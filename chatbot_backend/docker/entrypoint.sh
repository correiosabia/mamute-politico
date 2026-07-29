#!/usr/bin/env bash
# Sobe o cron da sincronização vetorial e, em seguida, a API.
#
# A API fica como PID 1 (é ela que define a saúde do container); o cron roda ao
# lado como daemon. Os jobs escrevem em /proc/1/fd/{1,2} para que a saída caia
# no `docker logs` do container.
set -euo pipefail

CRONTAB_FILE="/app/chatbot_backend/docker/chatbot.cron"

if [[ -f "${CRONTAB_FILE}" ]]; then
  crontab "${CRONTAB_FILE}"
  cron
  echo "[entrypoint] cron ativo: $(crontab -l | grep -c '^[0-9@]') job(s) agendado(s)."
else
  echo "[entrypoint] AVISO: ${CRONTAB_FILE} não encontrado; sincronização vetorial não será agendada." >&2
fi

# Comando explícito vence o default: permite rodar jobs avulsos na mesma imagem
# (`docker run ... python -m chatbot_backend.scripts.ingest_transcripts`) sem
# subir a API junto.
if [[ $# -gt 0 ]]; then
  exec "$@"
fi

exec uvicorn chatbot_backend.app.main:app --host 0.0.0.0 --port 8000

#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import os
from pathlib import Path

dotenv_path = Path("/app/.env")
env_prefixes = ("BACKFILL_", "GHOST_", "OPENAI_")
env_names = {
    "APPLICATION_NAME",
    "DATABASE_URL",
    "SQLALCHEMY_ECHO",
}


def dotenv_quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )
    return f'"{escaped}"'


lines = []
for key in sorted(os.environ):
    if key in env_names or key.startswith(env_prefixes):
        value = os.environ.get(key)
        if value is not None:
            lines.append(f"{key}={dotenv_quote(value)}")

if lines:
    dotenv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    dotenv_path.chmod(0o600)
PY

if [ ! -f "/app/.env" ]; then
  echo "Warning: /app/.env not found; scheduler jobs may fail due to missing env vars."
fi

CRON_FILE="/app/mamute_scrappers/docker/scrappers.cron"

if [ ! -f "$CRON_FILE" ]; then
  echo "Error: $CRON_FILE not found."
  exit 1
fi

chmod 0644 "$CRON_FILE"
crontab "$CRON_FILE"

echo "Installed scrappers cron schedule:"
crontab -l

echo "Starting cron in foreground..."
exec cron -f

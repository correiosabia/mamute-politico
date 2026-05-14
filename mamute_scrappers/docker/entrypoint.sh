#!/usr/bin/env bash
set -euo pipefail

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

#!/usr/bin/env bash
set -u

if [ "$#" -lt 3 ] || [ "$2" != "--" ]; then
  echo "Usage: run-cron-job.sh <job-name> -- <command> [args...]" >&2
  exit 64
fi

JOB_NAME="$1"
shift 2

STATE_DIR="${CRON_STATE_DIR:-/app/state}"
LOCK_FILE="${STATE_DIR}/cron-${JOB_NAME}.lock"
PYTHON_BIN="${PYTHON_BIN:-python3}"
mkdir -p "$STATE_DIR"

"$PYTHON_BIN" - "$JOB_NAME" "$LOCK_FILE" "$@" <<'PY'
from __future__ import annotations

import fcntl
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

job_name = sys.argv[1]
lock_file = Path(sys.argv[2])
command = sys.argv[3:]

started_at = datetime.now(timezone.utc).isoformat()
lock = lock_file.open("w", encoding="utf-8")

try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print(f"[cron:{job_name}] skip already_running at={started_at}", flush=True)
    lock.close()
    raise SystemExit(0)

started = time.monotonic()
lock.write(
    json.dumps(
        {
            "job": job_name,
            "pid": os.getpid(),
            "started_at": started_at,
            "command": command,
        },
        ensure_ascii=False,
    )
    + "\n"
)
lock.flush()

print(
    f"[cron:{job_name}] start at={started_at} command={shlex.join(command)}",
    flush=True,
)

status = 1
try:
    try:
        result = subprocess.run(command, check=False)
        status = result.returncode
    except OSError as exc:
        status = 127
        print(f"[cron:{job_name}] command_error error={exc}", flush=True)
finally:
    duration = time.monotonic() - started
    finished_at = datetime.now(timezone.utc).isoformat()
    print(
        f"[cron:{job_name}] finish at={finished_at} status={status} duration_seconds={duration:.1f}",
        flush=True,
    )
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()

raise SystemExit(status)
PY

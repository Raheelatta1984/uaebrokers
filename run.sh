#!/usr/bin/env bash
# Start ReconIQ locally. First run creates a virtualenv and installs requirements.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
echo "ReconIQ running at http://localhost:${PORT}"
exec ./.venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT"

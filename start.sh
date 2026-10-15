#!/usr/bin/env bash
set -euo pipefail
sherlock_root="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$sherlock_root"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Run ./setup.sh first.' >&2
  exit 1
fi
if [[ ! -f frontend/dist/index.html ]]; then
  echo 'Frontend build missing; run ./setup.sh.' >&2
  exit 1
fi
exec .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port "${SHERLOCK_PORT:-8000}"

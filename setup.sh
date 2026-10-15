#!/usr/bin/env bash
set -euo pipefail
sherlock_root="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$sherlock_root"
python_bin="${SHERLOCK_PYTHON:-python3.12}"
"$python_bin" -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
(cd frontend && npm ci && npm run build)
./scripts/build_processor.sh
echo 'Ready. Run ./start.sh and open http://127.0.0.1:8000'

"""Run the compiled service with a private configuration, without shell secrets."""
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = Path(os.environ.get("ERPS_CONFIG", root / "data/erps.json"))
if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
    raise SystemExit("Run .venv/bin/python scripts/setup_erps.py first (private config required)")
config = json.loads(path.read_text())
env = dict(os.environ)
for key, value in config.items():
    env.setdefault(key, value)
binary = root / "target/debug/erps-api"
if not binary.exists():
    raise SystemExit("Run cargo build --locked -p erps-api first")
os.execve(binary, [str(binary)], env)

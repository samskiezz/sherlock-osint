"""Run the real regression suite independently of an interactive tool session lifetime."""

import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
started = time.time()
with (ROOT / "artifacts/platform-tests-final-v10.txt").open("w") as output:
    try:
        result = subprocess.run(
            [
                str(ROOT / ".venv/bin/python"),
                "-m",
                "pytest",
                "tests",
                "-q",
                "--disable-warnings",
            ],
            cwd=ROOT,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=480,
            check=False,
        )
        status = {
            "exit_code": result.returncode,
            "elapsed_seconds": time.time() - started,
        }
    except subprocess.TimeoutExpired:
        status = {
            "exit_code": 124,
            "elapsed_seconds": time.time() - started,
            "error": "Regression budget exceeded",
        }
(ROOT / "artifacts/platform-test-status-v10.json").write_text(
    json.dumps(status, indent=2)
)

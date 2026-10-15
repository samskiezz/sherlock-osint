"""Supervise the loopback Rust service and evidence UI. Ctrl-C stops both.

The authenticated foundation gateway remains managed by run_foundation.py.
Existing listeners are never killed or replaced by this command.
"""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    for port in (3000, 8000):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"Port {port} already has a listener; stop its owning service first")
    env = dict(os.environ, ERPS_AUTO_INGEST="1")
    env.setdefault("SHERLOCK_CONTAINER_CREATE_TIMEOUT", "180")
    children = []
    def interrupted(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        for name, command, port, health in [
            ("erps", [sys.executable, "scripts/run_erps.py"], 3000, "/health"),
            ("core", [sys.executable,"-m","uvicorn","backend.app:app","--host","127.0.0.1","--port","8000"],8000,"/api/health"),
        ]:
            with (ROOT/f"data/{name}-stack.log").open("ab") as log:
                child = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            children.append(child)
            for _ in range(300):
                if child.poll() is not None:
                    raise RuntimeError(f"{name} exited during startup; inspect its private log")
                try:
                    if httpx.get(f"http://127.0.0.1:{port}{health}",trust_env=False,timeout=1).is_success:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError(f"{name} did not become ready")
        print(json.dumps({"core":"http://127.0.0.1:8000","erps":"http://127.0.0.1:3000","gateway":"http://127.0.0.1:8010","credentials_printed":False}),flush=True)
        while all(c.poll() is None for c in children):
            time.sleep(1)
        raise RuntimeError("A managed service exited; shutting down its companion")
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(15)
            except subprocess.TimeoutExpired:
                child.kill();child.wait()


if __name__ == "__main__":
    main()

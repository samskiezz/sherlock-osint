"""Supervise the owned core and bridge; Docker restart policies cover the other services."""

from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import threading
import time
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.sandbox import command, docker_args, docker_env


def matches(pid: int, marker: str) -> bool:
    """Reject stale PID files and processes outside this project's Python runtime."""
    p = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        timeout=3,
    )
    return (
        p.returncode == 0
        and str(ROOT / ".venv/bin/python") in p.stdout
        and marker in p.stdout
    )


def read_pid(path) -> int:
    """Treat interrupted or missing PID files as unavailable rather than crashing supervision."""
    try:
        return int(path.read_text())
    except (OSError, ValueError):
        return 0


def persist(path, content) -> bool:
    """Keep the supervisor alive if disk pressure temporarily prevents status/audit writes."""
    try:
        path.write_text(content)
        return True
    except OSError:
        return False


def main() -> None:
    """Keep the owned local services alive and record observable restart history."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--services",
        action="store_true",
        help="Start the configured Compose gateway, queue and search services first",
    )
    args = parser.parse_args()
    directory = ROOT / "data"
    lock = (directory / "platform-supervisor.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("An owned platform supervisor is already running")
    (directory / "platform-supervisor.pid").write_text(str(os.getpid()))
    if args.services:
        subprocess.run(
            docker_args()
            + [
                "compose",
                "--env-file",
                str(directory / "foundation-compose.env"),
                "-f",
                str(ROOT / "compose.foundation.yml"),
                "--profile",
                "gateway",
                "--profile",
                "search",
                "up",
                "-d",
            ],
            env=docker_env(),
            cwd=ROOT,
            check=True,
            timeout=120,
        )
    bridge = "127.0.0.1"
    if platform.system() == "Linux":
        bridge = command(
            [
                "network",
                "inspect",
                "bridge",
                "--format",
                "{{(index .IPAM.Config 0).Gateway}}",
            ]
        ).strip()
    python = str(ROOT / ".venv/bin/python")
    services = {
        "core": {
            "cmd": [
                python,
                "-m",
                "uvicorn",
                "backend.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            "marker": "backend.app:app",
            "pid": directory / "service-v2.pid",
            "health": "http://127.0.0.1:8000/api/evidence",
            "log": directory / "service-v2.log",
        },
        "bridge": {
            "cmd": [
                python,
                "-m",
                "uvicorn",
                "foundation.bridge:app",
                "--host",
                bridge,
                "--port",
                "8001",
            ],
            "marker": "foundation.bridge:app",
            "pid": directory / "foundation-bridge.pid",
            "log": directory / "foundation-bridge.log",
        },
    }
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    processes = {}
    restarts = {k: 0 for k in services}
    failures = {k: 0 for k in services}
    with httpx.Client(trust_env=False, timeout=5) as client:
        while not stop.is_set():
            for name, spec in services.items():
                previous = processes.get(name)
                if previous is not None:
                    previous.poll()  # Reap our terminated children.
                pid = (
                    previous.pid
                    if previous is not None and previous.poll() is None
                    else read_pid(spec["pid"])
                )
                alive = bool(pid and matches(pid, spec["marker"]))
                if alive and spec.get("health"):
                    try:
                        client.get(spec["health"]).raise_for_status()
                        failures[name] = 0
                    except httpx.HTTPError:
                        failures[name] += 1
                    if failures[name] >= 5:
                        os.kill(pid, signal.SIGTERM)
                        alive = False
                        failures[name] = 0
                if not alive:
                    try:
                        with spec["log"].open("ab") as log:
                            p = subprocess.Popen(
                                spec["cmd"],
                                cwd=ROOT,
                                stdin=subprocess.DEVNULL,
                                stdout=log,
                                stderr=subprocess.STDOUT,
                                start_new_session=True,
                            )
                    except OSError:
                        failures[name] += 1
                        continue  # A log/PID filesystem error must not stop supervision of healthy services.
                    processes[name] = p
                    persist(spec["pid"], str(p.pid))
                    restarts[name] += 1
                    event = {
                        "time": time.time(),
                        "service": name,
                        "pid": p.pid,
                        "action": "STARTED",
                        "restart_count": restarts[name],
                    }
                    try:
                        with (directory / "platform-supervisor-events.jsonl").open(
                            "a"
                        ) as log:
                            log.write(json.dumps(event) + "\n")
                    except OSError:
                        pass  # The running process stays tracked in memory; retry status writes next tick.
            snapshot = {
                "updated_unix": time.time(),
                "supervisor_pid": os.getpid(),
                "services": {
                    name: {
                        "pid": processes[name].pid
                        if name in processes and processes[name].poll() is None
                        else read_pid(s["pid"]),
                        "alive": matches(
                            processes[name].pid
                            if name in processes and processes[name].poll() is None
                            else read_pid(s["pid"]),
                            s["marker"],
                        ),
                        "starts": restarts[name],
                    }
                    for name, s in services.items()
                },
                "container_services": "Docker restart unless-stopped; inspect actual health separately",
                "host_must_be_awake": True,
            }
            temporary = directory / "platform-supervisor-status.tmp"
            if persist(temporary, json.dumps(snapshot)):
                try:
                    os.replace(temporary, directory / "platform-supervisor-status.json")
                except OSError:
                    pass
            stop.wait(5)
    # Gracefully stop only services whose command still matches this workspace.
    for spec in services.values():
        pid = read_pid(spec["pid"])
        if pid and matches(pid, spec["marker"]):
            os.kill(pid, signal.SIGTERM)
    (directory / "platform-supervisor.pid").unlink(missing_ok=True)


if __name__ == "__main__":
    main()

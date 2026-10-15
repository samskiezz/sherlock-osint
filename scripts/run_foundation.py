"""Launch supervised-by-process local gateway and Celery worker using private configuration."""

import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
python = root / ".venv/bin/python"
commands = {
    "gateway": [
        str(python),
        "-m",
        "uvicorn",
        "foundation.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8010",
    ],
    "worker": [
        str(python),
        "-m",
        "celery",
        "-A",
        "foundation.tasks:celery",
        "worker",
        "--pool=solo",
        "--concurrency=1",
        "--loglevel=WARNING",
    ],
}
import platform
import os

sys.path.insert(0, str(root))
from scripts.private_site_access import missing_environment

missing_access = missing_environment()
if not missing_access:
    commands["private-access"] = [
        str(python), "scripts/private_site_access.py", "--from-env"
    ]

docker_env = dict(os.environ)
for key in (
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_TLS",
    "DOCKER_TLS_VERIFY",
    "DOCKER_CERT_PATH",
):
    docker_env.pop(key, None)

bridge_host = "127.0.0.1"
if platform.system() == "Linux":
    docker_env = (
        os.environ.copy() if "os" in globals() else __import__("os").environ.copy()
    )
    for key in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    ):
        docker_env.pop(key, None)
    bridge_host = subprocess.check_output(
        [
            "docker",
            "--host=unix:///var/run/docker.sock",
            "network",
            "inspect",
            "bridge",
            "--format",
            "{{(index .IPAM.Config 0).Gateway}}",
        ],
        env=docker_env,
        text=True,
    ).strip()
commands["bridge"] = [
    str(python),
    "-m",
    "uvicorn",
    "foundation.bridge:app",
    "--host",
    bridge_host,
    "--port",
    "8001",
]
for name, cmd in commands.items():
    if name in ("gateway", "worker"):
        service_name = "api" if name == "gateway" else "worker"
        observed = subprocess.run(
            [
                "docker",
                "--host=unix:///var/run/docker.sock",
                "inspect",
                "--format",
                "{{.State.Running}}",
                "sherlock-foundation-" + service_name + "-1",
            ],
            env=docker_env
            if "docker_env" in globals()
            else __import__("os").environ.copy(),
            capture_output=True,
            text=True,
        )
        if observed.returncode == 0 and observed.stdout.strip() == "true":
            continue
    pidfile = root / f"data/foundation-{name}.pid"
    if pidfile.exists():
        import os

        try:
            os.kill(int(pidfile.read_text()), 0)
            continue
        except ProcessLookupError:
            pass
    with (root / f"data/foundation-{name}.log").open("ab") as log:
        process = subprocess.Popen(
            cmd,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    pidfile.write_text(str(process.pid))
print(
    json.dumps(
        {
            "gateway_url": "http://127.0.0.1:8010",
            "gateway_access": "workspace_only",
            "external_access": {
                "status": "missing_configuration" if missing_access else "starting_unverified",
                "missing_bindings": missing_access,
                "verify_command": ".venv/bin/python scripts/private_site_access.py --from-env --verify",
            },
            "worker": "Celery solo; bounded public-profile adapter",
            "logs": "data/foundation-*.log",
            "credentials_printed": False,
        }
    )
)

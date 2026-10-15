"""Reuse GCHQ CyberChef automatic decoding inside a network-disabled container."""

import hashlib, json, shutil, subprocess, uuid, threading
from pathlib import Path
from .sandbox import docker_args, docker_env, command

ROOT = Path(__file__).resolve().parents[1]


def _automatic(data: dict) -> dict:
    """Infer layered encodings with CyberChef Magic; expose real candidates and limits."""
    text = data.get("text", "")
    depth = int(data.get("depth", 3))
    if not isinstance(text, str) or not 1 <= len(text) <= 8000 or not 1 <= depth <= 3:
        raise ValueError("Automatic decoding supports 1–8,000 characters and depth 1–3")
    folder = ROOT / "integrations/decoders"
    package = folder / "node_modules/cyberchef/package.json"
    if (
        not package.is_file()
        or json.loads(package.read_text()).get("version") != "11.5.0"
    ):
        raise ValueError("Reviewed CyberChef 11.5.0 adapter is not installed")
    node = shutil.which("node")
    if not node:
        raise ValueError("Reviewed Node 24 runtime is unavailable")
    name = "sherlock-decode-" + uuid.uuid4().hex[:12]
    args = docker_args() + [
        "run",
        "--rm",
        "-i",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "1536m",
        "--memory-swap",
        "1536m",
        "--cpus",
        "1",
        "--pids-limit",
        "64",
        "--ulimit",
        "cpu=20:20",
        "--user",
        "1000:1000",
        "--mount",
        "type=bind,src=" + node + ",dst=/trusted/node,readonly",
        "--mount",
        "type=bind,src=" + str(folder) + ",dst=/decoders,readonly",
        "--entrypoint",
        "/trusted/node",
        "python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e",
        "--max-old-space-size=512",
        "/decoders/automatic.mjs",
    ]
    try:
        result = subprocess.run(
            args,
            input=json.dumps({"text": text, "depth": depth}),
            capture_output=True,
            text=True,
            timeout=45,
            env=docker_env(),
            check=False,
        )
        if result.returncode:
            raise ValueError(
                "Isolated CyberChef decoding failed or hit a resource limit; no host fallback was used"
            )
        if len(result.stdout) > 1024 * 1024:
            raise ValueError("Decoder output exceeded 1 MB")
        value = json.loads(result.stdout)
        value.update(
            input_sha256=hashlib.sha256(text.encode()).hexdigest(),
            runtime_sha256=hashlib.sha256(Path(node).read_bytes()).hexdigest(),
            adapter_sha256=hashlib.sha256(
                (folder / "automatic.mjs").read_bytes()
            ).hexdigest(),
            sandbox={
                "network": "none",
                "read_only": True,
                "memory_mb": 1536,
                "cpu": 1,
                "wall_seconds": 45,
                "input_transport": "stdin; no evidence vault or credentials mounted",
            },
            internal_attempt_count="Not exposed by CyberChef Magic; returned candidates are not the number of attempted transformations",
        )
        return value
    finally:
        try:
            command(["rm", "-f", name], timeout=5)
        except Exception:
            pass


DECODER_SLOTS = threading.BoundedSemaphore(2)


def automatic(data: dict) -> dict:
    """Bound simultaneous established-decoder containers independently of other analyses."""
    with DECODER_SLOTS:
        return _automatic(data)

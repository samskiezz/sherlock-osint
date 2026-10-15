"""Start a reviewed local Ollama service. Model downloads require --pull-model explicitly."""

import argparse, json, os, re, subprocess, time, sys
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.sandbox import command, docker_args, docker_env

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--pull-model", action="store_true")
args = parser.parse_args()
image = os.environ.get("SHERLOCK_OLLAMA_IMAGE", "ollama/ollama:0.40.3")
if os.uname().sysname == "Linux" and "SHERLOCK_OLLAMA_IMAGE" not in os.environ:
    try:
        command(["image", "inspect", "sherlock-ollama-cpu:0.40.3"])
        image = "sherlock-ollama-cpu:0.40.3"
    except Exception:
        pass
model = "qwen2.5:1.5b"
name = "sherlock-local-model"
inspected = json.loads(command(["image", "inspect", image]))[0]
image_id = inspected["Id"]
store = root / ".models"
store.mkdir(exist_ok=True)
try:
    container = json.loads(command(["inspect", name]))[0]
except Exception:
    container = None
if container and not container["State"]["Running"]:
    command(["start", name])
if not container:
    flags = [
        "run",
        "--detach",
        "--name",
        name,
        "--restart=unless-stopped",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=128",
        "--memory=4g",
        "--memory-swap=4g",
        "--cpus=4",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--publish",
        "127.0.0.1:11434:11434",
        "--mount",
        f"type=bind,src={store},dst=/models",
        "--tmpfs",
        f"/tmp:rw,nosuid,nodev,size=268435456,uid={os.getuid()},gid={os.getgid()},mode=700",
        "--env",
        "HTTP_PROXY",
        "--env",
        "HTTPS_PROXY",
        "--env",
        "NO_PROXY",
        "--env",
        "OLLAMA_MODELS=/models",
        "--env",
        "OLLAMA_HOST=0.0.0.0:11434",
        "--env",
        "OLLAMA_NUM_PARALLEL=1",
        "--env",
        "OLLAMA_MAX_LOADED_MODELS=1",
        "--env",
        "OLLAMA_KEEP_ALIVE=5m",
        "--tmpfs",
        f"/home/ubuntu/.ollama:rw,nosuid,nodev,noexec,size=16777216,uid={os.getuid()},gid={os.getgid()},mode=700",
    ]
    ca = Path("/etc/ssl/certs/ca-certificates.crt")
    if Path("/etc/codex/network-policy.json").exists() and ca.is_file():
        flags += [
            "--mount",
            f"type=bind,src={ca},dst=/run/trust-bundle.pem,readonly",
            "--env",
            "SSL_CERT_FILE=/run/trust-bundle.pem",
        ]
    command(flags + [image_id, "serve"], timeout=20)
client = httpx.Client(base_url="http://127.0.0.1:11434", trust_env=False, timeout=120)
for _ in range(40):
    try:
        client.get("/api/tags").raise_for_status()
        break
    except Exception:
        time.sleep(0.25)
else:
    raise SystemExit("Local model service did not start")
if args.pull_model:
    with client.stream(
        "POST", "/api/pull", json={"name": model, "stream": True}, timeout=120
    ) as response:
        response.raise_for_status()
        last = ""
        for line in response.iter_lines():
            if not line:
                continue
            state = json.loads(line)
            if state.get("error"):
                raise RuntimeError(
                    re.sub(
                        r'(https?://[^?\s"]+)\?[^"\s]+',
                        r"\1?[redacted]",
                        str(state["error"]),
                    )
                )
            text = state.get("status", "")
            if text != last:
                print(text, flush=True)
                last = text
models = client.get("/api/tags").json()
details = (
    client.post("/api/show", json={"name": model}).json()
    if any(m["name"] == model for m in models.get("models", []))
    else None
)
result = {
    "container": name,
    "image": image,
    "image_id": image_id,
    "listen_address": "127.0.0.1:11434",
    "model": model,
    "models": models,
    "model_details": details,
    "resource_limits": {"memory_gb": 4, "cpu": 4, "pids": 128},
    "network_note": "Networking enabled for the explicit model pull. Forensic processing containers remain network-disabled.",
}
(root / "artifacts/local-model-runtime.json").write_text(json.dumps(result, indent=2))
print(
    json.dumps(
        {
            "service": "ready",
            "model_installed": details is not None,
            "model": model,
            "image_id": image_id,
        }
    )
)

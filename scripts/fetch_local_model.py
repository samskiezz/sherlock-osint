"""Fetch a reviewed public OCI model through the session proxy; verify every blob before installation."""

import hashlib, json, os, re, shutil, sys
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[1]
store = root / ".models"
blobs = store / "blobs"
blobs.mkdir(parents=True, exist_ok=True)
registry = "https://registry.ollama.ai/v2/library/qwen2.5"
tag = "1.5b"
try:
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.get(registry + "/manifests/" + tag)
        response.raise_for_status()
        manifest_bytes = response.content
        manifest = response.json()
        layers = [manifest["config"], *manifest["layers"]]
        total = sum(l["size"] for l in layers)
        if total > 2 * 1024**3 or shutil.disk_usage(root).free < total * 2 + 1024**3:
            raise RuntimeError("Model exceeds the approved size/storage budget")
        for layer in layers:
            digest = layer["digest"]
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
                raise ValueError("Invalid model blob digest")
            expected = digest.split(":", 1)[1]
            destination = blobs / ("sha256-" + expected)
            if (
                destination.is_file()
                and hashlib.sha256(destination.read_bytes()).hexdigest() == expected
            ):
                continue
            temporary = blobs / (destination.name + ".download")
            hasher = hashlib.sha256()
            received = 0
            print(
                "Downloading verified layer",
                layer["mediaType"],
                layer["size"],
                flush=True,
            )
            with client.stream("GET", registry + "/blobs/" + digest) as fetched:
                fetched.raise_for_status()
                with temporary.open("wb") as f:
                    for chunk in fetched.iter_bytes(chunk_size=1024 * 1024):
                        received += len(chunk)
                        if received > layer["size"]:
                            raise ValueError("Model blob exceeds declared size")
                        f.write(chunk)
                        hasher.update(chunk)
            if received != layer["size"] or hasher.hexdigest() != expected:
                temporary.unlink(missing_ok=True)
                raise ValueError("Model blob integrity verification failed")
            temporary.chmod(0o400)
            os.replace(temporary, destination)
        path = store / "manifests/registry.ollama.ai/library/qwen2.5" / tag
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(manifest_bytes)
        record = {
            "source": registry + "/manifests/" + tag,
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "model": "qwen2.5:1.5b",
            "verified_blobs": layers,
            "bytes": total,
            "retrieval": "httpx via inherited session proxy; redirects handled normally; TLS verified",
            "installation": "Original OCI manifest and content-addressed SHA-256 blobs",
        }
        (root / "artifacts/local-model-integrity.json").write_text(
            json.dumps(record, indent=2)
        )
        print(
            json.dumps(
                {"model_installed": True, "bytes": total, "blobs_verified": len(layers)}
            )
        )
except Exception as ex:
    message = re.sub(r'(https?://[^?\s"]+)\?[^"\s]+', r"\1?[redacted]", str(ex))
    print("Model installation failed: " + message, file=sys.stderr)
    raise SystemExit(1)

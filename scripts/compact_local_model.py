"""Derive a CPU-only image from the installed reviewed image, preserving licences and CPU bytes."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.sandbox import command, docker_args, docker_env

root = Path(__file__).resolve().parents[1]
name = "sherlock-local-model"
info = json.loads(command(["inspect", name]))[0]
source = info["Image"]
prior = root / "artifacts/cpu-runtime-v9.json"
if prior.exists() and json.loads(prior.read_text()).get("derived_image_id") == source:
    print(json.dumps({"already_compacted": True, "image_id": source}))
    raise SystemExit(0)
removed = (
    "usr/lib/ollama/cuda_v12",
    "usr/lib/ollama/cuda_v13",
    "usr/lib/ollama/mlx_cuda_v13",
    "usr/lib/ollama/vulkan",
)
archive = root / "data/cpu-runtime.tar"
process = subprocess.Popen(
    docker_args() + ["export", name], stdout=subprocess.PIPE, env=docker_env()
)
kept_bytes = 0
skipped_bytes = 0
with (
    tarfile.open(fileobj=process.stdout, mode="r|") as src,
    tarfile.open(archive, mode="w|") as out,
):
    for member in src:
        clean = member.name.lstrip("./")
        if any(clean == p or clean.startswith(p + "/") for p in removed):
            skipped_bytes += member.size
            continue
        out.addfile(member, src.extractfile(member) if member.isfile() else None)
        kept_bytes += member.size
process.stdout.close()
if process.wait() != 0:
    raise RuntimeError("Export failed; original service retained")
if not (10_000_000 < kept_bytes < 800_000_000 and skipped_bytes > 4_000_000_000):
    raise RuntimeError("Unexpected image footprint; original service retained")
# Only a regenerable container is removed. Source image and model volume remain.
command(["stop", name], timeout=30)
command(["rm", name])
image = "sherlock-ollama-cpu:0.40.3"
command(
    [
        "import",
        "--change",
        'ENTRYPOINT ["/bin/ollama"]',
        "--change",
        "ENV LD_LIBRARY_PATH=/usr/lib/ollama",
        str(archive),
        image,
    ],
    timeout=120,
)
archive.unlink()
record = {
    "source_image_id": source,
    "derived_image": image,
    "derived_image_id": json.loads(command(["image", "inspect", image]))[0]["Id"],
    "removed_gpu_paths": removed,
    "preserved_bytes": kept_bytes,
    "excluded_bytes": skipped_bytes,
    "model_files_modified": False,
    "source_image_retained_until_validation": True,
}
(root / "artifacts/cpu-runtime-v9.json").write_text(json.dumps(record, indent=2))
print(json.dumps(record))

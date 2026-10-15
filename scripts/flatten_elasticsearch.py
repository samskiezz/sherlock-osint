"""Compact a local Elasticsearch runtime, excluding regenerated secrets and logs."""

import json
from pathlib import Path
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.sandbox import command, docker_args, docker_env

root = Path(__file__).resolve().parents[1]
name = "sherlock-foundation-elasticsearch-1"
info = json.loads(command(["inspect", name]))[0]
image = json.loads(command(["image", "inspect", info["Image"]]))[0]
record_path = root / "artifacts/elasticsearch-flat-v9.json"
old = json.loads(record_path.read_text()) if record_path.exists() else {}
if (
    old.get("runtime_sanitisation_version") == 2
    and old.get("derived_image_id") == image["Id"]
):
    print(
        json.dumps({"already_compacted_and_sanitised": True, "image_id": image["Id"]})
    )
    raise SystemExit(0)
provenance = image.get("RepoDigests") or old.get("official_source_image")
if not provenance:
    raise RuntimeError("Known upstream image provenance required before compaction")
archive = root / "data/elasticsearch-runtime.tar"
removed = [
    "usr/share/elasticsearch/config/elasticsearch.keystore",
    "usr/share/elasticsearch/config/elasticsearch.keystore.tmp",
    "usr/share/elasticsearch/config/certs",
    "usr/share/elasticsearch/logs",
]
source = subprocess.Popen(
    docker_args() + ["export", name], env=docker_env(), stdout=subprocess.PIPE
)
kept = 0
excluded = 0
with (
    tarfile.open(fileobj=source.stdout, mode="r|") as src,
    tarfile.open(archive, mode="w|") as dest,
):
    log_directory_seen = False
    for member in src:
        if (
            member.name.lstrip("./") == "usr/share/elasticsearch/logs"
            and member.isdir()
        ):
            dest.addfile(member)
            log_directory_seen = True
            continue
        clean = member.name.lstrip("./")
        if any(clean == p or clean.startswith(p + "/") for p in removed):
            excluded += member.size
            continue
        dest.addfile(member, src.extractfile(member) if member.isfile() else None)
        kept += member.size
    if not log_directory_seen:
        directory = tarfile.TarInfo("usr/share/elasticsearch/logs")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o775
        directory.uid = 1000
        directory.gid = 0
        dest.addfile(directory)
source.stdout.close()
if source.wait() != 0:
    raise RuntimeError("Export failed; original service retained")
command(["stop", name], timeout=30)
command(["rm", name])
changes = []
config = image["Config"]
for key in ("Entrypoint", "Cmd"):
    if config.get(key):
        changes += ["--change", key.upper() + " " + json.dumps(config[key])]
for key, instruction in [
    ("User", "USER"),
    ("WorkingDir", "WORKDIR"),
    ("StopSignal", "STOPSIGNAL"),
]:
    if config.get(key):
        changes += ["--change", instruction + " " + config[key]]
for value in config.get("Env", []):
    changes += ["--change", "ENV " + value]
tag = "sherlock-elasticsearch-flat:8.19.0"
command(["import", *changes, str(archive), tag], timeout=120)
archive.unlink()
new = json.loads(command(["image", "inspect", tag]))[0]
record = {
    "official_source_image": provenance,
    "source_runtime_image_id": image["Id"],
    "derived_image": tag,
    "derived_image_id": new["Id"],
    "preserved_runtime_file_bytes": kept,
    "excluded_bytes": excluded,
    "excluded_runtime_paths": removed,
    "runtime_secrets_excluded": True,
    "runtime_sanitisation_version": 2,
    "empty_log_directory_retained": True,
    "source_was_running_container": True,
    "preserved_files_unmodified": True,
    "volume_data_modified": False,
    "reason": "Compact VFS layers; regenerate private runtime keystore/certificates rather than baking them into the image",
    "image_bytes": new["Size"],
}
record_path.write_text(json.dumps(record, indent=2))
private = root / "data/foundation-compose.env"
lines = [
    line
    for line in private.read_text().splitlines()
    if not line.startswith("SHERLOCK_ELASTIC_IMAGE=")
]
private.write_text("\n".join(lines + ["SHERLOCK_ELASTIC_IMAGE=" + tag]) + "\n")
private.chmod(0o600)
command(["image", "rm", image["Id"]], timeout=30)
print(json.dumps(record))

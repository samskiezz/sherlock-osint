"""Generate separate local retrieval credentials without exporting secret values."""

import json
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
p = root / "data/foundation-compose.env"
if p.is_symlink() or p.stat().st_mode & 0o077:
    raise RuntimeError("Private Compose environment must be mode 0600")
values = dict(line.split("=", 1) for line in p.read_text().splitlines() if "=" in line)
values.setdefault("QDRANT_API_KEY", secrets.token_hex(32))
p.write_text("\n".join(k + "=" + v for k, v in values.items()) + "\n")
p.chmod(0o600)
cfg = {
    "qdrant_url": "http://127.0.0.1:56333",
    "qdrant_key": values["QDRANT_API_KEY"],
    "elastic_url": "http://127.0.0.1:59200",
    "elastic_password": values["ELASTIC_PASSWORD"],
    "ollama_url": "http://127.0.0.1:11434",
    "embedding_model": "all-minilm:22m",
}
r = root / "data/retrieval.json"
r.write_text(json.dumps(cfg))
r.chmod(0o600)
print(json.dumps({"configured": True, "credentials_exported": False}))

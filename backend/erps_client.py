"""ERPS is optional and fails explicitly. Credentials stay on the server."""
from __future__ import annotations
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
import httpx


def configuration():
    path = Path(os.environ.get("ERPS_CONFIG", Path(__file__).resolve().parents[1] / "data/erps.json"))
    data = {}
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
            raise RuntimeError("ERPS configuration must be a regular private file (0600)")
        data = json.loads(path.read_text())
    return {key: os.environ.get(key, data.get(key, "")) for key in ("ERPS_URL", "ERPS_TOKEN", "ERPS_READER_TOKEN", "ERPS_WRITER_TOKEN")}


class ErpsClient:
    def __init__(self, role="Admin", transport=None):
        cfg = configuration()
        key = {"Admin": "ERPS_TOKEN", "Analyst": "ERPS_WRITER_TOKEN", "Viewer": "ERPS_READER_TOKEN"}.get(role)
        if not key or not cfg.get(key) or not cfg.get("ERPS_URL"):
            raise RuntimeError("ERPS is not configured for this role")
        parsed = urlsplit(cfg["ERPS_URL"])
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password or parsed.path not in ("", "/"):
            raise RuntimeError("Invalid server-owned ERPS URL")
        self._c = httpx.Client(base_url=cfg["ERPS_URL"], timeout=180.0, trust_env=False,
            headers={"Authorization": "Bearer " + cfg[key], "X-ERPS-Purpose": "investigation"}, transport=transport)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._c.close()

    def request(self, method, path, **kwargs):
        response = self._c.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def resolve(self, mentions, constraints=None):
        return self.request("POST", "/resolve", json={"mentions": mentions, "constraints": constraints or []})

    def lineage(self, eid):
        return self.request("GET", f"/lineage/{eid}")

    def delete_source(self, source_var):
        return self.request("POST", "/deletion", json={"source_var": str(source_var)})

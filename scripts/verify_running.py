import hashlib, json, httpx, sqlite3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
c = httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=20)
current = c.get("/api/export/json").json()
before = json.loads((root / "artifacts/pre-restart-state.json").read_text())
evidence = current["evidence"]
old_layout = {
    b["id"]: {n["id"]: n["position"] for n in b["nodes"]} for b in before["boards"]
}
new_layout = {
    b["id"]: {n["id"]: n["position"] for n in b["nodes"]} for b in current["boards"]
}
old_hashes = {e["id"]: e["sha256"] for e in before["evidence"] if e["sha256"]}
new_hashes = {e["id"]: e["sha256"] for e in evidence if e["sha256"]}
result = {
    "actual_service_restart": True,
    "layout_preserved": old_layout == new_layout,
    "hash_records_preserved": all(
        new_hashes.get(k) == v for k, v in old_hashes.items()
    ),
    "enabled_watches": len([w for w in current["watches"] if w["enabled"]]),
    "byte_verification": [],
}
for e in evidence:
    if e["sha256"]:
        p = root / "data" / "originals" / e["sha256"]
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        result["byte_verification"].append(
            {
                "id": e["id"],
                "matches": actual == e["sha256"],
                "bytes": p.stat().st_size,
                "read_only": not bool(p.stat().st_mode & 0o222),
            }
        )
        if e["mime"] == "application/pdf":
            print("PDF pages", e["metadata"]["page_count"])
(root / "artifacts/restart-verification.json").write_text(json.dumps(result, indent=2))
manifest = [
    {
        "id": e["id"],
        "title": e["title"],
        "mime": e["mime"],
        "status": e["status"],
        "source_url": e["metadata"].get("original_url") or e["url"],
        "final_url": e["metadata"].get("final_url"),
        "retrieved_utc": e["metadata"].get("retrieved_utc"),
        "sha256": e["sha256"],
        "bytes": e["size"],
        "original_path": str(root / "data" / "originals" / e["sha256"]),
    }
    for e in evidence
    if e["sha256"]
]
(root / "artifacts/evidence-manifest.json").write_text(json.dumps(manifest, indent=2))
(root / "artifacts/SHA256SUMS").write_text(
    "\n".join(f"{e['sha256']}  data/originals/{e['sha256']}" for e in manifest) + "\n"
)
(root / "artifacts/watch-snapshot.json").write_text(
    json.dumps(c.get("/api/watches").json(), indent=2)
)
(root / "artifacts/case-export.json").write_text(json.dumps(current, indent=2))
(root / "artifacts/acquisition-status.json").write_text(
    json.dumps(c.get("/api/jobs").json(), indent=2)
)
print(
    json.dumps(
        {
            "layout_preserved": result["layout_preserved"],
            "hash_records_preserved": result["hash_records_preserved"],
            "originals_verified": len(manifest),
            "all_actual_bytes_match": all(
                x["matches"] and x["read_only"] for x in result["byte_verification"]
            ),
            "watches_enabled": result["enabled_watches"],
        }
    )
)
assert result["layout_preserved"] and result["hash_records_preserved"]
assert all(x["matches"] and x["read_only"] for x in result["byte_verification"])

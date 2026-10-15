"""Re-extract acquired files via the API's isolated processing path; originals stay untouched."""

import concurrent.futures, json
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[1]
with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=120) as c:
    evidence = [e for e in c.get("/api/evidence").json() if e["fileUrl"]]

    def process(e):
        r = c.post("/api/evidence/" + e["id"] + "/process")
        r.raise_for_status()
        updated = r.json()
        result = {
            "id": e["id"],
            "title": e["title"],
            "original_hash_unchanged": e["sha256"] == updated["sha256"],
            "sandbox": updated["metadata"]["sandbox"],
            "derivative_hashes": updated["metadata"]["derivative_hashes"],
        }
        print(e["id"], "isolated extraction complete", flush=True)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(process, evidence))
(root / "artifacts/case-sandbox-reprocessing.json").write_text(
    json.dumps(results, indent=2)
)
assert all(r["original_hash_unchanged"] for r in results)

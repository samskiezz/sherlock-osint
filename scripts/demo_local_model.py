"""Execute a real local model investigation; never substitutes a fixture model response."""

import json, time
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[1]
c = httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=10)
paper = next(
    e
    for e in c.get("/api/evidence").json()
    if e["mime"] == "application/pdf" and e["fileUrl"]
)
r = c.post(
    "/api/investigations",
    json={
        "question": "Name the two inventors printed on page 1. Use a single short exact quote from the provided passage for each finding. Do not infer later identities, employers or research teams.",
        "evidence_ids": [paper["id"]],
        "provider": "ollama",
        "model": "qwen2.5:1.5b",
    },
)
r.raise_for_status()
run = r.json()
print("Local model investigation queued", run["id"], flush=True)
for _ in range(120):
    run = c.get("/api/investigations/" + run["id"]).json()
    if run["status"] in ("COMPLETE", "FAILED"):
        break
    time.sleep(1)
(root / "artifacts/local-model-investigation.json").write_text(
    json.dumps(run, indent=2)
)
assert run["status"] == "COMPLETE", {"status": run["status"], "error": run["error"]}
assert run["tasks"][4]["output"] is not None
assert run["result"]["mode"] == "ollama"
assert all(t["status"] == "COMPLETE" for t in run["tasks"])
print(
    json.dumps(
        {
            "run_id": run["id"],
            "status": run["status"],
            "provider": run["provider"],
            "model": run["model"],
            "raw_model_findings": len(run["tasks"][4]["output"].get("findings", [])),
            "citation_checked_proposals": len(run["result"]["findings"]),
            "rejected_findings": len(run["result"]["rejected_findings"]),
            "review_state": run["result"]["review_state"],
            "integrity_checks": run["result"]["integrity_checks"],
        }
    ),
    flush=True,
)

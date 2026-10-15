import json, time
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[1]
c = httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=10)
original = next(
    e
    for e in c.get("/api/evidence").json()
    if e["mime"] == "application/pdf" and e["fileUrl"]
)
r = c.post(
    "/api/investigations",
    json={
        "question": "Which inventor names appear on page one of the acquired patent, and what attribution remains unverified?",
        "evidence_ids": [original["id"]],
        "provider": "deterministic",
    },
)
r.raise_for_status()
run = r.json()
for _ in range(40):
    run = c.get("/api/investigations/" + run["id"]).json()
    if run["status"] in ("COMPLETE", "FAILED"):
        break
    time.sleep(0.25)
assert run["status"] == "COMPLETE", run
assert all(t["status"] == "COMPLETE" for t in run["tasks"])
assert run["result"]["sources"]
assert run["result"]["sources"][0]["quote"] in original["text"]
assert run["result"]["findings"] == []
(root / "artifacts/investigation-demonstration.json").write_text(
    json.dumps(run, indent=2)
)
print(
    json.dumps(
        {
            "id": run["id"],
            "status": run["status"],
            "completed_agent_tasks": len(run["tasks"]),
            "quoted_originals": len(run["result"]["sources"]),
            "model_invoked": False,
            "factual_edges_created": False,
            "review_state": run["result"]["review_state"],
        }
    )
)

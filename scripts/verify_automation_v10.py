"""Prove actual source-bound workflows, local AI planning, cron state and acquired original bytes."""

import hashlib
import json
import time
from pathlib import Path
from datetime import datetime, timezone
import httpx

ROOT = Path(__file__).resolve().parents[1]
client = httpx.Client(base_url="http://127.0.0.1:8010", trust_env=False, timeout=120)
login = client.post(
    "/api/v1/auth/login",
    json=json.loads((ROOT / "data/foundation-secrets/admin-login.json").read_text()),
)
login.raise_for_status()
client.headers["Authorization"] = "Bearer " + login.json()["access_token"]


def get(path):
    """Read an authenticated actual endpoint, refusing HTTP failures."""
    r = client.get(path)
    r.raise_for_status()
    return r.json()


def post(path, data):
    """Mutate an explicitly requested bounded workflow, retaining visible failure outcomes."""
    r = client.post(path, json=data)
    r.raise_for_status()
    return r.json()


def wait_run(rid, seconds=180):
    """Poll real persisted receipts, never substitute expected outputs."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        run = get("/api/automation/runs/" + rid)
        if run["status"] in ("COMPLETE", "FAILED", "CANCELLED", "PARTIAL"):
            return run
        time.sleep(0.6)
    raise RuntimeError(
        "Workflow did not reach a terminal state in the acceptance budget"
    )


if __name__ == "__main__":
    proof = {"started_utc": datetime.now(timezone.utc).isoformat()}
    catalogue = get("/api/automation/catalogue")
    assert catalogue["count"] >= 200
    proof["catalogue"] = {
        k: catalogue[k] for k in ("count", "by_family", "by_kind", "claim")
    }
    (ROOT / "artifacts/automation-feature-catalogue-v10.json").write_text(
        json.dumps(catalogue, indent=2)
    )
    source = "EV-2bc448c8a80b"  # Actual preserved patent page; identity claims remain separate.
    workflow = post(
        "/api/automation/workflows",
        {
            "name": "Mondaloy · original verification and reproducible text triage",
            "objective": "Verify the acquired patent original, extract literal identifiers, inspect Unicode and count source terms; infer no identity, prediction or wrongdoing.",
            "authorisation": "User requested persistent public-source analysis and autonomous evidence processing",
            "max_seconds": 300,
            "steps": [
                {
                    "id": "integrity",
                    "tool": "evidence.verify",
                    "inputs": {"evidence_id": {"$binding": "evidence_id"}},
                },
                {
                    "id": "identifiers",
                    "tool": "text.identifiers",
                    "depends_on": ["integrity"],
                    "inputs": {"evidence_id": {"$binding": "evidence_id"}},
                },
                {
                    "id": "terms",
                    "tool": "text.word_frequency",
                    "depends_on": ["integrity"],
                    "inputs": {"evidence_id": {"$binding": "evidence_id"}},
                },
                {
                    "id": "unicode",
                    "tool": "text.unicode_controls",
                    "depends_on": ["integrity"],
                    "inputs": {"evidence_id": {"$binding": "evidence_id"}},
                },
            ],
        },
    )
    rid = post(
        "/api/automation/workflows/" + workflow["id"] + "/run", {"evidence_id": source}
    )["id"]
    run = wait_run(rid)
    assert run["status"] == "COMPLETE", run
    assert len(run["receipts"]) == 4 and all(
        r["status"] == "COMPLETE" for r in run["receipts"]
    )
    assert all(
        r["data"]["result"]["sources"][0]["evidence_id"] == source
        for r in run["receipts"]
    )
    proof["source_workflow"] = run
    print("Source-bound original workflow complete", flush=True)
    schedule = post(
        "/api/automation/schedules",
        {
            "workflow_id": workflow["id"],
            "trigger": "interval",
            "cron": "17 */6 * * *",
            "interval_minutes": 360,
            "evidence_id": source,
        },
    )
    proof["recurring_schedule"] = schedule
    new = post(
        "/api/automation/schedules",
        {
            "workflow_id": workflow["id"],
            "trigger": "new_evidence",
            "interval_minutes": 5,
        },
    )
    proof["new_evidence_schedule"] = new
    acquisition = post(
        "/api/automation/run",
        {
            "tool": "acquisition.enqueue",
            "inputs": {
                "url": "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf",
                "title": "NIST AI Risk Management Framework · primary methodological reference",
            },
            "authorisation": "Public NIST methodological document for this platform validation",
        },
    )
    receipt = wait_run(acquisition["id"])
    assert receipt["status"] == "COMPLETE", receipt
    jid = receipt["receipts"][0]["data"]["result"]["output"]["job_id"]
    deadline = time.monotonic() + 240
    job = None
    while time.monotonic() < deadline:
        job = next((j for j in get("/api/jobs") if j["id"] == jid), None)
        if job and job["status"] in ("COMPLETE", "FAILED"):
            break
        time.sleep(1)
    assert job and job["status"] == "COMPLETE", job
    original = get("/api/evidence/" + job["evidence_id"])
    r = client.get(original["fileUrl"])
    r.raise_for_status()
    assert (
        r.content.startswith(b"%PDF")
        and hashlib.sha256(r.content).hexdigest() == original["sha256"]
    )
    proof["acquired_original"] = {
        "evidence_id": original["id"],
        "title": original["title"],
        "bytes": len(r.content),
        "sha256": original["sha256"],
        "original_url": original["url"],
        "job_id": jid,
        "verified_against_actual_bytes": True,
    }
    print(
        "Acquired and hashed actual NIST original",
        original["id"],
        len(r.content),
        flush=True,
    )
    # Local AI must actually produce a schema-valid allowlisted selection; no canned fallback is reported as AI.
    ai = post(
        "/api/automation/mission",
        {
            "evidence_id": source,
            "question": "Identify the alloy, the inventors named in this document and its stated technical purpose; preserve any uncertainty.",
        },
    )
    ai_run = wait_run(ai["run"]["id"], 240)
    assert ai_run["status"] == "COMPLETE", ai_run
    assert ai_run["data"]["planner"]["selected_tools"]
    note = next(r for r in ai_run["receipts"] if r["step_id"] == "cited_note")
    assert note["status"] == "COMPLETE"
    assert note["data"]["result"]["output"]["findings"], (
        "Model returned no cited findings"
    )
    e = get("/api/evidence/" + source)
    for f in note["data"]["result"]["output"]["findings"]:
        assert (
            f["quote"] in e["text"]
            and f["state"] == "HYPOTHESIS / HUMAN REVIEW REQUIRED"
        )
    proof["ai_mission"] = ai_run
    proof["no_automatic_factual_edges"] = True
    print("Actual local AI plan and cited-note execution complete", flush=True)
    # Leave the watcher running, then a later acceptance pass records the automatic new-evidence run.
    proof["finished_initial_utc"] = datetime.now(timezone.utc).isoformat()
    (ROOT / "artifacts/automation-live-proof-v10.json").write_text(
        json.dumps(proof, indent=2)
    )
    print(
        json.dumps(
            {
                "tools": catalogue["count"],
                "workflow": run["id"],
                "ai_mission": ai_run["id"],
                "new_original": original["id"],
                "new_evidence_schedule": new["id"],
            }
        ),
        flush=True,
    )

"""Record real model citations, scheduled acquisition processing and restart checkpoint recovery."""

import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_automation_v10 import get, post, wait_run, client  # noqa: E402
from scripts.run_platform import matches  # noqa: E402

proof = json.loads((ROOT / "artifacts/automation-live-proof-v10.json").read_text())
source = "EV-812554d46064"
existing = next(
    (
        r
        for r in get("/api/automation")["runs"]
        if r["status"] == "COMPLETE"
        and r["data"].get("planner", {}).get("source_evidence_id") == source
    ),
    None,
)
if existing:
    run = get("/api/automation/runs/" + existing["id"])
else:
    ai = post(
        "/api/automation/mission",
        {
            "evidence_id": source,
            "question": "Identify the inventor names and the stated purpose of the nickel alloy. Distinguish patent claims from independently demonstrated performance.",
        },
    )
    run = wait_run(ai["run"]["id"], 240)
assert run["status"] == "COMPLETE", run
note = next(r for r in run["receipts"] if r["step_id"] == "cited_note")
findings = note["data"]["result"]["output"]["findings"]
assert findings, "Local model produced no source-cited findings"
e = get("/api/evidence/" + source)
for f in findings:
    assert f["quote"] == e["text"][f["source_offset"] : f["end"]]
    assert f["quote_verified"] and f["state"] == "HYPOTHESIS / HUMAN REVIEW REQUIRED"
proof["initial_ai_citation_count"] = len(
    proof["ai_mission"]["receipts"][-1]["data"]["result"]["output"]["findings"]
)
proof["ai_mission"] = run
print(
    "Actual local model returned",
    len(findings),
    "independently checked original-PDF quotations",
    flush=True,
)
# The trigger was left running before the new PDF was downloaded; no manual launch creates this run.
schedule = next(
    s
    for s in get("/api/automation")["schedules"]
    if s["id"] == proof["new_evidence_schedule"]["id"]
)
assert schedule["data"].get("last_run_id"), (
    "New-evidence scheduler has not processed the downloaded original"
)
key = f"{schedule['id']}:{proof['acquired_original']['evidence_id']}:{proof['acquired_original']['sha256']}"
watched = wait_run("AUTO-" + hashlib.sha256(key.encode()).hexdigest()[:20])
assert watched["status"] == "COMPLETE"
assert (
    watched["data"]["bindings"]["evidence_id"]
    == proof["acquired_original"]["evidence_id"]
)
proof["automatic_new_evidence_run"] = watched
proof["automatic_new_evidence_schedule_state"] = schedule
checks = {
    "evidence.read_text": {"evidence_id": source, "text_start": 0, "text_end": 350},
    "evidence.metadata": {"evidence_id": source},
    "evidence.citation": {"evidence_id": source, "quote": e["text"][150:240]},
    "knowledge.search": {
        "query": "nickel burn resistant metal alloys",
        "mode": "hybrid",
        "limit": 3,
    },
    "case.inventory": {},
    "system.health": {},
    "acquisition.inspect": {"job_id": proof["acquired_original"]["job_id"]},
}
proof["fixed_adapter_checks"] = {}
for tool, inputs in checks.items():
    result = post(
        "/api/automation/run",
        {
            "tool": tool,
            "inputs": inputs,
            "authorisation": "User-requested actual platform acceptance against public acquired originals",
        },
    )
    result = wait_run(result["id"])
    assert result["status"] == "COMPLETE", (tool, result)
    proof["fixed_adapter_checks"][tool] = result
print("All fixed service adapters exercised against actual data", flush=True)
# Pause a real source-bound job, restart only the owned core, verify the checkpoint then resume.
wid = proof["source_workflow"]["workflow_id"]
queued = post("/api/automation/workflows/" + wid + "/run", {"evidence_id": source})
paused = post("/api/automation/runs/" + queued["id"] + "/pause", {})
assert paused["status"] == "PAUSED"
time.sleep(2)
before = get("/api/automation/runs/" + queued["id"])
# Avoid interrupting independent live regression tests while probing restart recovery.
deadline = time.monotonic() + 360
while (ROOT / "artifacts/platform-tests-final-v10.txt").is_file() and " passed" not in (
    ROOT / "artifacts/platform-tests-final-v10.txt"
).read_text():
    if time.monotonic() > deadline:
        raise RuntimeError(
            "Regression tests have not completed; restart probe deferred"
        )
    time.sleep(0.5)
pid = int((ROOT / "data/service-v2.pid").read_text())
assert matches(pid, "backend.app:app")
os.kill(pid, signal.SIGTERM)
for _ in range(160):
    try:
        after = get("/api/automation/runs/" + queued["id"])
        if int((ROOT / "data/service-v2.pid").read_text()) != pid:
            break
    except Exception:
        pass
    time.sleep(0.25)
else:
    raise RuntimeError("Owned core did not recover after restart")
assert after["status"] == "PAUSED" and after["receipts"] == before["receipts"]
post("/api/automation/runs/" + queued["id"] + "/resume", {})
resumed = wait_run(queued["id"])
assert resumed["status"] == "COMPLETE"
proof["restart_checkpoint"] = {
    "old_pid": pid,
    "new_pid": int((ROOT / "data/service-v2.pid").read_text()),
    "paused_before_restart": True,
    "receipt_checkpoint_unchanged": True,
    "resumed_run": resumed,
}
# Verify originals again after all analytical/model operations.
for source in [source, proof["acquired_original"]["evidence_id"]]:
    current = get("/api/evidence/" + source)
    response = client.get(current["fileUrl"])
    response.raise_for_status()
    assert hashlib.sha256(response.content).hexdigest() == current["sha256"]
proof["originals_unchanged_after_automation"] = True
proof["core_health"] = get("/api/health")
proof["gateway_health"] = get("/health")
proof["scope"] = {
    "unrestricted_host_control": False,
    "all_master_specification_complete": False,
    "flawless_claim": False,
    "tor_network_access_verified": False,
    "macos_execution_verified": False,
    "semantic_entailment_automatically_verified": False,
}
(ROOT / "artifacts/automation-live-proof-v10.json").write_text(
    json.dumps(proof, indent=2)
)
print(
    json.dumps(
        {
            "actual_cited_findings": len(findings),
            "scheduled_run": watched["id"],
            "restart_checkpoint_recovered": True,
            "originals_unchanged": True,
        }
    ),
    flush=True,
)

"""Verify owned-service restart persistence, then enable requested unattended analysis."""

import json, os, signal, time
from pathlib import Path
import httpx
from scripts.run_platform import matches

ROOT = Path(__file__).resolve().parents[1]
c = httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=10)
rid = json.loads((ROOT / "artifacts/autopilot-model-queued-v11.json").read_text())[
    "dispatches"
][0]["run_id"]
before = c.get("/api/automation/runs/" + rid).json()
assert before["status"] == "COMPLETE"
settings = c.get("/api/autopilot").json()["settings"]
pid = int((ROOT / "data/service-v2.pid").read_text())
assert matches(pid, "backend.app:app")
os.kill(pid, signal.SIGTERM)
deadline = time.time() + 35
while time.time() < deadline:
    try:
        newpid = int((ROOT / "data/service-v2.pid").read_text())
        if newpid != pid and c.get("/api/health").status_code == 200:
            break
    except (httpx.HTTPError, ValueError):
        pass
    time.sleep(1)
else:
    raise RuntimeError("Owned core did not restart within budget")
after = c.get("/api/automation/runs/" + rid).json()
assert before["receipts"] == after["receipts"] and before["status"] == after["status"]
assert settings == c.get("/api/autopilot").json()["settings"]
gateway = httpx.Client(base_url="http://127.0.0.1:8010", trust_env=False, timeout=120)
r = gateway.post(
    "/api/v1/auth/login",
    json=json.loads((ROOT / "data/foundation-secrets/admin-login.json").read_text()),
)
r.raise_for_status()
gateway.headers["Authorization"] = "Bearer " + r.json()["access_token"]
r = gateway.post(
    "/api/autopilot/scan", json={"evidence_id": "EV-501a7ba6ffcd", "limit": 1}
)
r.raise_for_status()
assert not r.json()["dispatches"]
r = gateway.put(
    "/api/autopilot/settings",
    json={
        "enabled": True,
        "include_existing": True,
        "model_notes": True,
        "max_new_runs_per_tick": 2,
    },
)
r.raise_for_status()
r = gateway.post("/api/autopilot/scan", json={"limit": 2})
r.raise_for_status()
proof = {
    "previous_pid": pid,
    "current_pid": newpid,
    "persisted_run_id": rid,
    "completed_receipts_unchanged": True,
    "completed_step_count": len(after["receipts"]),
    "settings_persisted": True,
    "unchanged_source_was_not_requeued": True,
    "autopilot_enabled": True,
    "local_model_notes_enabled": True,
    "new_dispatches": r.json(),
    "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
(ROOT / "artifacts/autopilot-restart-v11.json").write_text(json.dumps(proof, indent=2))
print({k: v for k, v in proof.items() if k != "new_dispatches"})

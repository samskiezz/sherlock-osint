"""Real service restart while a scheduled research run is paused at a checkpoint."""

import hashlib
import json
import subprocess
import time
from pathlib import Path

import httpx

root = Path(__file__).resolve().parents[1]
c = httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=10)
campaign = next(
    x
    for x in c.get("/api/research").json()["campaigns"]
    if x["name"].startswith("Public propulsion records")
)
existing = {r["id"] for r in c.get("/api/research").json()["runs"]}
c.post(f"/api/research/{campaign['id']}/run").raise_for_status()
paused = None
for _ in range(160):
    runs = c.get("/api/research").json()["runs"]
    candidate = next(
        (
            r
            for r in runs
            if r["campaign_id"] == campaign["id"]
            and r["id"] not in existing
            and any(t["status"] == "COMPLETE" for t in r["tasks"])
            and r["status"] not in ("COMPLETE", "PARTIAL", "FAILED")
        ),
        None,
    )
    if candidate:
        c.post(f"/api/research/{campaign['id']}/pause").raise_for_status()
        paused = next(
            r
            for r in c.get("/api/research").json()["runs"]
            if r["id"] == candidate["id"]
        )
        break
    time.sleep(0.25)
assert paused and paused["status"] == "PAUSED", (
    "Could not pause a real research checkpoint"
)
print("Paused actual research checkpoint", paused["id"], flush=True)
originals = [e for e in c.get("/api/evidence").json() if e["sha256"]]
pid = int((root / "data/service-v2.pid").read_text())
args = subprocess.check_output(["ps", "-p", str(pid), "-o", "args="], text=True)
assert "uvicorn backend.app:app" in args
subprocess.run(["kill", "-TERM", str(pid)], check=True)
for _ in range(120):
    try:
        c.get("/api/health")
        time.sleep(0.1)
    except httpx.RequestError:
        break
with (root / "data/service-v2.log").open("ab") as log:
    process = subprocess.Popen(
        [str(root / "start.sh")],
        cwd=root,
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
(root / "data/service-v2.pid").write_text(str(process.pid))
for _ in range(50):
    try:
        if c.get("/api/health").status_code == 200:
            break
    except httpx.RequestError:
        pass
    time.sleep(0.2)
recovered = next(
    r for r in c.get("/api/research").json()["runs"] if r["id"] == paused["id"]
)
assert recovered["status"] == "PAUSED" and recovered["cursor"] == paused["cursor"]
assert [t["id"] for t in recovered["tasks"]] == [t["id"] for t in paused["tasks"]]
c.post(f"/api/research/{campaign['id']}/resume").raise_for_status()
for _ in range(200):
    final = next(
        r for r in c.get("/api/research").json()["runs"] if r["id"] == paused["id"]
    )
    if final["status"] in ("COMPLETE", "PARTIAL", "FAILED"):
        break
    time.sleep(0.25)
assert final["status"] in ("COMPLETE", "PARTIAL"), final
assert final["data"]["result"]["acquired"]
assert len({t["id"] for t in final["tasks"]}) == len(final["tasks"])
for original in originals:
    path = root / "data/originals" / original["sha256"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original["sha256"]
proof = {
    "paused_run": paused["id"],
    "checkpoint_retained": True,
    "initial_task_ids_retained": all(
        t["id"] in {x["id"] for x in final["tasks"]} for t in paused["tasks"]
    ),
    "resumed_status": final["status"],
    "originals_verified": len(originals),
    "result": final["data"]["result"],
    "tor_status": c.get("/api/onion/status").json(),
}
(root / "artifacts/research-restart-v4.json").write_text(json.dumps(proof, indent=2))
print(
    json.dumps({k: v for k, v in proof.items() if k not in ("result", "tor_status")}),
    flush=True,
)

"""Real service restart acceptance: paused checkpoint, board layout and immutable originals."""

import hashlib, json, subprocess, time
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[1]
c = httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=10)
evidence = c.get("/api/evidence").json()
paper = next(e for e in evidence if e["mime"] == "application/pdf" and e["fileUrl"])
run = None
for _ in range(3):
    created = c.post(
        "/api/investigations",
        json={
            "question": "Restart checkpoint: show exact inventor names in the acquired patent",
            "evidence_ids": [paper["id"]],
        },
    ).json()
    paused = c.post("/api/investigations/" + created["id"] + "/pause")
    if paused.status_code == 200:
        run = paused.json()
        break
assert run and run["status"] == "PAUSED", "Could not obtain a paused checkpoint"
before = c.get("/api/export/json").json()
task_ids = [t["id"] for t in run["tasks"]]
pid = int((root / "data/service-v2.pid").read_text())
args = subprocess.check_output(["ps", "-p", str(pid), "-o", "args="], text=True)
assert "uvicorn backend.app:app" in args
subprocess.run(["kill", "-TERM", str(pid)], check=True)
for _ in range(60):
    try:
        c.get("/api/health")
        time.sleep(0.1)
    except httpx.RequestError:
        break
with (root / "data/service-v2.log").open("ab") as log:
    server = subprocess.Popen(
        [str(root / "start.sh")],
        cwd=root,
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
(root / "data/service-v2.pid").write_text(str(server.pid))
for _ in range(40):
    try:
        if c.get("/api/health").status_code == 200:
            break
    except httpx.RequestError:
        pass
    time.sleep(0.2)
else:
    raise AssertionError("Service did not restart")
recovered = c.get("/api/investigations/" + run["id"]).json()
assert recovered["status"] == "PAUSED"
assert recovered["cursor"] == run["cursor"]
assert [t["id"] for t in recovered["tasks"]] == task_ids
c.post("/api/investigations/" + run["id"] + "/resume").raise_for_status()
for _ in range(40):
    resumed = c.get("/api/investigations/" + run["id"]).json()
    if resumed["status"] in ("COMPLETE", "FAILED"):
        break
    time.sleep(0.2)
assert resumed["status"] == "COMPLETE", resumed
assert resumed["result"]["sources"]
assert [t["id"] for t in resumed["tasks"]] == task_ids
current = c.get("/api/export/json").json()


def layouts(data):
    return {
        b["id"]: {n["id"]: n["position"] for n in b["nodes"]} for b in data["boards"]
    }


assert layouts(before) == layouts(current)
checks = []
for e in evidence:
    if e["sha256"]:
        p = root / "data/originals" / e["sha256"]
        checks.append(
            {
                "id": e["id"],
                "hash_matches": hashlib.sha256(p.read_bytes()).hexdigest()
                == e["sha256"],
                "read_only": not bool(p.stat().st_mode & 0o222),
            }
        )
assert all(ch["hash_matches"] and ch["read_only"] for ch in checks)
result = {
    "actual_service_restart": True,
    "paused_checkpoint_retained": True,
    "resumed_to_completion": True,
    "same_task_ids": task_ids,
    "run_id": run["id"],
    "cursor_before_restart": run["cursor"],
    "layout_preserved": True,
    "enabled_watches": sum(w["enabled"] for w in current["watches"]),
    "original_verification": checks,
}
(root / "artifacts/checkpoint-restart-verification.json").write_text(
    json.dumps(result, indent=2)
)
print(
    json.dumps(
        {
            "checkpoint_retained": True,
            "resumed_to_completion": True,
            "layout_preserved": True,
            "originals_verified": len(checks),
            "run_id": run["id"],
        }
    )
)

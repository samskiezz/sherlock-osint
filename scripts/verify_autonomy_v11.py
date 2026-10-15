"""Exercise actual authenticated services and preserve exact receipts, never credentials."""

import json, time, hashlib, sqlite3
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/autonomy-live-v11.json"
c = httpx.Client(base_url="http://127.0.0.1:8010", trust_env=False, timeout=120)
r = c.post(
    "/api/v1/auth/login",
    json=json.loads((ROOT / "data/foundation-secrets/admin-login.json").read_text()),
)
r.raise_for_status()
c.headers["Authorization"] = "Bearer " + r.json()["access_token"]


def call(path, data=None, method="POST"):
    """Send an authenticated fixed owned-service request and reject failure."""
    r = c.request(method, path, json=data)
    if r.is_error:
        raise RuntimeError(path + ": " + r.text[:2000])
    return r.json()


proof = {"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def save():
    """Checkpoint reviewable non-secret acceptance results."""
    OUT.write_text(json.dumps(proof, indent=2))


proof["catalogue"] = call("/api/automation/catalogue", method="GET")
proof["queued"] = {}
for name, tool, inputs in [
    ("auto_hex", "decoder.auto", {"text": "436f6c6520416c6c656e"}),
    ("auto_layered", "decoder.auto", {"text": "NDg2NTZjNmM2ZjIwNzc2ZjcyNmM2NA=="}),
    ("gematria", "gematria.all", {"text": "Cole Allen", "targets": ["Allen Cole"]}),
]:
    proof["queued"][name] = call(
        "/api/automation/run",
        {
            "tool": tool,
            "inputs": inputs,
            "authorisation": "User requested real automatic decoding and gematria verification",
        },
    )["id"]
proof["visual"] = call(
    "/api/visual/search", {"evidence_id": "EV-6a350b477547", "limit": 20}
)
proof["automatic_profile"] = call(
    "/api/autopilot/scan", {"evidence_id": "EV-9eb4054cad17", "limit": 1}
)
feed = call(
    "/api/social/feeds",
    {
        "name": "Looking Glass public case accounts",
        "query": "from:CForce3000 OR from:Bohrdom1 OR from:HenryMa79561893",
        "mode": "filtered_stream",
        "interval_seconds": 120,
        "acquire_media": True,
    },
)
proof["x_feed"] = feed
proof["x_poll"] = call("/api/social/feeds/" + feed["id"] + "/poll", {})
proof["prediction_audit"] = call(
    "/api/prediction-audits",
    {
        "artefact_id": "EV-501a7ba6ffcd",
        "artefact_quote": "Cole Allen",
        "claimed_publication_utc": "2023-12-22T00:00:00Z",
        "event_utc": "2026-04-25T00:00:00Z",
        "specific_outcome": "An attack at the White House Correspondents Dinner in April 2026",
        "specificity_terms": ["attack", "2026"],
        "counterevidence_ids": ["EV-501a7ba6ffcd"],
        "analysis_notes": "Audit of a name-only claim quoted in an acquired secondary fact-check. No original X post or independently dated historical header has been acquired here. Entered publication time is an allegation, not verified by this test.",
    },
)
existing = call("/api/research", method="GET")
# A real persisted recurring source watch; query results remain unverified leads.
name = "Waterfall artefact provenance and historical image comparisons"
rows = existing.get("campaigns", []) if isinstance(existing, dict) else existing
if not any(x.get("name") == name for x in rows):
    proof["research_campaign"] = call(
        "/api/research",
        {
            "name": name,
            "question": "Acquire public original and historical versions of Eternal Waterfall and compare the overlay claim. Keep artwork, altered composite, publication date claims and independent archival dates distinct; test conventional image-editing explanations.",
            "queries": ['"Eternal Waterfall" "Distinct Mind"', '"Js9auX5_9R8"'],
            "providers": ["source_pages", "public_web", "internet_archive"],
            "seeds": [
                "https://unsplash.com/photos/a-multicolored-image-of-a-multi-colored-background-Js9auX5_9R8",
                "https://leadstories.com/hoax-alert/2026/04/fact-check-iconic-raised-fist-scene-from-butler-assassination-attempt-is-not-hidden-within-an-abstract-digital-picture.html",
            ],
            "max_downloads": 4,
            "cron_expression": "15 */6 * * *",
            "collect_images": True,
        },
    )
save()
ids = dict(proof["queued"])
for i, d in enumerate(proof["automatic_profile"]["dispatches"]):
    ids["profile_" + str(i)] = d["run_id"]
proof["runs"] = {}
deadline = time.time() + 650
while time.time() < deadline:
    for name, rid in ids.items():
        proof["runs"][name] = call("/api/automation/runs/" + rid, method="GET")
    save()
    if all(
        r["status"] in ["COMPLETE", "PARTIAL", "FAILED", "CANCELLED"]
        for r in proof["runs"].values()
    ):
        break
    time.sleep(3)
proof["checks"] = {}
for name, wanted in [("auto_hex", "Cole Allen"), ("auto_layered", "Hello world")]:
    run = proof["runs"][name]
    output = (
        run["receipts"][0]["data"].get("result", {}).get("output", {})
        if run["receipts"]
        else {}
    )
    proof["checks"][name] = run["status"] == "COMPLETE" and any(
        x.get("data") == wanted for x in output.get("candidates", [])
    )
proof["checks"]["gematria"] = proof["runs"]["gematria"]["status"] == "COMPLETE"
proof["checks"]["no_fake_x_capture"] = proof["x_poll"]["status"] == "NOT_CONFIGURED"
proof["checks"]["name_is_not_prediction"] = (
    proof["prediction_audit"]["assessment"]["assessment"] == "NOT ESTABLISHED"
)
for name, run in proof["runs"].items():
    if name.startswith("profile_"):
        receipts = [r["data"] for r in run["receipts"] if r["status"] == "COMPLETE"]
        proof["checks"]["real_parallel_overlap"] = any(
            a.get("started_unix", 0) < b.get("finished_unix", 0)
            and b.get("started_unix", 0) < a.get("finished_unix", 0)
            for i, a in enumerate(receipts)
            for b in receipts[i + 1 :]
        )
proof["evidence_files"] = []
with sqlite3.connect(ROOT / "data/case.db") as db:
    db.row_factory = sqlite3.Row
    for eid in [
        "EV-501a7ba6ffcd",
        "EV-6a350b477547",
        "EV-0303ca000ce9",
        "EV-9eb4054cad17",
    ]:
        row = dict(
            db.execute(
                "SELECT id,title,path,sha256,size,mime,url FROM evidence WHERE id=?",
                (eid,),
            ).fetchone()
        )
        path = Path(row.pop("path"))
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        row["hash_verified"] = actual == row["sha256"]
        proof["evidence_files"].append(row)
proof["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
save()
print(
    json.dumps(
        {
            "checks": proof["checks"],
            "statuses": {k: v["status"] for k, v in proof["runs"].items()},
        },
        indent=2,
    )
)
if not all(proof["checks"].values()):
    raise SystemExit("An acceptance check failed; inspect exact receipts")

"""Publish an evidence board with actual acquired images and source-attributed counterevidence."""

import json
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
c = httpx.Client(base_url="http://127.0.0.1:8010", trust_env=False, timeout=90)
r = c.post(
    "/api/v1/auth/login",
    json=json.loads((ROOT / "data/foundation-secrets/admin-login.json").read_text()),
)
r.raise_for_status()
c.headers["Authorization"] = "Bearer " + r.json()["access_token"]


def call(path, data=None, method="POST"):
    """Require success from the owned authenticated service."""
    r = c.request(method, path, json=data)
    r.raise_for_status()
    return r.json()


source = "EV-501a7ba6ffcd"
e = call("/api/evidence/" + source, method="GET")
quote = "Lead Stories removed the panels that include transparent overlay effects from the above image."
assert quote in e["text"]
name = "Waterfall claim · originals, overlays and chronology"
boards = call("/api/boards", method="GET")
old = next((b for b in boards if b["name"] == name), None)
if old:
    raise SystemExit("Board already exists; preserving review arrangement")
note = call(
    "/api/annotations",
    {
        "title": "HYPOTHESIS REVIEW · a hidden pre-event image is not established",
        "kind": "hypothesis",
        "text": "The acquired artwork is a publisher-hosted copy, not an independently authenticated 2021 archive. The four-panel image contains progressive overlays according to the acquired secondary fact-check. Geometric image matches show shared visual material, not prediction or intent. No independent historical capture of the account header or original alleged prediction post is acquired here. The Time Machine Organisation source concerns cultural-heritage digitisation. Keep coincidence, editing, retrospective selection and historical attribution open. Gematria sums and readable decoder output do not establish foreknowledge. See saved prediction-audit records and exact original files.",
        "citations": [
            {
                "id": source,
                "quote": quote,
                "location": "Extracted fact-check text; paragraph describing overlay panel removal",
            }
        ],
    },
)
b = call("/api/boards", {"name": name})
nodes = []
ids = [
    ("art", "EV-6a350b477547", 30, 50),
    ("composite", "EV-0303ca000ce9", 410, 70),
    ("factcheck", source, 790, 70),
    ("heritage", "EV-9eb4054cad17", 790, 570),
    ("review", note["id"], 400, 570),
]
for nid, eid, x, y in ids:
    nodes.append(
        {
            "id": nid,
            "type": "evidence",
            "position": {"x": x, "y": y},
            "data": {"evidenceId": eid},
        }
    )
edges = []
for target, claim in [
    (
        "art",
        "The secondary fact-check identifies this publisher-hosted artwork copy as Eternal Waterfall; the artwork date is reported, not independently certified here.",
    ),
    (
        "composite",
        "The secondary fact-check describes transparent overlay panels in the acquired composite; this is source-attributed counterevidence to the hidden-image claim.",
    ),
]:
    edges.append(
        {
            "id": "source-" + target,
            "source": "factcheck",
            "target": target,
            "type": "smoothstep",
            "label": "Source-attributed analysis · review required",
            "data": {
                "state": "ALLEGED",
                "claim": claim,
                "confidence": "Secondary-source interpretation; original and independently archived timestamps require review",
                "method": "Exact acquired fact-check quotation and separately preserved JPEG comparison",
                "reason": "The source discusses the actual acquired visual artefacts. No prediction or identity edge is inferred.",
                "evidence": [
                    {
                        "id": source,
                        "quote": quote,
                        "location": "Extracted article paragraph",
                    }
                ],
                "contradictions": [
                    "No independently dated original historical header acquired"
                ],
            },
        }
    )
edges.append(
    {
        "id": "review-composite",
        "source": "review",
        "target": "composite",
        "type": "smoothstep",
        "label": "Tests hidden-image hypothesis · unverified",
        "data": {
            "state": "HYPOTHESIS",
            "claim": "Could the artwork contain intentional pre-event content? This remains unestablished.",
            "confidence": "No affirmative evidentiary conclusion",
            "method": "Competing explanations; source and chronology audit",
            "reason": "Preserve the allegation alongside counterevidence",
            "evidence": [],
            "contradictions": [source],
        },
    }
)
call("/api/boards/" + b["id"], {"nodes": nodes, "edges": edges}, "PUT")
(ROOT / "artifacts/waterfall-board-v11.json").write_text(
    json.dumps(
        {
            "board": b,
            "review_note_id": note["id"],
            "sources": [r[1] for r in ids],
            "nodes": nodes,
            "edges": edges,
        },
        indent=2,
    )
)
print(b)

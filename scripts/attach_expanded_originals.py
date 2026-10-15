"""Attach newly acquired primary records with literal source-backed document relationships."""

import json
import sqlite3
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=60, trust_env=False)
db = sqlite3.connect(ROOT / "data/case.db")
db.row_factory = sqlite3.Row


def quote(eid, start, length=500):
    """Select literal preserved source characters for a document relationship."""
    row = db.execute("SELECT text FROM evidence WHERE id=?", (eid,)).fetchone()
    a = row["text"].index(start)
    return {
        "id": eid,
        "quote": row["text"][a : a + length],
        "location": f"Indexed characters starting {a}",
    }


def save(name, ids, edges):
    """Create or update a specifically named case board without duplicating cards."""
    boards = c.get("/api/boards").json()
    existing = next((b for b in boards if b["name"] == name), None)
    if existing:
        bid = existing["id"]
    else:
        r = c.post("/api/boards", json={"name": name})
        r.raise_for_status()
        bid = r.json()["id"]
    nodes = [
        {
            "id": eid,
            "type": "evidence",
            "position": {"x": (i % 3) * 400, "y": (i // 3) * 480},
            "data": {"evidenceId": eid},
        }
        for i, eid in enumerate(ids)
    ]
    r = c.put("/api/boards/" + bid, json={"nodes": nodes, "edges": edges})
    r.raise_for_status()
    return bid


def edge(id, source, target, claim, proof, method):
    """Keep the asserted relationship at the document level, not a guilt or identity inference."""
    return {
        "id": id,
        "source": source,
        "target": target,
        "type": "smoothstep",
        "label": "Source-backed document relationship",
        "data": {
            "state": "DOCUMENTED",
            "claim": claim,
            "evidence": proof,
            "method": method,
            "reason": "Exact passages read from acquired originals; source record and allegation are kept distinct.",
            "confidence": "SOURCE-SUPPORTED RECORD; NOT A CONVICTION OR CAUSAL FINDING",
            "contradictions": [],
        },
    }


legal = ["EV-b9bbec3555f4", "EV-515b67cc6c69", "EV-c6d4cfb2872e"]
le = [
    edge(
        "doj-announces-complaint",
        legal[0],
        legal[1],
        "The DOJ announcement reports complaint charges against Cole Tomas Allen. The preserved complaint lists the three charged offenses; this is not a conviction.",
        [
            quote(legal[0], "Allen\u00a0is charged\u00a0by"),
            quote(legal[1], "18 U.S.C. § 1751(c)", 450),
        ],
        "AI-assisted comparison of official announcement and original complaint",
    ),
    edge(
        "affidavit-supports-complaint",
        legal[2],
        legal[1],
        "The acquired affidavit states that it supports a criminal complaint charging Cole Tomas Allen with the three listed offenses.",
        [quote(legal[2], "I make this affidavit in support", 480)],
        "Exact original affidavit introduction",
    ),
]
eu = ["EV-fe5e7358c427", "EV-e099a6052a61"]
ee = [
    edge(
        "cordis-defines-project",
        eu[0],
        eu[1],
        "The European Commission’s CORDIS record describes Time Machine as historical archive digitisation and identifies EPFL as coordinator.",
        [
            quote(eu[0], "Technology brings history to life", 550),
            quote(
                eu[0], "Coordinated by\nECOLE POLYTECHNIQUE FEDERALE DE LAUSANNE", 100
            ),
        ],
        "Exact official CORDIS project description and coordinator fields",
    )
]
legal_board = save(
    "Court records · DOJ complaint, affidavit and charge allegations", legal, le
)
eu_board = save("EU Time Machine · official historical digitisation records", eu, ee)
main = c.get("/api/boards/looking-glass").json()
nodes = main["nodes"]
edges = main["edges"]
x = max((n["position"]["x"] for n in nodes), default=0) + 440
for i, eid in enumerate(legal + eu[:1]):
    nid = "expanded-" + eid
    if not any(n["id"] == nid for n in nodes):
        nodes.append(
            {
                "id": nid,
                "type": "evidence",
                "position": {"x": x + (i % 2) * 400, "y": (i // 2) * 480},
                "data": {"evidenceId": eid},
            }
        )
for item in le:
    e = {
        **item,
        "id": "expanded-" + item["id"],
        "source": "expanded-" + item["source"],
        "target": "expanded-" + item["target"],
    }
    if not any(old["id"] == e["id"] for old in edges):
        edges.append(e)
r = c.put("/api/boards/looking-glass", json={"nodes": nodes, "edges": edges})
r.raise_for_status()
(ROOT / "artifacts/expanded-originals-board.json").write_text(
    json.dumps(
        {
            "legal_board": legal_board,
            "eu_project_board": eu_board,
            "main_board_cards": len(nodes),
            "actual_primary_records": legal + eu,
        },
        indent=2,
    )
)
print("Original records attached to main board and specific court/EU boards")

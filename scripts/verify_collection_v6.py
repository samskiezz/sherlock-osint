"""Real-vault proof of collection, source citations, method execution and secret-safe crypto."""

import hashlib, json, os, sqlite3
from pathlib import Path
import httpx

root = Path(__file__).resolve().parents[1]
c = httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=90)
evidence = c.get("/api/evidence").json()
magazine = next(
    e
    for e in evidence
    if e["fileUrl"]
    and e["mime"] == "application/pdf"
    and "Caltech Engineering and Science Summer 2016" in e["title"]
)
page = next(p for p in magazine["metadata"]["pages"] if "Cole Allen" in p["text"])
start = page["text"].index("and Cole Allen")
quote = page["text"][
    start : page["text"].index("prize for most points scored.", start)
    + len("prize for most points scored.")
]
assert page["page"] == 11 and c.get(magazine["fileUrl"]).content.startswith(b"%PDF")
board_name = "Caltech robotics · named primary record"
boards = c.get("/api/boards").json()
board = next((b for b in boards if b["name"] == board_name), None)
if not board:
    board = c.post("/api/boards", json={"name": board_name}).json()
    person = c.post(
        "/api/annotations",
        json={
            "title": "Cole Allen · name in 2016 Caltech caption",
            "kind": "person",
            "text": "The primary caption prints this name as a robotics team member. Identity resolution with people named elsewhere remains unresolved. This is a sourced secondary transcription, not an original portrait.",
            "citations": [{"id": magazine["id"], "page": 11, "quote": quote}],
        },
    ).json()
    photo = next(e for e in evidence if e["id"] == "EV-cbb53ca7395d")
    layout = {
        "nodes": [
            {
                "id": "caption-person",
                "type": "evidence",
                "position": {"x": 90, "y": 130},
                "data": {"evidenceId": person["id"]},
            },
            {
                "id": "primary-magazine",
                "type": "evidence",
                "position": {"x": 650, "y": 150},
                "data": {"evidenceId": magazine["id"]},
            },
            {
                "id": "context-team-photo",
                "type": "evidence",
                "position": {"x": 80, "y": 510},
                "data": {"evidenceId": photo["id"]},
            },
        ],
        "edges": [
            {
                "id": "primary-caption-name",
                "source": "caption-person",
                "target": "primary-magazine",
                "label": "Name printed in robotics caption · sourced",
                "data": {
                    "state": "DOCUMENTED",
                    "relationship": "Named in caption",
                    "claim": "The primary magazine caption includes the name Cole Allen. Identity resolution beyond this record remains unresolved.",
                    "evidence": [{"id": magazine["id"], "page": 11, "quote": quote}],
                    "confidence": "SOURCE-SUPPORTED NAME TRANSCRIPTION",
                    "method": "Exact source passage, reviewed in acquired PDF",
                },
            }
        ],
    }
    r = c.put("/api/boards/" + board["id"], json=layout)
    r.raise_for_status()
patents = c.get("/api/patents").json()["records"]
assert any("US:20100266442:A1" in p["data"]["publication_number"] for p in patents)
source = next(
    e
    for e in evidence
    if e["id"]
    == next(
        p["evidence_id"]
        for p in patents
        if "US:20100266442:A1" in p["data"]["publication_number"]
    )
)
claim = source["metadata"]["patent"]["claims"][0]
citation = "2010-10-21"
assert citation in source["text"]
analysis = c.post(
    "/api/tradecraft/run",
    json={
        "method": "ach",
        "inputs": {
            "hypotheses": [
                "Source labels this publication date 2010",
                "Source labels this publication date 2004",
            ],
            "matrix": [
                {
                    "evidence_id": source["id"],
                    "ratings": [1, -1],
                    "dependency_group": source["id"],
                    "explanation": "Illustrative human ratings from the displayed publication-date field, not a probability or authenticity finding.",
                }
            ],
        },
        "citations": [{"evidence_id": source["id"], "quote": citation}],
        "notes": "Catalogue legal status remains provisional; publication dates do not prove a modification date or experimental deployment.",
        "authorisation": "Legally accessible public patent records.",
    },
)
analysis.raise_for_status()
pinned = c.post(
    "/api/tradecraft/records/" + analysis.json()["id"] + "/pin",
    json={"board_id": board["id"]},
)
pinned.raise_for_status()
assert pinned.json()["state"] == "HYPOTHESIS"
key = os.urandom(32).hex()
crypto = c.post(
    "/api/crypto/run",
    json={
        "algorithm": "aes_gcm",
        "operation": "encrypt",
        "key_hex": key,
        "input": "Owned Looking Glass laboratory fixture",
        "encoding": "utf8",
        "authorisation": "Owned local laboratory test data",
    },
)
crypto.raise_for_status()
enc = crypto.json()
plain = c.post(
    "/api/crypto/run",
    json={
        "algorithm": "aes_gcm",
        "operation": "decrypt",
        "key_hex": key,
        "input": enc["output_base64"],
        "encoding": "base64",
        "nonce_hex": enc["nonce_hex"],
        "authorisation": "Owned local laboratory test data",
    },
)
plain.raise_for_status()
assert plain.json()["output_text"] == "Owned Looking Glass laboratory fixture"
assert key not in json.dumps(c.get("/api/crypto").json())
manifest = c.get("/api/vault/manifest").json()
assert not manifest["missing_original_ids"]
assert all(e.get("hash_matches") for e in manifest["records"] if e["file_exists"])
registry = c.get("/api/tradecraft").json()
snapshot = c.get("/api/vault/database")
snapshot.raise_for_status()
exported = root / "artifacts/looking-glass-database-snapshot-v6.sqlite"
exported.write_bytes(snapshot.content)
with sqlite3.connect(exported) as db:
    assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
proof = {
    "url": "http://127.0.0.1:8000",
    "database": manifest["database_path"],
    "original_files": manifest["original_files"],
    "original_bytes": manifest["original_bytes"],
    "all_original_hashes_verified": True,
    "patent_records": len(patents),
    "methods": len(registry["methods"]),
    "method_families": sum(
        m["classification"] == "TECHNIQUE FAMILY" for m in registry["methods"]
    ),
    "unimplemented_method_entries": sum(
        m["implementation"] == "NOT IMPLEMENTED" for m in registry["methods"]
    ),
    "caltech_magazine": {
        k: magazine[k] for k in ["id", "title", "sha256", "size", "url"]
    },
    "caption_pdf_page": page["page"],
    "caption_quote": quote,
    "source_board": board["id"],
    "provisional_analysis_id": analysis.json()["id"],
    "analysis_pin": pinned.json(),
    "aes_gcm_round_trip": True,
    "crypto_key_not_persisted": True,
    "photo_originals": [
        {
            "id": e["id"],
            "title": e["title"],
            "sha256": e["sha256"],
            "size": e["size"],
            "url": e["url"],
        }
        for e in evidence
        if e["mime"].startswith("image/") and e["fileUrl"]
    ],
    "campaigns": [
        {k: r[k] for k in ["id", "name", "enabled", "next_run", "settings"]}
        for r in c.get("/api/research").json()["campaigns"]
    ],
    "tor": manifest["tor"],
    "heartbeats": manifest["heartbeats"],
}
(root / "artifacts/collection-proof-v6.json").write_text(json.dumps(proof, indent=2))
print(
    json.dumps(
        {
            k: proof[k]
            for k in [
                "original_files",
                "original_bytes",
                "patent_records",
                "methods",
                "unimplemented_method_entries",
                "aes_gcm_round_trip",
                "all_original_hashes_verified",
            ]
        }
    )
)

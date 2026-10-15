"""Organise acquired originals without inventing biographical relationships."""

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
import httpx

root = Path(__file__).resolve().parents[1]
c = httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=20)
es = c.get("/api/evidence").json()
boards = c.get("/api/boards").json()
nasa_source = next(
    e for e in es if e["title"] == "NASA discovery response · superalloy"
)
archive_source = next(
    e for e in es if e["title"].startswith("ARCHIVE discovery response")
)
papers = [
    e
    for e in es
    if e["mime"] == "application/pdf" and urlparse(e["url"]).hostname == "ntrs.nasa.gov"
]
archives = sorted(
    [e for e in es if e["metadata"].get("source_class") == "HISTORICAL ARCHIVE"],
    key=lambda e: e["metadata"]["archive_capture_date"],
)


def organise(name, source, files, mode):
    b = (
        next((b for b in boards if b["name"] == name), None)
        or c.post("/api/boards", json={"name": name}).json()
    )
    previous = c.get("/api/boards/" + b["id"]).json()
    positions = {n["id"]: n["position"] for n in previous["nodes"]}
    nodes = [
        {
            "id": source["id"],
            "type": "evidence",
            "position": positions.get(source["id"], {"x": 440, "y": 0}),
            "data": {"evidenceId": source["id"]},
        }
    ]
    edges = []
    for i, e in enumerate(files):
        nodes.append(
            {
                "id": e["id"],
                "type": "evidence",
                "position": positions.get(
                    e["id"], {"x": (i % 3) * 350, "y": 400 + (i // 3) * 410}
                ),
                "data": {"evidenceId": e["id"]},
            }
        )
        quote = (
            urlparse(e["url"]).path
            if mode == "nasa"
            else e["url"].split("/web/")[1][:14]
        )
        assert quote in source["text"], (e["id"], quote)
        edges.append(
            {
                "id": "catalogue-" + e["id"],
                "source": source["id"],
                "target": e["id"],
                "label": "Lists public PDF download"
                if mode == "nasa"
                else "Records historical capture",
                "data": {
                    "state": "DOCUMENTED",
                    "claim": "The preserved source catalogue lists this exact download path."
                    if mode == "nasa"
                    else "The preserved Internet Archive index records this capture timestamp for the Steam URL. This is not the original creation date.",
                    "evidence": [
                        {
                            "id": source["id"],
                            "quote": quote,
                            "location": "Preserved public catalogue response",
                        }
                    ],
                    "method": "Literal public catalogue URL/timestamp match; tool-generated source link",
                    "proposed_by": "Acquisition organiser",
                    "confidence": "Source-supported record link",
                },
            }
        )
    r = c.put("/api/boards/" + b["id"], json={"nodes": nodes, "edges": edges})
    r.raise_for_status()
    return {
        "id": b["id"],
        "name": name,
        "originals": len(nodes),
        "documented_catalogue_links": len(edges),
    }


result = {
    "boards": [
        organise(
            "NASA materials literature · scientific context, not team evidence",
            nasa_source,
            papers,
            "nasa",
        ),
        organise(
            "Bohrdom · preserved historical Steam captures",
            archive_source,
            archives,
            "archive",
        ),
    ],
    "verified_originals": [],
}
for e in es:
    if e["fileUrl"]:
        path = root / "data/originals" / e["sha256"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == e["sha256"]
        result["verified_originals"].append(
            {
                "id": e["id"],
                "title": e["title"],
                "source_url": e["url"],
                "bytes": path.stat().st_size,
                "sha256": actual,
                "read_only": not bool(path.stat().st_mode & 0o222),
            }
        )
if not any(
    x["left_id"] == archives[0]["id"] and x["right_id"] == archives[-1]["id"]
    for x in c.get("/api/comparisons").json()
):
    r = c.post(
        "/api/comparisons",
        json={"left_id": archives[0]["id"], "right_id": archives[-1]["id"]},
    )
    r.raise_for_status()
    result["historical_comparison"] = r.json()
else:
    result["historical_comparison"] = next(
        x
        for x in c.get("/api/comparisons").json()
        if x["left_id"] == archives[0]["id"] and x["right_id"] == archives[-1]["id"]
    )
result["automatic_audits"] = c.get("/api/watches").json()["analyses"]
(root / "artifacts/release-v3-evidence.json").write_text(json.dumps(result, indent=2))
print(
    json.dumps(
        {
            "boards": result["boards"],
            "verified_originals": len(result["verified_originals"]),
            "archived_versions": len(archives),
            "nasa_pdfs": len(papers),
            "audits_completed": sum(
                x["status"] == "COMPLETE" for x in result["automatic_audits"]
            ),
        }
    )
)

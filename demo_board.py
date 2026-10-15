"""Arrange acquired originals and explicitly separate the imported dossier leads."""

import httpx, json

c = httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=30)
evidence = c.get("/api/evidence").json()
old = c.get("/api/boards/looking-glass").json()
if not any(
    b["name"] == "Imported dossier · unverified leads"
    for b in c.get("/api/boards").json()
):
    b = c.post(
        "/api/boards", json={"name": "Imported dossier · unverified leads"}
    ).json()
    c.put(
        "/api/boards/" + b["id"], json={"nodes": old["nodes"], "edges": old["edges"]}
    ).raise_for_status()


def find(part):
    return next(e for e in evidence if part in e["title"])


photo = find("team photograph")
paper = find("original patent PDF")
art = find("official Steam artwork")
report = find("Tridroid Cup original")
steam = find("public application metadata")
nodes = []
for nid, eid, x, y in [
    ("photo", photo["id"], 40, 35),
    ("report", report["id"], 425, 35),
    ("paper", paper["id"], 810, 35),
    ("art", art["id"], 40, 440),
    ("steam", steam["id"], 425, 440),
    ("quantum", "NOTE-quantum", 810, 440),
    ("note", "NOTE-notes", 1170, 50),
]:
    nodes.append(
        {
            "id": nid,
            "type": "evidence",
            "position": {"x": x, "y": y},
            "data": {"evidenceId": eid},
        }
    )
edges = [
    {
        "id": "source-photo",
        "source": "report",
        "target": "photo",
        "type": "smoothstep",
        "label": "Captioned in source · documented",
        "data": {
            "claim": "The Caltech report captions this linked image “Members of team Blitzkrieg Bots.” Individual identities in the photograph are not established here.",
            "state": "DOCUMENTED",
            "confidence": "Source-supported; identities not resolved",
            "method": "Human review of acquired institutional webpage and linked photograph",
            "reason": "Photograph URL is linked from the original Caltech report; the report gives the quoted caption.",
            "evidence": [
                {
                    "id": report["id"],
                    "quote": "Members of team Blitzkrieg Bots.",
                    "location": "Image gallery caption; original HTML contains linked photo URL",
                }
            ],
            "contradictions": [],
        },
    },
    {
        "id": "steam-art",
        "source": "steam",
        "target": "art",
        "type": "smoothstep",
        "label": "Links official artwork · documented",
        "data": {
            "claim": "The acquired Steam API response contains the acquired artwork URL. This is not evidence of game executable modification.",
            "state": "DOCUMENTED",
            "confidence": "Source-supported link",
            "method": "Static inspection of original Steam API JSON",
            "reason": "header_image property points to this exact acquired image URL",
            "evidence": [
                {
                    "id": steam["id"],
                    "quote": art["url"],
                    "location": "JSON → 945530 → data → header_image",
                }
            ],
            "contradictions": [],
        },
    },
    {
        "id": "question-materials",
        "source": "quantum",
        "target": "paper",
        "type": "smoothstep",
        "label": "Technical research question · hypothesis",
        "data": {
            "claim": "Does this alloy patent support any unconventional propulsion claim? The acquired patent alone does not establish that proposition.",
            "state": "HYPOTHESIS",
            "confidence": "Unassessed",
            "method": "Human investigative question",
            "reason": "Separate technical source from speculative interpretation",
            "evidence": [],
            "contradictions": [],
        },
    },
]
r = c.put("/api/boards/looking-glass", json={"nodes": nodes, "edges": edges})
r.raise_for_status()
print("Arranged", len(nodes), "cards and", len(edges), "inspectable relationships")
# Inventor identities are limited to the names in the acquired patent; no later identity merge is asserted.
name = "Patent provenance · inventors & original"
existing = next((b for b in c.get("/api/boards").json() if b["name"] == name), None)
b = existing or c.post("/api/boards", json={"name": name}).json()
people = []
for title, quote, x in [
    ("Monica A. Jacinto · patent inventor", "Inventors: Monica A. Jacinto", 0),
    ("Dallis Ann Hardwick · patent inventor", "Dallis Ann Hardwick", 850),
]:
    found = next(
        (e for e in c.get("/api/evidence").json() if e["title"] == title), None
    )
    if not found:
        r = c.post(
            "/api/annotations",
            json={
                "title": title,
                "kind": "person",
                "text": "Name transcribed from the inventor listing on page 1 of the acquired 2003 patent. No identity merge, employer, death, disappearance or research-team membership is asserted.",
                "citations": [
                    {
                        "id": paper["id"],
                        "quote": quote,
                        "location": "Patent PDF, page 1, inventor listing",
                    }
                ],
            },
        )
        r.raise_for_status()
        found = r.json()
    people.append((found, x, quote))
n = [
    {
        "id": "patent-pdf",
        "type": "evidence",
        "position": {"x": 425, "y": 50},
        "data": {"evidenceId": paper["id"]},
    }
]
links = []
for i, (person, x, quote) in enumerate(people):
    nid = "inventor-" + str(i)
    n.append(
        {
            "id": nid,
            "type": "evidence",
            "position": {"x": x, "y": 70},
            "data": {"evidenceId": person["id"]},
        }
    )
    links.append(
        {
            "id": "invented-" + str(i),
            "source": nid,
            "target": "patent-pdf",
            "label": "Listed inventor · documented",
            "type": "smoothstep",
            "data": {
                "claim": person["title"].split(" · ")[0]
                + " is listed as an inventor on US20030053926A1.",
                "state": "DOCUMENTED",
                "method": "Human transcription of acquired patent page 1",
                "confidence": "Source-supported inventor name; no external identity resolution",
                "reason": "Name appears in the actual patent inventor listing",
                "evidence": [
                    {"id": paper["id"], "quote": quote, "location": "Patent PDF page 1"}
                ],
                "contradictions": [],
            },
        }
    )
r = c.put("/api/boards/" + b["id"], json={"nodes": n, "edges": links})
r.raise_for_status()
print("Inventor-to-original-paper acceptance path created")

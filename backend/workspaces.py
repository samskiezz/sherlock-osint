"""Source-linked graph analytics, chronology, public places and human claim review.

SQLite is the canonical local case store. Graph algorithms operate on explicit
board edges; no inferred identity or co-occurrence edge is promoted to fact.
"""

import json
import difflib
from collections import defaultdict, deque
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

from fastapi import HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field


class Citation(BaseModel):
    id: str
    quote: str = Field(min_length=8, max_length=12000)
    location: str = Field(default="", max_length=200)


class ClaimInput(BaseModel):
    board_id: str
    source: str
    target: str
    relationship: str = Field(min_length=1, max_length=100)
    claim: str = Field(min_length=8, max_length=4000)
    supporting: list[Citation] = Field(default_factory=list, max_length=20)
    contradicting: list[Citation] = Field(default_factory=list, max_length=20)
    origin: str = "Human proposal"


class ReviewInput(BaseModel):
    decision: str
    reason: str = Field(min_length=8, max_length=2000)


class EventInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start: str
    end: str | None = None
    date_type: str
    evidence_id: str
    quote: str = Field(min_length=8, max_length=12000)
    layer: str = Field(default="Source chronology", max_length=100)


class PlaceInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-85, le=85)
    evidence_id: str
    quote: str = Field(min_length=8, max_length=12000)
    precision: str = "Approximate institution location"
    category: str = "Public institution"


class ComparisonInput(BaseModel):
    left_id: str
    right_id: str


def install(core):
    with core.db() as c:
        c.executescript("""
CREATE TABLE IF NOT EXISTS claims(id TEXT PRIMARY KEY,created TEXT,updated TEXT,status TEXT,data TEXT,review TEXT);
CREATE TABLE IF NOT EXISTS chronology(id TEXT PRIMARY KEY,created TEXT,data TEXT);
CREATE TABLE IF NOT EXISTS places(id TEXT PRIMARY KEY,created TEXT,data TEXT);
CREATE TABLE IF NOT EXISTS comparisons(id TEXT PRIMARY KEY,created TEXT,data TEXT);
""")

    def verify(citations):
        canonical = []
        for citation in citations:
            source = core.get_evidence(citation.id)
            valid, reason = core.investigator["integrity"](source)
            if not valid:
                raise HTTPException(422, reason)
            offset = source["text"].find(citation.quote)
            if offset < 0:
                raise HTTPException(422, "Exact quote absent from attested source text")
            # Compute location from extraction, not the submitter's assertion.
            page = next(
                (
                    p["page"]
                    for p in source["metadata"].get("pages", [])
                    if citation.quote in p.get("text", "")
                ),
                None,
            )
            canonical.append(
                {
                    "id": citation.id,
                    "quote": citation.quote,
                    "location": f"Page {page}"
                    if page
                    else f"Indexed characters {offset}–{offset + len(citation.quote)}",
                    "sha256": source["sha256"],
                    "proposed_location": citation.location,
                }
            )
        return canonical

    def graph(board_id, documented_only=False):
        board = core.board(board_id)
        result = {"nodes": [], "edges": [], "board_id": board_id}
        node_map = {}
        for n in board["nodes"]:
            eid = n.get("data", {}).get("evidenceId")
            try:
                evidence = core.get_evidence(eid)
            except HTTPException:
                continue
            node_map[n["id"]] = {
                "id": n["id"],
                "evidence_id": eid,
                "title": evidence["title"],
                "kind": evidence["kind"],
                "status": evidence["status"],
                "original": bool(evidence["fileUrl"]),
                "position": n.get("position", {}),
            }
        for edge in board["edges"]:
            if edge["source"] not in node_map or edge["target"] not in node_map:
                continue
            data = edge.get("data", {})
            factual = data.get("state") in ("DOCUMENTED", "CORROBORATED")
            citation_ok = False
            problem = None
            if factual:
                try:
                    citations = [Citation(**x) for x in data.get("evidence", [])]
                    if not citations:
                        raise ValueError("No citations")
                    verify(citations)
                    citation_ok = True
                except Exception as e:
                    problem = str(e)
            if documented_only and not citation_ok:
                continue
            result["edges"].append(
                {**edge, "citation_verified": citation_ok, "integrity_problem": problem}
            )
        result["nodes"] = list(node_map.values())
        adj = {n: set() for n in node_map}
        for e in result["edges"]:
            adj[e["source"]].add(e["target"])
            adj[e["target"]].add(e["source"])
        seen, components = set(), []
        for start in adj:
            if start in seen:
                continue
            stack, group = [start], []
            seen.add(start)
            while stack:
                node = stack.pop()
                group.append(node)
                for other in sorted(adj[node]):
                    if other not in seen:
                        seen.add(other)
                        stack.append(other)
            components.append(group)
        result["components"] = sorted(components, key=len, reverse=True)
        result["degree"] = {n: len(v) for n, v in adj.items()}
        result["density"] = (
            2
            * len(
                {
                    frozenset((e["source"], e["target"]))
                    for e in result["edges"]
                    if e["source"] != e["target"]
                }
            )
            / (len(adj) * (len(adj) - 1))
            if len(adj) > 1
            else 0
        )
        result["documented_only"] = documented_only
        result["traversal"] = (
            "Undirected relationship traversal; no causal or identity implication"
        )
        return result

    @core.app.get("/api/graph/{board_id}")
    def graph_api(
        board_id: str,
        documented_only: bool = False,
        source: str = "",
        target: str = "",
        hops: int = 1,
    ):
        g = graph(board_id, documented_only)
        adj = defaultdict(list)
        for e in g["edges"]:
            adj[e["source"]].append((e["target"], e["id"]))
            adj[e["target"]].append((e["source"], e["id"]))
        node_ids = {n["id"] for n in g["nodes"]}
        if source and source not in node_ids or target and target not in node_ids:
            raise HTTPException(404, "Graph node absent")
        if source and target:
            queue, parent = deque([source]), {source: None}
            while queue:
                current = queue.popleft()
                if current == target:
                    break
                for other, eid in adj[current]:
                    if other not in parent:
                        parent[other] = (current, eid)
                        queue.append(other)
            path, edge_path = [], []
            if target in parent:
                current = target
                while current is not None:
                    path.append(current)
                    step = parent[current]
                    if step is None:
                        break
                    current, eid = step
                    edge_path.append(eid)
            g["path"] = list(reversed(path))
            g["path_edges"] = list(reversed(edge_path))
        elif source:
            visited, frontier = {source}, {source}
            for _ in range(max(1, min(hops, 5))):
                frontier = {n for x in frontier for n, _ in adj[x]} - visited
                visited.update(frontier)
            g["neighbourhood"] = sorted(visited)
        return g

    def claim_value(row):
        return {
            **row,
            "data": json.loads(row["data"]),
            "review": json.loads(row["review"]) if row["review"] else None,
        }

    @core.app.get("/api/claims")
    def claims():
        return [
            claim_value(r)
            for r in core.rows("SELECT * FROM claims ORDER BY created DESC")
        ]

    @core.app.post("/api/claims")
    def propose(value: ClaimInput):
        b = core.board(value.board_id)
        ids = {n["id"] for n in b["nodes"]}
        if (
            value.source not in ids
            or value.target not in ids
            or value.source == value.target
        ):
            raise HTTPException(422, "Choose distinct existing board nodes")
        data = value.model_dump()
        data["supporting"] = verify(value.supporting)
        data["contradicting"] = verify(value.contradicting)
        data["origin"] = (
            "Human proposal"  # AI proposals use investigator tasks, not this endpoint.
        )
        cid = core.uid("CLAIM")
        core.execute(
            "INSERT INTO claims VALUES(?,?,?,?,?,?)",
            (cid, core.now(), core.now(), "REVIEW REQUIRED", json.dumps(data), None),
        )
        core.log("claim_proposed", {"id": cid, "board": value.board_id})
        return claim_value(core.rows("SELECT * FROM claims WHERE id=?", (cid,))[0])

    @core.app.post("/api/claims/{claim_id}/review")
    def review(claim_id: str, value: ReviewInput):
        if value.decision not in ("ACCEPT", "REJECT", "DISPUTE"):
            raise HTTPException(422, "Decision must be ACCEPT, REJECT or DISPUTE")
        with core.lock, core.db() as c:
            row = c.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Claim absent")
            data = json.loads(row["data"])
            support = verify([Citation(**x) for x in data["supporting"]])
            contrary = verify([Citation(**x) for x in data["contradicting"]])
            if value.decision == "ACCEPT" and (not support or contrary):
                raise HTTPException(
                    422,
                    "Acceptance requires original support and resolution of contradicting evidence",
                )
            if value.decision == "DISPUTE" and not contrary:
                raise HTTPException(
                    422, "Disputed claims require original contradicting evidence"
                )
            state = {
                "ACCEPT": "DOCUMENTED",
                "REJECT": "REJECTED",
                "DISPUTE": "CONTRADICTED",
            }[value.decision]
            decision = {
                **value.model_dump(),
                "reviewer": "Local human investigator",
                "time": core.now(),
            }
            # Only accepted/disputed claims become graph edges. Rejection removes its prior edge.
            board_row = c.execute(
                "SELECT data FROM boards WHERE id=?", (data["board_id"],)
            ).fetchone()
            if not board_row:
                raise HTTPException(404, "Board absent")
            board = json.loads(board_row["data"])
            node_ids = {n["id"] for n in board["nodes"]}
            if data["source"] not in node_ids or data["target"] not in node_ids:
                raise HTTPException(
                    409, "Claim endpoints were removed; restore them before review"
                )
            board["edges"] = [e for e in board["edges"] if e["id"] != claim_id]
            if value.decision != "REJECT":
                board["edges"].append(
                    {
                        "id": claim_id,
                        "source": data["source"],
                        "target": data["target"],
                        "label": data["relationship"],
                        "data": {
                            "state": state,
                            "claim": data["claim"],
                            "evidence": support,
                            "contradicting": contrary,
                            "method": "Human review of exact acquired passages",
                            "proposed_by": data["origin"],
                            "review": decision,
                            "confidence": "Source-supported; human reviewed"
                            if state == "DOCUMENTED"
                            else "Disputed",
                        },
                    }
                )
            c.execute(
                "UPDATE boards SET data=? WHERE id=?",
                (json.dumps(board), data["board_id"]),
            )
            c.execute(
                "UPDATE claims SET status=?,updated=?,review=? WHERE id=?",
                (state, core.now(), json.dumps(decision), claim_id),
            )
            from .audit_chain import append

            append(
                c,
                core.now(),
                "claim_reviewed",
                json.dumps({"id": claim_id, **decision}),
            )
        return claim_value(core.rows("SELECT * FROM claims WHERE id=?", (claim_id,))[0])

    def parse_date(value):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return (
                parsed.replace(tzinfo=timezone.utc)
                if parsed.tzinfo is None
                else parsed.astimezone(timezone.utc)
            )
        except ValueError:
            raise HTTPException(422, "Use an ISO date or UTC timestamp")

    @core.app.post("/api/chronology")
    def add_event(value: EventInput):
        if value.date_type not in (
            "Creation",
            "Publication",
            "Archive capture",
            "Modification",
            "Repository commit",
            "Catalogue indexing",
            "Event",
        ):
            raise HTTPException(422, "Select a distinct supported date type")
        start = parse_date(value.start)
        end = parse_date(value.end) if value.end else start
        if end < start:
            raise HTTPException(422, "Uncertainty interval ends before it starts")
        citations = verify([Citation(id=value.evidence_id, quote=value.quote)])
        date_tokens = set(__import__("re").findall(r"\b\d{4}\b", value.quote))
        if str(start.year) not in date_tokens:
            raise HTTPException(
                422,
                "Source passage must contain the proposed year; exact interpretation still requires human review",
            )
        eid = core.uid("EVENT")
        data = {
            **value.model_dump(),
            "id": eid,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "citations": citations,
            "status": "SOURCE-LINKED · HUMAN INTERPRETATION",
            "interpretation": "Date type and interval entered by investigator, not independently authenticated",
        }
        core.execute(
            "INSERT INTO chronology VALUES(?,?,?)", (eid, core.now(), json.dumps(data))
        )
        core.log("chronology_added", {"id": eid, "source": value.evidence_id})
        return data

    @core.app.get("/api/chronology")
    def chronology():
        events = [json.loads(r["data"]) for r in core.rows("SELECT * FROM chronology")]
        for e in core.rows(
            "SELECT id,title,created,sha256,metadata FROM evidence WHERE sha256 IS NOT NULL"
        ):
            metadata = json.loads(e["metadata"])
            events.append(
                {
                    "id": "retrieval-" + e["id"],
                    "title": e["title"],
                    "start": metadata.get("retrieved_utc", e["created"]),
                    "end": metadata.get("retrieved_utc", e["created"]),
                    "date_type": "Retrieval",
                    "evidence_id": e["id"],
                    "layer": "Acquisition",
                    "status": "RECORDED RETRIEVAL",
                    "citations": [],
                    "sha256": e["sha256"],
                }
            )
            if metadata.get("archive_capture_date"):
                stamp = metadata["archive_capture_date"]
                events.append(
                    {
                        "id": "archive-" + e["id"],
                        "title": e["title"],
                        "start": stamp,
                        "end": stamp,
                        "date_type": "Archive capture",
                        "evidence_id": e["id"],
                        "layer": "Historical Steam captures",
                        "status": "ARCHIVE REPLAY TIMESTAMP",
                        "citations": [],
                        "sha256": e["sha256"],
                        "interpretation": metadata.get(
                            "archive_date_interpretation",
                            "Archive capture is distinct from source creation",
                        ),
                    }
                )
        return sorted(events, key=lambda e: e["start"])

    @core.app.get("/api/comparisons")
    def comparisons():
        return [
            json.loads(r["data"])
            for r in core.rows("SELECT * FROM comparisons ORDER BY created DESC")
        ]

    @core.app.post("/api/comparisons")
    def compare(value: ComparisonInput):
        if value.left_id == value.right_id:
            raise HTTPException(422, "Select two distinct acquired records")
        sources = [core.get_evidence(eid) for eid in (value.left_id, value.right_id)]
        for source in sources:
            valid, reason = core.investigator["integrity"](source)
            if not valid:
                raise HTTPException(422, reason)
        left, right = sources
        lines = [s["text"].splitlines() for s in sources]
        truncated = any(len(x) > 2000 for x in lines)
        diff = list(
            difflib.unified_diff(
                lines[0][:2000],
                lines[1][:2000],
                fromfile=left["id"],
                tofile=right["id"],
                lineterm="",
            )
        )
        result = {
            "id": core.uid("COMPARE"),
            "created": core.now(),
            "left_id": left["id"],
            "right_id": right["id"],
            "original_hashes": [s["sha256"] for s in sources],
            "text_hashes": [
                s["metadata"]["derivative_hashes"]["text.txt"] for s in sources
            ],
            "capture_dates": [
                s["metadata"].get("archive_capture_date") for s in sources
            ],
            "method": "Python difflib unified line diff of attested extracted text; first 2,000 lines per record",
            "diff": diff[:500],
            "truncated": truncated or len(diff) > 500,
            "changed": left["text"] != right["text"],
            "interpretation": "Differences in preserved webpage text do not establish changes to a game binary, authorship or historical account ownership.",
        }
        core.execute(
            "INSERT INTO comparisons VALUES(?,?,?)",
            (result["id"], result["created"], json.dumps(result)),
        )
        core.log(
            "version_comparison_saved",
            {"id": result["id"], "sources": [value.left_id, value.right_id]},
        )
        return result

    @core.app.post("/api/places")
    def add_place(value: PlaceInput):
        if value.category not in (
            "Public institution",
            "Public event",
            "Historical place",
        ):
            raise HTTPException(
                422,
                "Only public institutions, events and historical places are supported",
            )
        citations = verify([Citation(id=value.evidence_id, quote=value.quote)])
        pid = core.uid("PLACE")
        data = {
            **value.model_dump(),
            "id": pid,
            "citations": citations,
            "status": "SOURCE-LINKED · APPROXIMATE",
            "coordinate_method": "Investigator-entered; source quote supports place association, coordinates not independently authenticated",
        }
        core.execute(
            "INSERT INTO places VALUES(?,?,?)", (pid, core.now(), json.dumps(data))
        )
        core.log("place_added", {"id": pid, "source": value.evidence_id})
        return data

    @core.app.get("/api/places")
    def places():
        return [json.loads(r["data"]) for r in core.rows("SELECT * FROM places")]

    @core.app.get("/api/graph/{board_id}/export/{fmt}")
    def export_graph(board_id: str, fmt: str, documented_only: bool = False):
        g = graph(board_id, documented_only)
        if fmt not in ("graphml", "gexf"):
            raise HTTPException(422, "Supported graph exports: graphml, gexf")
        if fmt == "graphml":
            ns = "http://graphml.graphdrawing.org/xmlns"
            root = ET.Element("graphml", xmlns=ns)
            for name in (
                "title",
                "evidence_id",
                "status",
                "claim",
                "citations",
                "state",
            ):
                ET.SubElement(
                    root,
                    "key",
                    {
                        "id": name,
                        "for": "all",
                        "attr.name": name,
                        "attr.type": "string",
                    },
                )
            graph_el = ET.SubElement(root, "graph", id=board_id, edgedefault="directed")
            for n in g["nodes"]:
                el = ET.SubElement(graph_el, "node", id=n["id"])
                for name in ("title", "evidence_id", "status"):
                    ET.SubElement(el, "data", key=name).text = n[name]
            for e in g["edges"]:
                el = ET.SubElement(
                    graph_el, "edge", id=e["id"], source=e["source"], target=e["target"]
                )
                for name, content in {
                    "claim": e.get("data", {}).get("claim", str(e.get("label", ""))),
                    "state": e.get("data", {}).get("state", "UNVERIFIED"),
                    "citations": json.dumps(e.get("data", {}).get("evidence", [])),
                }.items():
                    ET.SubElement(el, "data", key=name).text = content
        else:
            root = ET.Element("gexf", xmlns="http://gexf.net/1.3", version="1.3")
            graph_el = ET.SubElement(
                root, "graph", mode="static", defaultedgetype="directed"
            )
            attributes = ET.SubElement(graph_el, "attributes", {"class": "edge"})
            for name in ("state", "claim", "citations"):
                ET.SubElement(
                    attributes, "attribute", id=name, title=name, type="string"
                )
            ns = ET.SubElement(graph_el, "nodes")
            for n in g["nodes"]:
                ET.SubElement(ns, "node", id=n["id"], label=n["title"])
            es = ET.SubElement(graph_el, "edges")
            for e in g["edges"]:
                el = ET.SubElement(
                    es,
                    "edge",
                    id=e["id"],
                    source=e["source"],
                    target=e["target"],
                    label=str(e.get("label", "")),
                )
                values = ET.SubElement(el, "attvalues")
                for name, value in {
                    "state": e.get("data", {}).get("state", "UNVERIFIED"),
                    "claim": e.get("data", {}).get("claim", ""),
                    "citations": json.dumps(e.get("data", {}).get("evidence", [])),
                }.items():
                    ET.SubElement(values, "attvalue", {"for": name, "value": value})
        return Response(
            ET.tostring(root, encoding="utf-8", xml_declaration=True),
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{board_id}.{fmt}"'},
        )

    return {"graph": graph, "verify": verify}

"""Source-linked patent and publisher-image corpus; no inferred people identities."""

import json
import threading
from fastapi import HTTPException


def install(core):
    core.execute(
        "CREATE TABLE IF NOT EXISTS patent_records(evidence_id TEXT PRIMARY KEY,updated TEXT,data TEXT)"
    )
    core.execute(
        "CREATE TABLE IF NOT EXISTS media_leads(parent_evidence_id TEXT,url TEXT,created TEXT,data TEXT,PRIMARY KEY(parent_evidence_id,url))"
    )

    def index():
        from urllib.parse import urljoin

        for e in core.rows(
            "SELECT id,url,title,metadata,text FROM evidence WHERE status='ORIGINAL VERIFIED'"
        ):
            meta = json.loads(e["metadata"])
            if meta.get("patent"):
                data = {
                    **meta["patent"],
                    "evidence_id": e["id"],
                    "sha256": core.get_evidence(e["id"])["sha256"],
                    "source_url": e["url"],
                    "extraction_method": "Static DOM metadata in network-disabled processor",
                    "review_state": "REVIEW REQUIRED",
                    "demonstration_status": "PATENT DISCLOSURE ONLY",
                    "claims": meta["patent"].get("claims", []),
                }
                old = core.rows(
                    "SELECT data FROM patent_records WHERE evidence_id=?", (e["id"],)
                )
                if old and json.loads(old[0]["data"]) == data:
                    continue
                core.execute(
                    "INSERT INTO patent_records VALUES(?,?,?) ON CONFLICT(evidence_id) DO UPDATE SET updated=excluded.updated,data=excluded.data",
                    (e["id"], core.now(), json.dumps(data)),
                )
            if any(
                term in (e["title"] + " " + e["text"][:10000]).lower()
                for term in ("cole allen", "cole tomas allen")
            ):
                for lead in meta.get("media", []):
                    # A publisher preview is a lead, not a facial identification.
                    if lead.get("origin") != "publisher meta tag" and not any(
                        term in lead.get("caption", "").lower()
                        for term in ("cole allen", "cole tomas allen")
                    ):
                        continue
                    url = urljoin(e["url"], lead["href"])
                    try:
                        core.validate_url(url)
                    except ValueError:
                        continue
                    core.execute(
                        "INSERT OR IGNORE INTO media_leads VALUES(?,?,?,?)",
                        (
                            e["id"],
                            url,
                            core.now(),
                            json.dumps(
                                {
                                    **lead,
                                    "parent_title": e["title"],
                                    "subject_status": "UNVERIFIED ATTRIBUTION",
                                    "independent_original_required": True,
                                }
                            ),
                        ),
                    )

    @core.app.get("/api/patents")
    def listing():
        index()
        return {
            "records": [
                {**r, "data": json.loads(r["data"])}
                for r in core.rows("SELECT * FROM patent_records ORDER BY updated DESC")
            ],
            "warning": "Claims, priority dates, catalogue legal-status labels and cited documents are distinct from experimental demonstration and current legal status.",
        }

    @core.app.get("/api/photo-corpus")
    def photos():
        index()
        leads = []
        for r in core.rows("SELECT * FROM media_leads ORDER BY created DESC"):
            match = core.rows(
                "SELECT DISTINCT e.id,e.sha256,e.status FROM evidence e LEFT JOIN jobs j ON j.evidence_id=e.id WHERE (e.url=? OR j.url=?) AND e.sha256 IS NOT NULL AND e.mime LIKE 'image/%'",
                (r["url"], r["url"]),
            )
            leads.append(
                {
                    **r,
                    "data": json.loads(r["data"]),
                    "acquired": match[0] if match else None,
                }
            )
        return {
            "leads": leads,
            "images": [
                core.get_evidence(r["id"])
                for r in core.rows(
                    "SELECT id FROM evidence WHERE mime LIKE 'image/%' AND sha256 IS NOT NULL"
                )
            ],
            "coverage": "A growing public-source corpus, not every photograph that exists. Captions and publisher previews are attribution leads; no face matching or identity merge is performed.",
        }

    @core.app.post("/api/photo-corpus/queue")
    def queue(value: dict):
        from .app import Acquire

        records = core.rows(
            "SELECT * FROM media_leads WHERE parent_evidence_id=? AND url=?",
            (value.get("parent_evidence_id"), value.get("url")),
        )
        if not records:
            raise HTTPException(422, "Select a preserved publisher-linked image lead")
        lead = records[0]
        data = json.loads(lead["data"])
        result = core.queue(
            Acquire(
                url=lead["url"],
                title=("Unverified publisher photograph · " + data["parent_title"])[
                    :200
                ],
            )
        )
        core.log(
            "public_photo_lead_queued",
            {
                "parent": lead["parent_evidence_id"],
                "url": lead["url"],
                "job": result["id"],
            },
        )
        return result

    def loop():
        while not core.stopping.is_set():
            try:
                core.heartbeat("patent-media-index")
                index()
            except Exception as ex:
                core.log("patent_media_index_failed", {"reason": str(ex)[:500]})
            core.stopping.wait(30)

    @core.app.on_event("startup")
    def start():
        threading.Thread(target=loop, name="patent-media-index", daemon=True).start()

    return {"index": index}

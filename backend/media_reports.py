"""General image-review receipts, including negative results and bounded coverage."""

import hashlib
import json
from urllib.parse import urlparse


def build_report(reference, features, comparison, metadata):
    """Summarise measured diagnostics without converting anomalies into hidden messages."""
    diagnostics = metadata.get("image_forensics", {})
    panel = features.get("panel_analysis", {})
    leads = []
    for row in comparison.get("results", []):
        exact = row["original_sha256"] == reference["sha256"]
        geometric = row.get("ransac_inliers", 0) >= 12
        perceptual = row.get("hash_distances", {}).get("phash", 65) <= 8
        if exact or geometric or perceptual:
            leads.append(
                {
                    "evidence_id": row["evidence_id"],
                    "title": row["title"],
                    "kind": "EXACT_BYTES"
                    if exact
                    else "GEOMETRIC_REUSE_CANDIDATE"
                    if geometric
                    else "PERCEPTUAL_SIMILARITY_CANDIDATE",
                    "ransac_inliers": row.get("ransac_inliers", 0),
                    "phash_distance": row.get("hash_distances", {}).get("phash"),
                    "original_sha256": row["original_sha256"],
                }
            )
    overlay = panel.get("status") == "MIXTURE_SEQUENCE_DETECTED"
    return {
        "version": "0.13.0",
        "evidence_id": reference["id"],
        "title": reference["title"],
        "source_url": reference["url"],
        "source_domain": urlparse(reference["url"]).hostname or "Imported file",
        "original_sha256": reference["sha256"],
        "assessment": "REVIEW_LEADS"
        if leads or overlay
        else "NO_MATCH_IN_TESTED_CORPUS",
        "summary": (
            f"{len(leads)} similarity leads from {comparison['compared']} acquired references."
            if leads
            else f"No reuse lead from {comparison['compared']} acquired references. Technical image checks saved."
        )
        + (" A panel-composition candidate was also measured." if overlay else ""),
        "checks": [
            {"method": "Original and derivative integrity", "status": "VERIFIED"},
            {
                "method": "OCR",
                "status": "TEXT_EXTRACTED"
                if reference.get("text", "").strip()
                else "NO_TEXT_EXTRACTED",
            },
            {
                "method": "Perceptual / multiscale / ORB comparison",
                "status": "COMPLETE",
                "compared": comparison["compared"],
            },
            {
                "method": "Four-panel mixture test",
                "status": panel.get("status", "UNAVAILABLE"),
                "pairs_attempted": panel.get("pairs_attempted", 0),
            },
            {
                "method": "Channels, LSB and recompression residuals",
                "status": "INDICATORS_ONLY" if diagnostics else "UNAVAILABLE",
            },
        ],
        "similarity_leads": leads,
        "diagnostic_indicators": diagnostics.get("anomaly_indicators", []),
        "explanation_ids": comparison.get("explanation_ids", []),
        "coverage": {
            k: comparison.get(k)
            for k in (
                "compared",
                "unavailable",
                "corpus_limit",
                "corpus_truncated",
                "ranked_results_retained",
                "results_truncated",
                "scope",
            )
        },
        "comparison_id": comparison["id"],
        "limitations": "These bounded tests do not exhaust hidden-image methods. No match does not authenticate an image or exclude concealed content. Similarity and residual anomalies do not establish intent, identity or foreknowledge. Semantic reverse-image search across the internet is not configured.",
    }


def install(core):
    """Expose paginated persisted reports; the UI never launches an analysis."""
    core.execute(
        "CREATE TABLE IF NOT EXISTS media_reports(evidence_id TEXT PRIMARY KEY,updated TEXT,data TEXT)"
    )

    core.execute(
        "CREATE TABLE IF NOT EXISTS media_origins(id TEXT PRIMARY KEY,image_url TEXT,observed TEXT,data TEXT)"
    )
    core.execute(
        "CREATE INDEX IF NOT EXISTS media_origins_url ON media_origins(image_url)"
    )

    def register(image_url, context):
        """Preserve each distinct feed/post/page origin, keeping recurring observations idempotent."""
        encoded = json.dumps(context, sort_keys=True)
        key = hashlib.sha256((image_url + encoded).encode()).hexdigest()
        core.execute(
            "INSERT OR IGNORE INTO media_origins VALUES(?,?,?,?)",
            (key, image_url, core.now(), encoded),
        )

    def save(reference, features, comparison):
        """Save a report only after the caller's source-attested comparison succeeds."""
        _, metadata, _ = core.forensics["source"](reference["id"])
        report = build_report(reference, features, comparison, metadata)
        core.execute(
            "INSERT OR REPLACE INTO media_reports VALUES(?,?,?)",
            (reference["id"], core.now(), json.dumps(report)),
        )
        return report

    def portfolio(limit=24, offset=0):
        """List every image with bounded, source-balanced paging so one publisher cannot fill the home screen."""
        rows = core.rows(
            """WITH ranked AS (
            SELECT e.id,e.title,e.url,e.sha256,e.created,r.updated,r.data,v.status,v.error,
            row_number() OVER (
              PARTITION BY coalesce(json_extract(r.data,'$.source_domain'),
                nullif(substr(substr(e.url,instr(e.url,'://')+3),1,instr(substr(e.url,instr(e.url,'://')+3)||'/','/')-1),''),'Imported file')
              ORDER BY e.created DESC,e.id) AS source_rank
            FROM evidence e LEFT JOIN media_reports r ON e.id=r.evidence_id
            LEFT JOIN visual_review_state v ON e.id=v.evidence_id
            WHERE e.path IS NOT NULL AND e.mime LIKE 'image/%')
            SELECT * FROM ranked ORDER BY source_rank,created DESC,id LIMIT ? OFFSET ?""",
            (limit, offset),
        )
        items = []
        for row in rows:
            report = json.loads(row["data"]) if row["data"] else None
            stale = bool(report and report["original_sha256"] != row["sha256"])
            items.append(
                {
                    "evidence_id": row["id"],
                    "title": row["title"],
                    "source_url": row["url"],
                    "source_domain": urlparse(row["url"]).hostname or "Imported file",
                    "preview_url": f"/api/evidence/{row['id']}/preview",
                    "updated": row["updated"],
                    "status": "STALE" if stale else row["status"] or "PENDING",
                    "error": row["error"],
                    "report": None if stale else report,
                    "origins": [
                        {"observed": x["observed"], **json.loads(x["data"])}
                        for x in core.rows(
                            "SELECT observed,data FROM media_origins WHERE image_url=? ORDER BY observed DESC LIMIT 20",
                            (row["url"],),
                        )
                    ],
                }
            )
        total = core.rows(
            "SELECT count(*) AS n FROM evidence WHERE path IS NOT NULL AND mime LIKE 'image/%'"
        )[0]["n"]
        return {
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(items) < total,
        }

    @core.app.get("/api/media/reports")
    def reports(limit: int = 24, offset: int = 0):
        """Read a bounded page of general media reviews without changing work queues."""
        from fastapi import HTTPException

        if not 1 <= limit <= 100 or offset < 0:
            raise HTTPException(422, "Use limit 1..100 and nonnegative offset")
        return portfolio(limit, offset)

    return {"save": save, "portfolio": portfolio, "register": register}

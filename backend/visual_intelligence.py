"""Source-attested image retrieval and geometric comparisons using established libraries."""

import base64
import hashlib
import json
from typing import Any
from fastapi import HTTPException
from pydantic import BaseModel, Field
import numpy as np
import cv2

cv2.setNumThreads(1)


def hamming(left: str, right: str) -> int:
    """Measure bit disagreement between equal-length hex image signatures."""
    if len(left) != len(right) or not 1 <= len(left) <= 64:
        raise ValueError("Comparable bounded hash formats required")
    return (int(left, 16) ^ int(right, 16)).bit_count()


def compare_features(a: dict, b: dict) -> dict:
    """Use pHash/dHash and ORB-Hamming/RANSAC on bounded source-derived descriptors."""
    hashes = {k: hamming(a[k], b[k]) for k in ("phash", "dhash", "colorhash")}
    scales = [
        {
            "sigma": sigma,
            "phash_hamming": hamming(
                a["views"][sigma]["phash"], b["views"][sigma]["phash"]
            ),
        }
        for sigma in a["views"]
        if sigma in b["views"]
    ]
    pairs = []
    inliers = 0
    transform = None

    def descriptors(v):
        """Validate bounded stored descriptors before allocating OpenCV arrays."""
        orb = v["orb"]
        rows = int(orb["rows"])
        points = np.asarray(orb["points"], dtype=float).reshape(-1, 2)
        if (
            not 0 <= rows <= 400
            or points.shape != (rows, 2)
            or not np.isfinite(points).all()
        ):
            raise ValueError("Invalid bounded ORB keypoints")
        raw = base64.b64decode(orb["descriptors_b64"], validate=True)
        if len(raw) != rows * 32:
            raise ValueError("ORB descriptor byte count mismatch")
        return np.frombuffer(raw, dtype=np.uint8).reshape(rows, 32), points

    da, pa = descriptors(a)
    db, pb = descriptors(b)
    if len(da) >= 4 and len(db) >= 4:
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        matches = matcher.knnMatch(da, db, k=2)
        good = [
            m
            for ms in matches
            if len(ms) == 2
            for m, n in [ms]
            if m.distance < 0.75 * n.distance
        ]
        pairs = [
            {
                "left": int(m.queryIdx),
                "right": int(m.trainIdx),
                "hamming": float(m.distance),
            }
            for m in good
        ]
        if len(good) >= 4:
            cv2.setRNGSeed(42)
            matrix, mask = cv2.findHomography(
                np.float32([pa[m.queryIdx] for m in good]),
                np.float32([pb[m.trainIdx] for m in good]),
                cv2.RANSAC,
                4.0,
                maxIters=1000,
                confidence=0.99,
            )
            if matrix is not None and np.isfinite(matrix).all():
                transform = matrix.tolist()
                inliers = int(mask.sum())
    return {
        "hash_distances": hashes,
        "multiscale": scales,
        "orb_ratio_matches": len(pairs),
        "ransac_inliers": inliers,
        "homography": transform,
        "matching_keypoints": pairs[:100],
        "parameters": {
            "orb_max_features": 400,
            "ratio_threshold": 0.75,
            "ransac_pixel_threshold": 4,
            "ransac_max_iters": 1000,
            "seed": 42,
        },
        "library": "OpenCV " + cv2.__version__,
        "assessment": "SIMILARITY LEAD / HUMAN REVIEW REQUIRED",
        "limitations": "Low-frequency resemblance, perceptual hashes and geometric matches do not prove identity, image authenticity, a hidden intentional image or a prediction. Blurred/overlaid illustrations can create apparent structure. RANSAC inliers are geometric correspondences, not semantic evidence.",
    }


class VisualSearch(BaseModel):
    """An acquired reference image and an explicit bounded corpus comparison."""

    evidence_id: str
    limit: int = Field(default=20, ge=1, le=100)


def install(core: Any) -> dict:
    """Expose real-original image search with hash-attested extracted signatures."""
    core.execute(
        "CREATE TABLE IF NOT EXISTS visual_explanations(id TEXT PRIMARY KEY,created TEXT,evidence_id TEXT,data TEXT)"
    )
    core.execute(
        "CREATE TABLE IF NOT EXISTS visual_runs(id TEXT PRIMARY KEY,created TEXT,evidence_id TEXT,data TEXT)"
    )

    def source(eid: str) -> tuple[dict, dict]:
        """Verify original, extraction and result.json before using any derived features."""
        e, meta, digest = core.forensics["source"](eid)
        if not e["mime"].startswith("image/"):
            raise ValueError("An acquired image is required")
        path = core.ROOT / "derivatives" / eid / "result.json"
        expected = meta.get("derivative_hashes", {}).get("result.json")
        if (
            path.is_symlink()
            or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise ValueError("Image extraction receipt failed integrity verification")
        features = (
            json.loads(path.read_text()).get("metadata", {}).get("visual_features")
        )
        if not features:
            raise ValueError(
                "Image requires reprocessing with the current isolated processor"
            )
        return e, features

    def search(eid: str, limit: int = 20) -> dict:
        """Compare actual acquired images; preserve failures and corpus coverage boundaries."""
        reference, features = source(eid)
        results = []
        stories = []
        unavailable = []
        scanned = 0
        rows = core.rows(
            "SELECT id FROM evidence WHERE mime LIKE 'image/%' AND path IS NOT NULL ORDER BY created DESC LIMIT 501"
        )
        for row in rows[:500]:
            if row["id"] == eid:
                continue
            try:
                e, other = source(row["id"])
                comparison = compare_features(features, other)
                from .visual_explanation import explain

                story = explain(core, reference, features, e, other)
                if story is None:
                    story = explain(core, e, other, reference, features)
                if story:
                    core.execute(
                        "INSERT OR REPLACE INTO visual_explanations VALUES(?,?,?,?)",
                        (
                            story["id"],
                            core.now(),
                            story["reference_id"],
                            json.dumps(story),
                        ),
                    )
                    stories.append(story["id"])
                scanned += 1
                results.append(
                    {
                        "evidence_id": e["id"],
                        "title": e["title"],
                        "original_url": e["url"],
                        "original_sha256": e["sha256"],
                        **comparison,
                    }
                )
            except ValueError as ex:
                unavailable.append({"evidence_id": row["id"], "reason": str(ex)})
        results.sort(
            key=lambda r: (
                r["original_sha256"] != reference["sha256"],
                -r["ransac_inliers"],
                r["hash_distances"]["phash"],
            )
        )
        record = {
            "reference_id": eid,
            "explanation_ids": stories,
            "reference_sha256": reference["sha256"],
            "compared": scanned,
            "unavailable": unavailable,
            "corpus_limit": 500,
            "corpus_truncated": len(rows) > 500,
            "results": results[:limit],
            "ranked_results_retained": min(limit, len(results)),
            "results_truncated": len(results) > limit,
            "scope": "Stored acquired image corpus only; this is not an unrestricted internet-wide image or face search.",
            "controls": "Self/known-transform and unrelated-image acceptance fixtures establish implementation behavior; no case-level false-positive rate is established.",
        }
        rid = core.uid("VISUAL")
        core.execute(
            "INSERT INTO visual_runs VALUES(?,?,?,?)",
            (rid, core.now(), eid, json.dumps(record)),
        )
        result = {"id": rid, **record}
        if hasattr(core, "media_reports"):
            core.media_reports["save"](reference, features, result)
        return result

    @core.app.get("/api/visual/explanations")
    def explanations() -> list:
        """Return already-produced visual explanations; viewing never starts analysis."""
        verified = []
        for r in core.rows(
            "SELECT * FROM visual_explanations ORDER BY created DESC LIMIT 30"
        ):
            data = json.loads(r["data"])
            try:
                bound_originals = [
                    (data["reference_id"], data["reference_sha256"]),
                    (data["composite_id"], data["composite_sha256"]),
                ]
                if data.get("photo_reference"):
                    bound_originals.append(
                        (
                            data["photo_reference"]["evidence_id"],
                            data["photo_reference"]["original_sha256"],
                        )
                    )
                for eid, expected in bound_originals:
                    original, _, _ = core.forensics["source"](eid)
                    if original["sha256"] != expected:
                        raise ValueError("Saved visual explanation source hash changed")
                for citation in data["sources"]:
                    original, _, digest = core.forensics["source"](
                        citation["evidence_id"]
                    )
                    if (
                        original["sha256"] != citation["original_sha256"]
                        or digest != citation["text_sha256"]
                        or citation["quote"] not in original["text"]
                    ):
                        raise ValueError(
                            "Saved source attribution no longer matches its original"
                        )
                verified.append({**r, "data": data})
            except ValueError as ex:
                verified.append({**r, "data": {"unavailable": True, "reason": str(ex)}})
        return verified

    @core.app.get("/api/visual")
    def overview() -> dict:
        """Show actual image-analysis coverage and saved source-bound retrieval results."""
        return {
            "runs": [
                {**r, "data": json.loads(r["data"])}
                for r in core.rows(
                    "SELECT * FROM visual_runs ORDER BY created DESC LIMIT 50"
                )
            ],
            "images": [
                {"id": r["id"], "metadata": json.loads(r["metadata"])}
                for r in core.rows(
                    "SELECT id,metadata FROM evidence WHERE mime LIKE 'image/%' AND path IS NOT NULL"
                )
            ],
            "policy": "Source-preserving image comparison; matches are review-required leads and never predictions or identity determinations.",
        }

    @core.app.post("/api/visual/search")
    def api_search(value: VisualSearch) -> dict:
        """Run visual retrieval on an acquired image with explicit failure reporting."""
        try:
            return search(value.evidence_id, value.limit)
        except ValueError as ex:
            raise HTTPException(422, str(ex)) from ex

    return {
        "search": search,
        "source": source,
        "overview": overview,
        "explanations": explanations,
    }

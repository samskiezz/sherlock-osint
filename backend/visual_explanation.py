"""Explain measured panel mixtures and exact publisher attribution without inferring identity."""

import hashlib
import json
import re
from urllib.parse import urljoin
from .visual_intelligence import compare_features


def panel_features(parent, panel):
    """Adapt source-derived panel signatures to the established geometric matcher."""
    return {
        **parent,
        "phash": panel["phash"],
        "dhash": panel["dhash"],
        "colorhash": panel["colorhash"],
        "views": {},
        "orb": panel["orb_features"],
    }


def explain(core, anchor, anchor_features, composite, composite_features):
    """Produce a source-grounded visual sequence only after a real mixture and anchor match."""
    analysis = composite_features.get("panel_analysis", {})
    if analysis.get("status") != "MIXTURE_SEQUENCE_DETECTED":
        return None
    endpoints = analysis["best"]["endpoints"]
    matches = []
    for p in analysis["panels"]:
        if p["panel"] not in endpoints:
            continue
        match = compare_features(anchor_features, panel_features(composite_features, p))
        matches.append(
            (match["ransac_inliers"], -match["hash_distances"]["phash"], p, match)
        )
    if not matches:
        return None
    matches.sort(key=lambda x: (-x[0], -x[1]))
    _, _, matched, match = matches[0]
    if match["ransac_inliers"] < 8:
        return None
    alternative = next(
        p
        for p in analysis["panels"]
        if p["panel"] in endpoints and p["panel"] != matched["panel"]
    )
    contexts = []
    verified_pages = []
    for row in core.rows(
        "SELECT id FROM evidence WHERE mime LIKE '%html%' AND path IS NOT NULL ORDER BY created DESC LIMIT 100"
    ):
        try:
            source, metadata, digest = core.forensics["source"](row["id"])
            verified_pages.append((source, metadata, digest))
            linked = [
                m
                for m in metadata.get("media", [])
                if urljoin(source["url"], m.get("href", ""))
                in [composite["url"], anchor["url"]]
            ]
            if not linked:
                continue
            text = source["text"]
            reference_title = anchor["title"].split("·", 1)[0].strip()
            normalised = re.sub(r"\s+", " ", text)
            described_as_artwork = bool(
                len(reference_title) < 100
                and re.search(
                    r"(?:digital image|artwork|painting|illustration).{0,150}?(?:titled|called|named)\s+"
                    + re.escape(reference_title),
                    normalised,
                    re.I,
                )
            )
            # Names come from an explicit source description, never a face matcher.
            subject = re.search(
                r"\b(?:President|president)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)\b", text
            )
            quote_start = max(0, subject.start() - 110) if subject else 0
            quote_end = (
                min(len(text), subject.end() + 210) if subject else min(300, len(text))
            )
            quote = text[quote_start:quote_end]
            contexts.append(
                {
                    "evidence_id": source["id"],
                    "title": source["title"],
                    "url": source["url"],
                    "quote": quote,
                    "text_start": quote_start,
                    "text_end": quote_end,
                    "original_sha256": source["sha256"],
                    "text_sha256": digest,
                    "subject_name_reported": subject[1] if subject else None,
                    "describes_reference_as_artwork": described_as_artwork,
                    "attribution": "Publisher description; not independent biometric recognition or recognition from the artwork",
                }
            )
        except ValueError:
            continue
    reference_is_artwork = any(c["describes_reference_as_artwork"] for c in contexts)
    identity = (
        next((c for c in contexts if c["subject_name_reported"]), None)
        if reference_is_artwork
        else None
    )
    photo_reference = match_published_photo(
        core,
        composite,
        composite_features,
        alternative,
        verified_pages,
        {anchor["id"], composite["id"]},
    )
    if photo_reference:
        caption_source = photo_reference["citation"]
        if caption_source["subject_name_reported"]:
            identity = caption_source
        if not any(c["evidence_id"] == caption_source["evidence_id"] for c in contexts):
            contexts.append(caption_source)
    a, b = endpoints
    sequence = []
    for p in analysis["panels"]:
        # Convert weights to the matched anchor endpoint; endpoint B may be either image.
        artwork_weight = (
            p["endpoint_b_weight"]
            if matched["panel"] == b
            else 1 - p["endpoint_b_weight"]
        )
        sequence.append(
            {
                "panel": p["panel"],
                "image_url": f"/api/evidence/{composite['id']}/diagnostic/visual-panel-{p['panel']}",
                "fit_url": f"/api/evidence/{composite['id']}/diagnostic/visual-fit-{p['panel']}",
                "residual_url": f"/api/evidence/{composite['id']}/diagnostic/visual-residual-{p['panel']}",
                "reference_weight": artwork_weight,
                "artwork_weight": artwork_weight,
                "other_image_weight": 1 - artwork_weight,
                "rmse": p["rmse"],
                "error_reduction": p["error_reduction"],
            }
        )
    sequence.sort(key=lambda p: p["artwork_weight"])
    middle = [p for p in sequence if p["panel"] not in endpoints]
    key = hashlib.sha256(
        json.dumps(
            [
                anchor["id"],
                anchor["sha256"],
                composite["id"],
                composite["sha256"],
                "panel-explanation-v13",
            ]
        ).encode()
    ).hexdigest()[:24]
    subject = identity["subject_name_reported"] if identity else None
    return {
        "id": "VISUAL-STORY-" + key,
        "title": f"{subject}: how the photograph enters the composite"
        if subject
        else "How two images form the composite",
        "summary": "The acquired collage is consistent with a progressive overlay of two different images. Its intermediate panels closely fit measured blends of the endpoint panels.",
        "assessment": "MEASURED COMPOSITION CANDIDATE; SOURCE AND CHRONOLOGY REVIEW REQUIRED",
        "reference_id": anchor["id"],
        "reference_is_artwork": reference_is_artwork,
        "reference_label": "Artwork" if reference_is_artwork else "Matched reference",
        "other_label": "Photograph" if identity else "Other image",
        "reference_sha256": anchor["sha256"],
        "composite_id": composite["id"],
        "composite_sha256": composite["sha256"],
        "subject_name_reported": subject,
        "subject_attribution": identity,
        "photo_reference": photo_reference,
        "sources": contexts,
        "matched_artwork_panel": matched["panel"],
        "photo_candidate_panel": alternative["panel"],
        "geometry": match,
        "sequence": sequence,
        "steps": [
            {
                "title": "Separate the acquired composite",
                "detail": "Four panel crops were extracted without changing the preserved original.",
            },
            {
                "title": "Locate the stored reference image",
                "detail": f"Panel {matched['panel'] + 1} matches the acquired reference through {match['ransac_inliers']} geometric inliers.",
            },
            {
                "title": "Identify the other endpoint from its source",
                "detail": f"The photograph endpoint matches an acquired publisher image through {photo_reference['geometry']['ransac_inliers']} geometric inliers. Its exact caption names {subject}; this is reference-image matching and source attribution, not recognition from the standalone reference."
                if photo_reference and subject
                else f"The linked acquired publisher describes the image as {subject}. This name is source attribution, not recognition from the standalone reference."
                if subject
                else "A different endpoint image is visible. Its subject is not yet identified by a linked acquired source.",
            },
            {
                "title": "Test the intermediate panels",
                "detail": "Every endpoint pair was tested. The selected pair fits the two intermediate panels with "
                + ", ".join(f"{p['rmse'] * 255:.1f}/255 RGB RMSE" for p in middle)
                + ".",
            },
            {
                "title": "Check source dates and provenance",
                "detail": "A blend fit does not establish when or why a composition was made. Historical claims require independent dated originals.",
            },
        ],
        "limits": "Pixel mixing tests use a downsampled RGB model. Approximate composition is not an edit-history certificate. The source may be mistaken; a visually recognisable composite does not establish person recognition from the standalone artwork.",
        "method": analysis["method"],
        "pairs_attempted": analysis["pairs_attempted"],
    }


def match_published_photo(
    core, composite, composite_features, panel, verified_pages, excluded
):
    """Match the photograph endpoint against acquired, captioned publisher images.

    Identity is reported by the exact publisher caption. A geometric correspondence
    is a retrieval lead, not biometric identification or authenticated edit history.
    """
    if not hasattr(core, "visual"):
        return None
    endpoint = panel_features(composite_features, panel)
    found = []
    for row in core.rows(
        "SELECT id FROM evidence WHERE mime LIKE 'image/%' AND path IS NOT NULL ORDER BY created DESC LIMIT 100"
    ):
        if row["id"] in excluded:
            continue
        try:
            image, features = core.visual["source"](row["id"])
        except ValueError:
            continue
        captions = []
        for page, metadata, digest in verified_pages:
            for media in metadata.get("media", []):
                if urljoin(page["url"], media.get("href", "")) != image["url"]:
                    continue
                caption = (
                    media.get("caption", "").replace(" License this photo", "").strip()
                )
                if not 10 < len(caption) < 1200:
                    continue
                exact = re.search(
                    r"\s+".join(re.escape(t) for t in caption.split()), page["text"]
                )
                if not exact:
                    continue
                subject = re.search(
                    r"\b(?:President|president)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)\b",
                    exact[0],
                )
                captions.append(
                    {
                        "evidence_id": page["id"],
                        "title": page["title"],
                        "url": page["url"],
                        "quote": exact[0],
                        "text_start": exact.start(),
                        "text_end": exact.end(),
                        "original_sha256": page["sha256"],
                        "text_sha256": digest,
                        "subject_name_reported": subject[1] if subject else None,
                        "attribution": "Acquired publisher caption attached to the acquired image; geometric reference match, not biometric identification",
                    }
                )
        if not captions:
            continue
        match = compare_features(features, endpoint)
        if match["ransac_inliers"] < 12:
            continue
        found.append(
            {
                "evidence_id": image["id"],
                "title": image["title"],
                "original_url": image["url"],
                "original_sha256": image["sha256"],
                "preview_url": f"/api/evidence/{image['id']}/preview",
                "caption": captions[0]["quote"],
                "citation": captions[0],
                "geometry": match,
                "assessment": "Geometric correspondence to a source-captioned photograph; review required",
            }
        )
    found.sort(key=lambda f: -f["geometry"]["ransac_inliers"])
    return found[0] if found else None

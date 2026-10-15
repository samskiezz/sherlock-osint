"""Verify the actual image vault and persisted automatic review receipts."""

import hashlib
import json
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    """Save public evidence IDs/hashes and honest live source status, never credentials."""
    client = httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=30)
    all_items, offset = [], 0
    while True:
        response = client.get(
            "/api/media/reports", params={"limit": 100, "offset": offset}
        )
        response.raise_for_status()
        page = response.json()
        all_items.extend(page["items"])
        if not page["has_more"]:
            break
        offset += len(page["items"])
    images = []
    for item in all_items:
        response = client.get("/api/evidence/" + item["evidence_id"])
        response.raise_for_status()
        evidence = response.json()
        original = ROOT / "data/originals" / evidence["sha256"]
        okay = (
            original.is_file()
            and not original.is_symlink()
            and hashlib.sha256(original.read_bytes()).hexdigest() == evidence["sha256"]
        )
        images.append(
            {
                "evidence_id": item["evidence_id"],
                "title": item["title"],
                "source_domain": item["source_domain"],
                "sha256": evidence["sha256"],
                "size": evidence["size"],
                "original_present_and_hash_verified": okay,
                "review_status": item["status"],
                "report_saved": bool(item["report"]),
                "assessment": item["report"]["assessment"] if item["report"] else None,
                "origins": item["origins"],
            }
        )
    campaign_runs = client.get("/api/research").json()["runs"]
    run = next(
        (r for r in campaign_runs if r["campaign_id"] == "CAMPAIGN-7e355288d1bb"), None
    )
    result = {
        "total_acquired_images": len(images),
        "distinct_source_domains": len({x["source_domain"] for x in images}),
        "saved_reports": sum(x["report_saved"] for x in images),
        "verified_image_originals": sum(
            x["original_present_and_hash_verified"] for x in images
        ),
        "images": images,
        "new_broad_media_watch": {
            "run_id": run["id"],
            "status": run["status"],
            "discovered": len(run["data"].get("hits", [])),
            "registered_jobs": len(run["data"].get("jobs", [])),
            "failures": [
                {"objective": t["objective"], "reason": t["error"]}
                for t in run["tasks"]
                if t.get("error")
            ],
        }
        if run
        else None,
        "limitations": "Publisher image renditions are not camera originals. No live X collection is verified. Matching is bounded to the acquired reference corpus; no claim of universal concealed-image detection or future prediction.",
    }
    (ROOT / "artifacts/continuous-media-state-v13.json").write_text(
        json.dumps(result, indent=2)
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "total_acquired_images",
                    "distinct_source_domains",
                    "saved_reports",
                    "verified_image_originals",
                )
            }
        )
    )
    assert images and all(
        x["original_present_and_hash_verified"] and x["report_saved"] for x in images
    )


if __name__ == "__main__":
    main()

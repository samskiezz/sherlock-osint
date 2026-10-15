"""Stream a real case package with reviewed originals, verified derivatives and omission records."""

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any
import zipfile
from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

MAX_ARCHIVE_INPUT = 1024**3


def build(core: Any, payload: dict[str, Any]) -> FileResponse:
    """Write an on-disk ZIP, never substituting summaries for permitted original bytes."""
    if shutil.disk_usage(core.ROOT).free < core.MIN_FREE_BYTES:
        raise HTTPException(507, "Insufficient free storage to export safely")
    fd, name = tempfile.mkstemp(prefix="looking-glass-", suffix=".zip")
    __import__("os").close(fd)
    path = Path(name)
    omissions = []
    included = []
    members = {}
    total = 0
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for evidence in payload["evidence"]:
                if not evidence.get("sha256"):
                    continue
                eid = evidence["id"]
                digest = evidence["sha256"]
                meta = evidence["metadata"]
                review = meta.get("licence_review", {})
                reason = None
                original = core.ROOT / "originals" / digest
                if (
                    not review.get("redistributable")
                    or review.get("original_sha256") != digest
                ):
                    reason = "Redistribution rights not positively reviewed; original remains in the local vault"
                elif (
                    original.is_symlink()
                    or not original.is_file()
                    or original.resolve().parent != (core.ROOT / "originals").resolve()
                ):
                    reason = "Original file missing or outside the original vault"
                elif hashlib.sha256(original.read_bytes()).hexdigest() != digest:
                    reason = "Original integrity verification failed"
                elif total + original.stat().st_size > MAX_ARCHIVE_INPUT:
                    reason = "Export exceeds the explicit 1 GiB input budget"
                if reason:
                    omissions.append({"id": eid, "sha256": digest, "reason": reason})
                    continue
                member = "originals/" + digest
                if member not in members:
                    z.write(original, member)
                    members[member] = digest
                    total += original.stat().st_size
                included.append(
                    {
                        "evidence_id": eid,
                        "member": member,
                        "sha256": digest,
                        "licence_review": review,
                    }
                )
                for filename, expected in meta.get("derivative_hashes", {}).items():
                    if Path(filename).name != filename:
                        continue
                    derivative = core.ROOT / "derivatives" / eid / filename
                    target = f"derivatives/{eid}/{filename}"
                    if derivative.is_symlink() or not derivative.is_file():
                        omissions.append(
                            {
                                "id": eid,
                                "derivative": filename,
                                "reason": "Derivative absent or symlink",
                            }
                        )
                        continue
                    if hashlib.sha256(derivative.read_bytes()).hexdigest() != expected:
                        omissions.append(
                            {
                                "id": eid,
                                "derivative": filename,
                                "reason": "Derivative integrity verification failed",
                            }
                        )
                        continue
                    if total + derivative.stat().st_size > MAX_ARCHIVE_INPUT:
                        omissions.append(
                            {
                                "id": eid,
                                "derivative": filename,
                                "reason": "Export input budget reached",
                            }
                        )
                        continue
                    z.write(derivative, target)
                    members[target] = expected
                    total += derivative.stat().st_size
            manifest = json.dumps(payload, indent=2).encode()
            z.writestr("manifest.json", manifest)
            members["manifest.json"] = hashlib.sha256(manifest).hexdigest()
            z.writestr("included-originals.json", json.dumps(included, indent=2))
            z.writestr("original-omissions.json", json.dumps(omissions, indent=2))
            z.writestr(
                "SHA256SUMS",
                "\n".join(
                    digest + "  " + member for member, digest in sorted(members.items())
                )
                + "\n",
            )
            z.writestr(
                "README.txt",
                "PROJECT LOOKING GLASS. This package contains the case records and only originals whose redistribution was positively reviewed. Missing, restricted, unreviewed or damaged files are explicitly listed in original-omissions.json. SHA256SUMS refers to included files. A recorded licence assessment is a human statement, not independent legal certification. Original files remain unchanged in the local vault. Maximum input: 1 GiB.",
            )
        core.log(
            "case_archive_built",
            {
                "original_records_included": len(included),
                "omissions": len(omissions),
                "input_bytes": total,
                "archive_bytes": path.stat().st_size,
            },
        )
        return FileResponse(
            path,
            media_type="application/zip",
            filename="looking-glass-case.zip",
            background=BackgroundTask(path.unlink, missing_ok=True),
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise


def install(core: Any) -> None:
    """Record explicit redistribution decisions separately from immutable source bytes."""

    class LicenceReview(BaseModel):
        """Human licence assessment, recorded for audit and reviewed export selection."""

        redistributable: bool
        licence: str = Field(min_length=2, max_length=200)
        basis: str = Field(min_length=20, max_length=2000)

    @core.app.post("/api/evidence/{eid}/licence-review")
    def review(eid: str, value: LicenceReview) -> dict[str, Any]:
        """Save a reversible human rights assessment; never automatically infer public domain."""
        e = core.get_evidence(eid)
        if not e.get("sha256"):
            raise HTTPException(422, "An acquired original is required")
        with core.lock:
            meta = json.loads(
                core.rows("SELECT metadata FROM evidence WHERE id=?", (eid,))[0][
                    "metadata"
                ]
            )
            decision = {
                **value.model_dump(),
                "recorded_at": core.now(),
                "original_sha256": e["sha256"],
                "authority": "Human assessment submitted through the local API; see authenticated gateway audit for account identity",
            }
            meta["licence_review"] = decision
            core.execute(
                "UPDATE evidence SET metadata=? WHERE id=?", (json.dumps(meta), eid)
            )
            core.log("licence_review_recorded", {"evidence_id": eid, **decision})
        return decision

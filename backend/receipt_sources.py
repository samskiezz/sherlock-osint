"""Read source attestations without altering immutable historical receipts."""

import hashlib


def receipt_sources(data):
    result = data.get("result") or {}
    if result.get("sources"):
        return result["sources"]
    # Early forensic adapters omitted the wrapper binding, but the hashed output
    # already records both original and extract digests. Reuse those declarations;
    # never fill missing historical hashes from the current source.
    if data.get("tool") == "forensics.screen":
        output = result.get("output") or {}
        details = output.get("data") or {}
        if (
            output.get("evidence_id")
            and details.get("evidence_sha256")
            and details.get("text_derivative_sha256")
        ):
            start = details.get("input_offset", 0)
            return [
                {
                    "evidence_id": output["evidence_id"],
                    "original_sha256": details["evidence_sha256"],
                    "text_sha256": details["text_derivative_sha256"],
                    "text_start": start,
                    "text_end": start + len(details.get("input", "")),
                }
            ]
    return []


def derivative_binding_valid(core, binding):
    hashes = binding.get("derivative_hashes") or {}
    if not isinstance(hashes, dict):
        return False
    for name, expected in hashes.items():
        if name != "result.json":
            return False
        target = core.ROOT / "derivatives" / binding["evidence_id"] / name
        try:
            if (
                target.is_symlink()
                or not target.is_file()
                or not target.resolve().is_relative_to(
                    (core.ROOT / "derivatives").resolve()
                )
            ):
                return False
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                return False
        except OSError:
            return False
    return True

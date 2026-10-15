"""Check independent source citation validation; no model output is treated as a proven claim."""

import pytest
from backend.cited_model import select_passages, validate_findings


def test_numbered_passages_preserve_original_offsets_and_pages():
    text = (
        "\n[Page 1]\nPublication metadata. "
        + ("unrelated text. " * 70)
        + "\n[Page 2]\nThe nickel alloy resists burning in oxygen. Inventor: Example Researcher."
    )
    passages, truncated = select_passages(
        text, "Identify the nickel alloy and inventor"
    )
    assert not truncated and any(p["page"] == 2 for p in passages)
    assert all(text[p["start"] : p["end"]] == p["text"] for p in passages)


def test_claims_remain_hypotheses_even_with_valid_quotations():
    text = "An alloy is described. Its performance is not independently verified."
    p = [{"text": text, "start": 0, "end": len(text), "page": 3}]
    accepted, rejected = validate_findings(
        {"findings": [{"claim": "The text describes an alloy.", "passage_index": 0}]},
        p,
        text,
        "EV-fixture",
    )
    assert not rejected and accepted[0]["quote"] == text and accepted[0]["page"] == 3
    assert accepted[0]["state"] == "HYPOTHESIS / HUMAN REVIEW REQUIRED"
    # Citation correctness never silently becomes a semantic entailment verdict.
    accepted, _ = validate_findings(
        {
            "findings": [
                {"claim": "This alloy enables time travel.", "passage_index": 0}
            ]
        },
        p,
        text,
        "EV-fixture",
    )
    assert accepted[0]["state"] == "HYPOTHESIS / HUMAN REVIEW REQUIRED"
    assert "verified_fact" not in accepted[0]


def test_fabricated_indices_and_malformed_claims_are_rejected():
    text = "Actual source."
    p = [{"text": text, "start": 0, "end": len(text), "page": None}]
    accepted, rejected = validate_findings(
        {
            "findings": [
                {"claim": "Invented citation", "passage_index": 8},
                {"claim": "Wrong index type", "passage_index": True},
                {"claim": "x" * 301, "passage_index": 0},
            ]
        },
        p,
        text,
        "EV-fixture",
    )
    assert not accepted and len(rejected) == 3
    assert validate_findings({"findings": []}, p, text, "EV-fixture") == ([], [])


def test_tampered_passage_and_invalid_schema_fail_closed():
    p = [{"text": "forged", "start": 0, "end": 6, "page": None}]
    with pytest.raises(ValueError, match="no longer matches"):
        validate_findings(
            {"findings": [{"claim": "Anything", "passage_index": 0}]},
            p,
            "actual",
            "EV-fixture",
        )
    with pytest.raises(ValueError):
        validate_findings({"findings": "invented"}, p, "actual", "EV-fixture")

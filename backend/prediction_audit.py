"""Audit alleged pre-event predictions without treating resemblance or numerology as forecasts."""

import json
from datetime import datetime, timezone
from typing import Any
from fastapi import HTTPException
from pydantic import BaseModel, Field


def utc(value: str) -> datetime:
    """Require explicit timezone information, preserving the original date interpretation."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(
            "Use timezone-aware dates; an ambiguous local date cannot establish chronology"
        )
    return parsed.astimezone(timezone.utc)


class Audit(BaseModel):
    """A source-backed alleged prediction, outcome and independent timestamp records."""

    artefact_id: str
    artefact_quote: str = Field(min_length=1, max_length=2000)
    claimed_publication_utc: str = Field(max_length=60)
    event_utc: str = Field(max_length=60)
    specific_outcome: str = Field(min_length=10, max_length=1000)
    specificity_terms: list[str] = Field(min_length=2, max_length=10)
    timestamp_source_id: str = Field(default="", max_length=100)
    timestamp_quote: str = Field(default="", max_length=2000)
    counterevidence_ids: list[str] = Field(default_factory=list, max_length=20)
    analysis_notes: str = Field(default="", max_length=2000)


def evaluate(value: Audit, source_text: str, timestamp_text: str | None = None) -> dict:
    """Check exact quotation and stated time order; do not certify user-entered dates."""
    if value.artefact_quote not in source_text:
        raise ValueError(
            "Alleged prediction quotation is absent from the acquired source"
        )
    pub, event = utc(value.claimed_publication_utc), utc(value.event_utc)
    terms = value.specificity_terms
    if any(not isinstance(t, str) or not 1 <= len(t) <= 100 for t in terms):
        raise ValueError("Specificity terms must be bounded literal strings")
    missing = [t for t in terms if t.casefold() not in value.artefact_quote.casefold()]
    independent_quote = bool(
        value.timestamp_source_id
        and value.timestamp_source_id != value.artefact_id
        and value.timestamp_quote
        and timestamp_text
        and value.timestamp_quote in timestamp_text
    )
    reasons = []
    if pub >= event:
        reasons.append("Declared publication time is not before the event")
    if missing:
        reasons.append("The original quotation lacks supplied outcome-specific terms")
    if not independent_quote:
        reasons.append(
            "No distinct acquired timestamp-supporting quotation was verified"
        )
    return {
        "assessment": "NOT ESTABLISHED"
        if reasons
        else "CHRONOLOGY CANDIDATE / HUMAN REVIEW REQUIRED",
        "declared_time_order": pub < event,
        "declared_lead_seconds": (event - pub).total_seconds(),
        "missing_specificity_terms": missing,
        "independent_timestamp_quote_present": independent_quote,
        "reasons": reasons,
        "date_verification": "User-entered dates were parsed, not independently certified. A quotation from a second file does not prove an authentic archive timestamp or source independence.",
        "alternative_explanations": [
            "Post-event alteration or overlay",
            "Ambiguous wording and retrospective reinterpretation",
            "Selection from many unrelated names, images or transformations",
            "Incorrect identity or historical account/header attribution",
            "Coincidence and ordinary publication history",
        ],
        "controls": "Pre-register an unambiguous outcome and unchanged rule, record every attempted comparison, use unrelated controls, and evaluate unseen outcomes. Additive sums and visual resemblance do not by themselves constitute specific predictions.",
        "forecast_claim": False,
    }


def install(core: Any) -> dict:
    """Preserve reproducible chronology assessments and visible counterevidence."""
    core.execute(
        "CREATE TABLE IF NOT EXISTS prediction_audits(id TEXT PRIMARY KEY,created TEXT,data TEXT)"
    )

    @core.app.get("/api/prediction-audits")
    def listing() -> list:
        """Return original claims, exact source references, uncertainties and counterevidence."""
        return [
            {**r, "data": json.loads(r["data"])}
            for r in core.rows(
                "SELECT * FROM prediction_audits ORDER BY created DESC LIMIT 100"
            )
        ]

    @core.app.post("/api/prediction-audits")
    def create(value: Audit) -> dict:
        """Audit the exact claim instead of converting an anomaly into a prediction."""
        try:
            e, meta, digest = core.forensics["source"](value.artefact_id)
            timestamp = None
            timestamp_source = None
            if value.timestamp_source_id:
                other, om, od = core.forensics["source"](value.timestamp_source_id)
                timestamp = other["text"]
                timestamp_source = {
                    "evidence_id": other["id"],
                    "original_sha256": other["sha256"],
                    "text_sha256": od,
                }
            assessment = evaluate(value, e["text"], timestamp)
            counter = []
            for eid in value.counterevidence_ids:
                other, om, od = core.forensics["source"](eid)
                counter.append(
                    {
                        "evidence_id": eid,
                        "original_sha256": other["sha256"],
                        "text_sha256": od,
                    }
                )
        except ValueError as ex:
            raise HTTPException(422, str(ex)) from ex
        record = {
            "inputs": value.model_dump(),
            "assessment": assessment,
            "source": {
                "evidence_id": e["id"],
                "original_sha256": e["sha256"],
                "text_sha256": digest,
            },
            "timestamp_source": timestamp_source,
            "counterevidence": counter,
        }
        rid = core.uid("PREDICTION-AUDIT")
        core.execute(
            "INSERT INTO prediction_audits VALUES(?,?,?)",
            (rid, core.now(), json.dumps(record)),
        )
        core.log(
            "prediction_claim_audited",
            {"id": rid, "assessment": assessment["assessment"]},
        )
        return {"id": rid, **record}

    return {"evaluate": create}

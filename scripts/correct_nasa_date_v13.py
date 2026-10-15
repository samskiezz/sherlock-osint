"""Correct a secondary catalogue label without altering acquired source bytes."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def correct(value):
    """Retain NASA's date_created semantics rather than relabelling it publication time."""
    if isinstance(value, list):
        return [correct(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: correct(item) for key, item in value.items()}
    if (
        result.get("provider") == "nasa_images"
        and "publication_date_reported" in result
    ):
        result["catalogue_date_created_reported"] = result.pop(
            "publication_date_reported"
        )
    return result


def main():
    """Repair only derived research records and append an auditable correction event."""
    from backend import app as core

    changed = {}
    statements = [
        (
            "research_discovery",
            "SELECT rowid AS record_id,data AS value FROM research_discovery WHERE data LIKE '%publication_date_reported%' AND data LIKE '%nasa_images%'",
            "UPDATE research_discovery SET data=? WHERE rowid=?",
        ),
        (
            "research_run_jobs",
            "SELECT rowid AS record_id,data AS value FROM research_run_jobs WHERE data LIKE '%publication_date_reported%' AND data LIKE '%nasa_images%'",
            "UPDATE research_run_jobs SET data=? WHERE rowid=?",
        ),
        (
            "research_runs",
            "SELECT rowid AS record_id,data AS value FROM research_runs WHERE data LIKE '%publication_date_reported%' AND data LIKE '%nasa_images%'",
            "UPDATE research_runs SET data=? WHERE rowid=?",
        ),
        (
            "research_tasks",
            "SELECT rowid AS record_id,output AS value FROM research_tasks WHERE output LIKE '%publication_date_reported%' AND output LIKE '%nasa_images%'",
            "UPDATE research_tasks SET output=? WHERE rowid=?",
        ),
    ]
    for table, select_sql, update_sql in statements:
        count = 0
        for row in core.rows(select_sql):
            old = json.loads(row["value"])
            new = correct(old)
            if new != old:
                core.execute(update_sql, (json.dumps(new), row["record_id"]))
                count += 1
        changed[table] = count
    core.log(
        "nasa_catalogue_date_label_correction",
        {
            "records": changed,
            "reason": "NASA date_created retained literally; not an independently established publication or archive timestamp",
            "original_files_changed": False,
        },
    )
    (ROOT / "artifacts/nasa-date-label-correction-v13.json").write_text(
        json.dumps(
            {
                "records": changed,
                "original_files_changed": False,
                "correct_field": "catalogue_date_created_reported",
            },
            indent=2,
        )
    )
    print(json.dumps(changed))


if __name__ == "__main__":
    main()

"""Explicit alphabetic sums for puzzle research, not prediction or identity evidence."""

from __future__ import annotations
import hashlib
import random
import string
import unicodedata
from typing import Any

ENGLISH = {c: i + 1 for i, c in enumerate(string.ascii_lowercase)}
HEBREW = dict(
    zip(
        "אבגדהוזחטיכלמנסעפצקרשת",
        [
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            20,
            30,
            40,
            50,
            60,
            70,
            80,
            90,
            100,
            200,
            300,
            400,
        ],
    )
)
FINALS = {"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"}
GREEK = dict(
    zip(
        "αβγδεϛζηθικλμνξοπϟρστυφχψωϡ",
        [
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            20,
            30,
            40,
            50,
            60,
            70,
            80,
            90,
            100,
            200,
            300,
            400,
            500,
            600,
            700,
            800,
            900,
        ],
    )
)
GREEK.update({"ς": 200, "ϝ": 6, "ϙ": 90})
TABLES = {
    "english_ordinal": ENGLISH,
    "english_reverse": {c: 27 - v for c, v in ENGLISH.items()},
    "english_reduced": {c: 1 + (v - 1) % 9 for c, v in ENGLISH.items()},
    "english_reverse_reduced": {c: 1 + (26 - v) % 9 for c, v in ENGLISH.items()},
    "hebrew_standard": {**HEBREW, **{c: HEBREW[v] for c, v in FINALS.items()}},
    "hebrew_final_extended": {**HEBREW, **dict(zip(FINALS, [500, 600, 700, 800, 900]))},
    "hebrew_ordinal": {
        **{c: i + 1 for i, c in enumerate(HEBREW)},
        **{c: list(HEBREW).index(v) + 1 for c, v in FINALS.items()},
    },
    "greek_isopsephy": GREEK,
}
POLICY = "Alphabetic sums are many-to-one puzzle transforms. A numerical match does not establish shared identity, intentional encoding, a relationship, wrongdoing or a prediction. Modern English puzzle tables are not ancient Sumerian numerals."


def calculate(text: str, table: dict) -> dict:
    """Record original character positions and each normalised letter contribution."""
    contributions = []
    ignored = []
    for index, char in enumerate(text):
        normalized = "".join(
            c
            for c in unicodedata.normalize("NFKD", char.casefold())
            if not unicodedata.combining(c)
        )
        matched = False
        for letter in normalized:
            if letter in table:
                contributions.append(
                    {
                        "offset": index,
                        "original": char,
                        "letter": letter,
                        "value": table[letter],
                    }
                )
                matched = True
        if not matched and not char.isspace():
            ignored.append({"offset": index, "character": char})
    total = sum(c["value"] for c in contributions)
    return {
        "sum": total,
        "digital_root": 1 + (total - 1) % 9 if total else 0,
        "contributions": contributions,
        "ignored": ignored,
        "matched_letters": len(contributions),
    }


def analyse(data: dict[str, Any]) -> dict:
    """Run every displayed table automatically, preserving collisions and negative controls."""
    text = data.get("text", "")
    targets = data.get("targets", [])
    seed = int(data.get("seed", 42))
    if not isinstance(text, str) or not 1 <= len(text) <= 4000:
        raise ValueError("Use 1–4,000 original characters")
    if (
        not isinstance(targets, list)
        or len(targets) > 100
        or any(not isinstance(t, str) or not 1 <= len(t) <= 200 for t in targets)
    ):
        raise ValueError(
            "At most 100 explicit comparison strings, each 1–200 characters"
        )
    rng = random.Random(seed)
    results = []
    for name, table in TABLES.items():
        original = calculate(text, table)
        comparisons = [{"text": t, **calculate(t, table)} for t in targets]
        matches = [
            {"text": c["text"], "sum": c["sum"]}
            for c in comparisons
            if c["sum"] == original["sum"]
            and c["matched_letters"]
            and original["matched_letters"]
        ]
        n = original["matched_letters"]
        controls = []
        if n:
            alphabet = list(table)
            controls = [
                sum(table[rng.choice(alphabet)] for _ in range(min(n, 4000)))
                for _ in range(128)
            ]
        results.append(
            {
                "table": name,
                "mapping": table,
                **original,
                "comparison_count": len(comparisons),
                "matches": matches,
                "toy_controls": {
                    "sampling": "128 independent uniform-letter strings, matching the number of recognised letters; not a real-world linguistic or name population",
                    "n": len(controls),
                    "equal_sum_count": sum(v == original["sum"] for v in controls),
                    "min": min(controls) if controls else None,
                    "max": max(controls) if controls else None,
                },
                "permutation_control": "Reordering the same letters leaves every additive sum unchanged. Letter shuffling is not a meaningful negative control for these methods.",
                "validation": "PUZZLE EXPERIMENT / UNVALIDATED; no p-value or probability of prediction asserted",
            }
        )
    return {
        "input": text,
        "input_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "normalisation": "Per-character NFKD, casefold and removal of combining marks. No transliteration; original offsets preserved.",
        "results": results,
        "seed": seed,
        "tables_attempted": len(TABLES),
        "target_comparisons_attempted": len(TABLES) * len(targets),
        "control_strings_attempted": sum(r["toy_controls"]["n"] for r in results),
        "multiplicity": "All attempted tables and comparisons retained. English ordinal/reduced sums are dependent modulo nine. No independent evidential weight is assigned to repeated matches.",
        "limitations": POLICY,
    }

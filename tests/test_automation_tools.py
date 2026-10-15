"""Executable-catalogue checks plus independent mathematical, ML and safety invariants."""

import json
import math
import warnings
import numpy as np
import pytest
from backend.automation_tools import (
    CATALOGUE,
    execute,
    GRAPH_EXAMPLE,
    ML_EXAMPLE,
)
from backend.automation import Workflow, resolve, catalogue


@pytest.mark.parametrize("tool", sorted(CATALOGUE))
def test_every_registered_pure_tool_executes_strict_json(tool):
    """A named tool only counts when its real installed handler produces a bounded result."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = execute(tool, CATALOGUE[tool]["example"])
    assert result["tool"] == tool
    assert result["inputs_sha256"]
    json.dumps(result, allow_nan=False)
    assert CATALOGUE[tool]["reference"].startswith("https://")


def test_catalogue_count_classification_and_no_unimplemented_padding():
    """Keep model methods, deterministic tests and encodings honestly classified."""
    tools = catalogue()
    assert len(tools) >= 200 and len({t["id"] for t in tools}) == len(tools)
    assert all(t["status"] in ("EXECUTABLE", "EXECUTABLE_ADAPTER") for t in tools)
    assert all(t["procedure"] and t["limitations"] for t in tools)
    assert (
        len([t for t in tools if t["kind"] in ("MACHINE_LEARNING", "MODEL_INFERENCE")])
        >= 30
    )
    assert not any(
        "sokalmichener" in t["id"] for t in tools
    )  # Removed upstream; no phantom adapter.


def out(tool, **data):
    """Get a pure tool output with an explicit synthetic sampling population."""
    return execute(
        tool,
        {
            "reference_population": "Independent labelled synthetic test; arbitrary units",
            **data,
        },
    )["output"]


def test_statistics_known_vectors_not_just_library_smoke():
    """Check analytically known entropy, ranks, correlation and robust slope."""
    assert out("stats.entropy", values=[1, 1, 1, 1])["result"] == pytest.approx(2)
    assert out("stats.rankdata", values=[8, 2, 2, 5])["result"] == [4, 1.5, 1.5, 3]
    assert out("stats.pearsonr", values=[1, 2, 3, 4], comparison=[2, 4, 6, 8])[
        "result"
    ]["statistic"] == pytest.approx(1)
    assert out("stats.theilslopes", values=[1, 3, 5, 7, 9])["result"][
        "slope"
    ] == pytest.approx(2)
    assert out("stats.wasserstein_distance", values=[1, 2, 3], comparison=[11, 12, 13])[
        "result"
    ] == pytest.approx(10)
    assert out("stats.skew", values=[-2, -1, 0, 1, 2])["result"] == pytest.approx(0)


@pytest.mark.parametrize("tool", [k for k in CATALOGUE if k.startswith("distance.")])
def test_all_distances_zero_on_identical_nonconstant_vectors(tool):
    """Check metric identity; Russell–Rao instead counts shared absences as dissimilarity."""
    values = CATALOGUE[tool]["example"]["values"]
    expected = 1 - sum(values) / len(values) if tool == "distance.russellrao" else 0
    assert out(tool, values=values, comparison=values)["distance"] == pytest.approx(
        expected, abs=1e-10
    )


def test_peak_and_frequency_known_sine_wave():
    """A known 4 Hz tone must yield a 4 Hz spectral peak at a recorded 32 Hz sample rate."""
    a = [math.sin(2 * math.pi * 4 * i / 32) for i in range(128)]
    v = out("signal.periodogram", values=a, sampling_hz=32)
    assert v["frequency_hz"][int(np.argmax(v["power_density"]))] == 4
    r = out("signal.autocorrelation", values=a)
    assert r["correlation"][0] == pytest.approx(1)
    assert r["correlation"][8] > 0.9


def test_graph_cut_path_and_predicted_links_are_never_factual_edges():
    """Check known topology and explicit hypothesis labels for predicted nonedges."""
    d = GRAPH_EXAMPLE
    assert execute("graph.articulation_points", d)["output"]["result"] == ["d", "c"]
    assert execute("graph.shortest_path", d)["output"]["result"] == ["a", "c", "d", "e"]
    r = execute("graph.jaccard_coefficient", d)["output"]["result"]
    assert all(x["state"] == "HYPOTHESIS / NOT A FACTUAL EDGE" for x in r)
    assert all(
        {x["source"], x["target"]}
        not in [{e["source"], e["target"]} for e in d["edges"]]
        for x in r
    )


def test_text_exact_offsets_and_negatives():
    """Extract literals without assigning identity, ownership or authenticity."""
    text = "Cole Allen. DOI 10.1234/abc. US20030053926A1 @name 2023-12-22 https://example.org/a"
    r = execute("text.identifiers", {"text": text})["output"]["result"]
    assert all(text[x["start"] : x["end"]] == x["value"] for x in r)
    assert not any("Cole" in x["value"] for x in r)
    assert (
        out("text.unicode_controls", text="x\u202ey")["result"][0]["codepoint"]
        == "U+202E"
    )
    assert out("text.unicode_controls", text="ordinary text\n")["result"] == []
    assert (
        out("text.jaccard_words", text="alloy rocket", comparison_text="cake flour")[
            "result"
        ]
        == 0
    )
    assert (
        out("text.jaccard_words", text="alloy rocket", comparison_text="rocket alloy")[
            "result"
        ]
        == 1
    )


def test_ml_independent_holdout_and_exact_row_leakage_rejection():
    """Verify high accuracy on a separable holdout and reject observable train/test leakage."""
    d = {
        "baseline": [[float(i), float(i % 3)] for i in range(20)],
        "labels": [int(i >= 10) for i in range(20)],
        "points": [[1.5, 0.2], [18.5, 0.2]],
        "holdout_labels": [0, 1],
        "feature_names": ["synthetic x units", "synthetic y units"],
        "reference_population": "Independent deliberately separable synthetic classification study",
    }
    result = execute("ml.logistic", d)["output"]
    assert result["accuracy"] == 1 and result["no_exact_row_overlap"]
    assert result["train_rows"] == 20 and result["holdout_rows"] == 2
    with pytest.raises(ValueError, match="overlap"):
        execute("ml.logistic", {**d, "points": d["baseline"][:2]})
    # Extreme holdout values must not change the fitted training transform or clusters.
    a = execute("ml.kmeans", ML_EXAMPLE)["output"]["training_labels"]
    b = execute(
        "ml.kmeans",
        {**ML_EXAMPLE, "points": [[1000, 1000, 1000], [-1000, -1000, -1000]]},
    )["output"]["training_labels"]
    assert a == b


@pytest.mark.parametrize(
    "tool,data",
    [
        ("stats.gmean", {"values": [-1, 2, 3]}),
        ("stats.entropy", {"values": [-1, 2, 3]}),
        ("stats.describe", {"values": [1, float("inf"), 3]}),
        ("stats.pearsonr", {"values": [1, 2, 3], "comparison": [1, 2, 3, 4]}),
        ("signal.periodogram", {"values": [1, 2, 3]}),
        ("signal.periodogram", {"values": list(range(20)), "sampling_hz": 0}),
        ("graph.pagerank", {"nodes": ["a", "a"], "edges": []}),
        (
            "graph.pagerank",
            {"nodes": ["a", "b"], "edges": [{"source": "a", "target": "x"}]},
        ),
        ("distance.jaccard", {"values": [0.5, 1, 0], "comparison": [1, 0, 1]}),
        ("text.tfidf_similarity", {"text": "a", "texts": ["only one document"]}),
        ("text.token_spans", {"text": "a" * 16001}),
        ("cipher.hex", {"text": "not hex"}),
        ("ml.logistic", {"baseline": [[1, 2]], "points": [[1, 2]]}),
    ],
)
def test_invalid_inputs_fail_visibly(tool, data):
    """Reject invalid domains and resource-bound violations without fabricated scores."""
    with pytest.raises((ValueError, TypeError, KeyError)):
        out(tool, **data)


def test_workflow_cycles_unknown_tools_implicit_references_and_bounds():
    """Only explicit acyclic allowlisted procedures can be authorised."""
    base = {
        "name": "Test",
        "objective": "Bounded synthetic workflow",
        "authorisation": "Owned synthetic data",
    }
    for steps in [
        [{"id": "a", "tool": "shell.exec", "inputs": {"command": "anything"}}],
        [{"id": "a", "tool": "text.word_frequency", "depends_on": ["b"]}],
        [
            {"id": "a", "tool": "text.word_frequency"},
            {"id": "a", "tool": "text.token_spans"},
        ],
        [
            {"id": "a", "tool": "text.word_frequency"},
            {
                "id": "b",
                "tool": "text.token_spans",
                "inputs": {"text": {"$ref": "a.output"}},
            },
        ],
    ]:
        with pytest.raises(ValueError):
            Workflow(**base, steps=steps)
    assert resolve(
        {"text": {"$ref": "read.output.text"}},
        {"read": {"output": {"text": "actual quoted source"}}},
        {},
    ) == {"text": "actual quoted source"}
    assert resolve(
        {"evidence_id": {"$binding": "evidence_id"}}, {}, {"evidence_id": "EV-1"}
    ) == {"evidence_id": "EV-1"}
    with pytest.raises(ValueError):
        resolve({"$ref": "x.output.missing"}, {"x": {"output": {}}}, {})
    with pytest.raises(ValueError):
        execute("__import__", {})

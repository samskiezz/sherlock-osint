"""Determinism, held-out controls, hand-calculated distances and pathological inputs."""

import copy
import math
import pytest
from backend.learned_anomalies import run, EXAMPLE, METHODS


@pytest.mark.parametrize(
    "method", ["isolation_forest", "lof", "one_class_svm", "pca", "mahalanobis"]
)
def test_detectors_score_heldout_far_point_above_benign_control_reproducibly(method):
    data = copy.deepcopy(EXAMPLE)
    data["points"] = [[0.01, 0.01], [8, -9]]
    first = run(method, data)
    second = run(method, data)
    assert first == second
    assert first["scores"][1] > first["scores"][0]
    assert 1 in first["outlier_indices"] and 0 not in first["outlier_indices"]
    assert first["parameters"]["baseline_mean"] == second["parameters"]["baseline_mean"]
    assert first["validation"] == "EXPLORATORY / HUMAN REVIEW REQUIRED"


def test_mahalanobis_one_dimension_matches_manual_population_variance():
    baseline = [[float(x)] for x in range(11)]
    result = run(
        "mahalanobis",
        {
            "baseline": baseline,
            "points": [[15]],
            "feature_names": ["x units"],
            "reference_population": "uniform deterministic fixture",
        },
    )
    variance = sum((x - 5) ** 2 for x in range(11)) / 11
    assert result["scores"] == pytest.approx([10 / math.sqrt(variance)])


def test_standardisation_does_not_fit_the_scored_observations():
    data = copy.deepcopy(EXAMPLE)
    a = run("isolation_forest", data)
    data["points"] = [[100000, 100000]]
    b = run("isolation_forest", data)
    assert a["parameters"]["baseline_mean"] == b["parameters"]["baseline_mean"]
    assert a["parameters"]["baseline_scale"] == b["parameters"]["baseline_scale"]


def test_grubbs_single_outlier_and_zero_dispersion():
    a = run("grubbs", METHODS["grubbs"][3])
    assert a["outlier_indices"] == [9] and a["G"] > a["critical_G"]
    b = run("grubbs", {"values": [5, 5, 5], "reference_population": "constant fixture"})
    assert not b["defined"] and not b["outlier_indices"]


@pytest.mark.parametrize(
    "change",
    [
        {"reference_population": ""},
        {"feature_names": []},
        {"baseline": [[1, 1]] * 20},
        {"points": [[float("nan"), 0]]},
        {"points": [[1, 2, 3]]},
        {"seed": -1},
    ],
)
def test_bad_baselines_units_shapes_and_nonfinite_values_are_rejected(change):
    with pytest.raises(ValueError):
        run("isolation_forest", {**EXAMPLE, **change})


def test_covariance_singularity_pca_dimensions_and_neighbours_are_rejected():
    with pytest.raises(ValueError):
        run("mahalanobis", {**EXAMPLE, "baseline": [[x, 2 * x] for x in range(20)]})
    with pytest.raises(ValueError):
        run("pca", {**EXAMPLE, "components": 2})
    with pytest.raises(ValueError):
        run("lof", {**EXAMPLE, "n_neighbors": 20})

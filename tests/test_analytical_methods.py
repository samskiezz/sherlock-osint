import math
import pytest
from backend.analytical_methods import run, METHODS


def path(*nodes):
    return {
        "nodes": list(nodes),
        "edges": [{"source": a, "target": b} for a, b in zip(nodes, nodes[1:])],
    }


def test_brandes_normalisation_and_disconnected_closeness():
    data = path("a", "b", "c")
    assert run("betweenness", data)["centrality"] == {"a": 0, "b": 1, "c": 0}
    assert run("closeness", data)["centrality"] == {
        "a": pytest.approx(2 / 3),
        "b": 1,
        "c": pytest.approx(2 / 3),
    }
    data["nodes"].append("isolated")
    r = run("closeness", data)["centrality"]
    assert r["b"] == pytest.approx(2 / 3) and r["isolated"] == 0
    assert run("network", data)["components"] == [["a", "b", "c"], ["isolated"]]


def test_core_decomposition_triangle_with_tail_and_eigenvector():
    data = path("a", "b", "c", "d")
    data["edges"].append({"source": "c", "target": "a"})
    assert run("kcore", data)["core_number"] == {"d": 1, "a": 2, "b": 2, "c": 2}
    r = run("eigenvector", path("a", "b", "c"))
    assert r["converged"]
    assert r["centrality"]["b"] == pytest.approx(1 / math.sqrt(2), abs=1e-8)
    assert r["centrality"]["a"] == pytest.approx(0.5, abs=1e-8)
    with pytest.raises(ValueError):
        run("network", {"nodes": ["a"], "edges": [{"source": "a", "target": "a"}]})


def test_duplicate_edges_collapse_and_graph_limits():
    d = path("a", "b")
    d["edges"] *= 3
    assert run("network", d)["simple_edge_count"] == 1
    with pytest.raises(ValueError):
        run("network", {"nodes": ["a", "a"], "edges": []})
    with pytest.raises(ValueError):
        run("network", {"nodes": [str(i) for i in range(301)], "edges": []})


def test_js_and_ks_known_extreme_and_identical_distributions():
    assert (
        run("js", {"p": [1, 0], "q": [0, 1], "reference_population": "fixture"})[
            "divergence_bits"
        ]
        == 1
    )
    assert (
        run(
            "js", {"p": [0.5, 0.5], "q": [0.5, 0.5], "reference_population": "fixture"}
        )["divergence_bits"]
        == 0
    )
    assert (
        run(
            "ks",
            {
                "values": [1, 2, 3],
                "comparison": [4, 5, 6],
                "reference_population": "fixture",
            },
        )["statistic_D"]
        == 1
    )
    assert (
        run(
            "ks",
            {
                "values": [1, 1, 3],
                "comparison": [1, 1, 3],
                "reference_population": "fixture",
            },
        )["statistic_D"]
        == 0
    )
    with pytest.raises(ValueError):
        run("js", {"p": [2, 0], "q": [0, 1], "reference_population": "fixture"})


def test_cusum_and_ewma_detect_shift_not_constant_baseline():
    d = {
        "values": [10] * 10,
        "reference_population": "ordered synthetic fixture",
        "baseline_mean": 10,
        "baseline_sd": 1,
    }
    for method in ("cusum", "ewma"):
        assert not any(x["signal"] for x in run(method, d)["sequence"])
        r = run(method, {**d, "values": [10] * 3 + [15] * 10})
        assert any(x["signal"] for x in r["sequence"])
    r = run("ewma", {**d, "values": [10, 12], "alpha": 0.5})
    assert r["sequence"][1]["ewma"] == 11
    with pytest.raises(ValueError):
        run("cusum", {**d, "baseline_sd": 0})


def test_zscore_degenerate_and_benford_nonzero_digit_handling():
    r = run("zscore", {"values": [1, 1, 1], "reference_population": "fixture"})
    assert r["scores"] == [None] * 3 and not r["outlier_indices"]
    r = run(
        "benford", {"values": [0, 0.0002, -30, 4e20], "reference_population": "fixture"}
    )
    assert r["excluded_zeros"] == 1 and r["n_nonzero"] == 3
    assert [v["digit"] for v in r["counts"] if v["observed"]] == [2, 3, 4]
    assert r["p_value"] is None


def test_dbscan_density_noise_and_border_reassignment():
    d = {
        "points": [[0, 0], [0, 0.1], [0.1, 0], [9, 9]],
        "eps": 0.2,
        "min_samples": 3,
        "reference_population": "fixture",
    }
    r = run("dbscan", d)
    assert r["labels"] == [0, 0, 0, -1] and r["noise_indices"] == [3]
    # First point is visited as noise, then becomes a reachable border point.
    r = run(
        "dbscan",
        {
            "points": [[0], [0.1], [0.2]],
            "eps": 0.11,
            "min_samples": 3,
            "reference_population": "fixture",
        },
    )
    assert r["labels"] == [0, 0, 0] and r["core_indices"] == [1]
    with pytest.raises(ValueError):
        run("dbscan", {**d, "eps": float("nan")})


@pytest.mark.parametrize("method", ["zscore", "cusum", "ewma", "benford", "ks"])
def test_baseline_required_and_nonfinite_rejected(method):
    with pytest.raises(ValueError):
        run(method, {"values": [1, 2, 3]})
    with pytest.raises(ValueError):
        run(method, {"values": [1, float("inf")], "reference_population": "fixture"})


def test_cipher_adapters_preserve_offsets_and_attempt_counts():
    r = run("kasiski", {"text": "ABCABCABCABC"})
    assert r["normalised_input"] == "ABCABCABCABC"
    assert r["repeats"][0]["offsets_in_letters_only"] == [0, 3, 6, 9]
    assert (
        run("chi_squared", {"text": "Wklv lv d orqj hqjolvk whvw phvvdjh"})["attempts"]
        == 26
    )
    assert run("friedman", {"text": "SHORT"})["estimated_key_length"] is None


def test_louvain_two_clusters_seeded_and_isolated_cliques():
    data = {
        "nodes": ["a", "b", "c", "d", "e", "f", "i"],
        "edges": [
            {"source": a, "target": b}
            for a, b in [
                ("a", "b"),
                ("a", "c"),
                ("b", "c"),
                ("d", "e"),
                ("d", "f"),
                ("e", "f"),
            ]
        ],
    }
    r = run("louvain", data)
    assert r["communities"] == [["a", "b", "c"], ["d", "e", "f"], ["i"]]
    assert r["modularity"] == pytest.approx(0.5)
    assert run("louvain", data) == r
    assert sorted(run("cliques", data)["maximal_cliques"]) == [
        ["a", "b", "c"],
        ["d", "e", "f"],
        ["i"],
    ]
    with pytest.raises(ValueError):
        run("louvain", {**data, "resolution": 0})


def test_graph_scores_agree_with_independent_networkx_on_seeded_graphs():
    import networkx as nx

    for seed in range(6):
        g = nx.gnp_random_graph(12, 0.2, seed=seed)
        data = {
            "nodes": [str(n) for n in g.nodes],
            "edges": [{"source": str(a), "target": str(b)} for a, b in g.edges],
        }
        for method, oracle, key in [
            ("betweenness", nx.betweenness_centrality, "centrality"),
            ("closeness", nx.closeness_centrality, "centrality"),
            ("kcore", nx.core_number, "core_number"),
        ]:
            actual = run(method, data)[key]
            expected = oracle(g)
            for node, value in expected.items():
                assert actual[str(node)] == pytest.approx(value)


def test_feed_parser_rejects_entity_expansion():
    from backend import scheduler
    from defusedxml.common import DefusedXmlException

    xml = b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><rss><item><title>&secret;</title></item></rss>'
    with pytest.raises(DefusedXmlException):
        scheduler.ET.fromstring(xml)

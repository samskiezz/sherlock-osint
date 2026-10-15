"""Bounded, deterministic analytics. Baselines and input snapshots are mandatory."""

import json
from typing import Any
import math
import statistics
from collections import Counter, deque

GRAPH_METHODS = {
    "network",
    "betweenness",
    "closeness",
    "eigenvector",
    "kcore",
    "louvain",
    "cliques",
}
# name, reference, explicit procedure, editable example
METHODS = {
    "louvain": (
        "Louvain community detection",
        "https://doi.org/10.1088/1742-5468/2008/10/P10008",
        "NetworkX 3.7 Louvain modularity optimisation; seeded RNG, explicit resolution and bounded levels; communities are topological, not associations of guilt.",
        {"board_id": "", "seed": 42, "resolution": 1.0},
    ),
    "cliques": (
        "Clique detection",
        "https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.clique.find_cliques.html",
        "NetworkX maximal cliques; bounded to 100 nodes and 1,000 enumerated results, explicit truncation if more exist.",
        {"board_id": ""},
    ),
    "network": (
        "Social Network Analysis",
        "https://networkx.org/documentation/stable/reference/algorithms/component.html",
        "Undirected simple graph: degree and connected components; parallel edges collapsed, loops rejected.",
        {"board_id": ""},
    ),
    "betweenness": (
        "Betweenness centrality",
        "https://doi.org/10.1080/0022250X.2001.9990249",
        "Brandes shortest-path dependency accumulation; undirected normalisation 2/((n-1)(n-2)).",
        {"board_id": ""},
    ),
    "closeness": (
        "Closeness centrality",
        "https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.centrality.closeness_centrality.html",
        "Shortest-path closeness with Wasserman–Faust disconnected-component correction.",
        {"board_id": ""},
    ),
    "eigenvector": (
        "Eigenvector centrality",
        "https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.centrality.eigenvector_centrality.html",
        "Power iteration on adjacency + identity, L2 normalisation, convergence tolerance 1e-9; reject nonconvergence.",
        {"board_id": ""},
    ),
    "kcore": (
        "K-core decomposition",
        "https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.core.core_number.html",
        "Iterative minimum-degree peeling with neighbour degree updates above current core number.",
        {"board_id": ""},
    ),
    "zscore": (
        "Z-score analysis",
        "https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm",
        "Sample mean and sample standard deviation; report |Z| > supplied threshold; zero dispersion undefined.",
        {
            "values": [10, 11, 12, 13, 100],
            "reference_population": "Synthetic fixture; not case evidence",
            "threshold": 3,
        },
    ),
    "cusum": (
        "CUSUM",
        "https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm",
        "Two-sided cumulative sums with fixed user-supplied baseline mean, standard deviation, allowance k and threshold h.",
        {
            "values": [10, 10, 11, 13, 14, 15],
            "reference_population": "Synthetic ordered fixture",
            "baseline_mean": 10,
            "baseline_sd": 1,
            "allowance": 0.5,
            "threshold": 5,
        },
    ),
    "ewma": (
        "EWMA control charts",
        "https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm",
        "Exponentially weighted moving average with time-dependent control limits and explicit fixed baseline.",
        {
            "values": [10, 10, 11, 13, 14, 15],
            "reference_population": "Synthetic ordered fixture",
            "baseline_mean": 10,
            "baseline_sd": 1,
            "alpha": 0.2,
            "limit_sigma": 3,
        },
    ),
    "benford": (
        "Benford’s Law analysis",
        "https://doi.org/10.2307/984802",
        "First nonzero decimal digit counts compared with log10(1+1/d); counts and Pearson discrepancy only, no guilt or significance assertion.",
        {
            "values": [1, 10, 20, 30, 40, 50, 60, 70, 80, 90],
            "reference_population": "Synthetic example; Benford suitability must be assessed",
        },
    ),
    "js": (
        "Jensen–Shannon divergence",
        "https://doi.org/10.1109/18.61115",
        "Equal-weight mixture, base-2 KL terms; vectors must be nonnegative, finite, same length and normalised.",
        {
            "p": [1, 0],
            "q": [0, 1],
            "reference_population": "Synthetic distribution comparison",
        },
    ),
    "ks": (
        "Kolmogorov–Smirnov testing",
        "https://www.itl.nist.gov/div898/handbook/eda/section3/eda35g.htm",
        "Exact empirical two-sample maximum CDF distance; descriptive D only, no approximate p-value or significance claim.",
        {
            "values": [1, 2, 3],
            "comparison": [4, 5, 6],
            "reference_population": "Synthetic two-sample comparison",
        },
    ),
    "dbscan": (
        "DBSCAN",
        "https://www.dbs.ifi.lmu.de/Publikationen/Papers/KDD-96.final.frame.pdf",
        "Euclidean radius neighbourhoods with inclusive self-count, deterministic density reachability and noise labels; no automatic criminal groups.",
        {
            "points": [[0, 0], [0, 0.1], [0.1, 0], [9, 9]],
            "eps": 0.2,
            "min_samples": 3,
            "reference_population": "Synthetic coordinates; units and scaling supplied by analyst",
        },
    ),
    "kasiski": (
        "Kasiski examination",
        "https://en.wikipedia.org/wiki/Kasiski_examination",
        "Existing cipher engine: repeated 3–5 letter sequences, exact normalised offsets and factor counts.",
        {"text": "ABCABCABCABC"},
    ),
    "friedman": (
        "Friedman test",
        "https://en.wikipedia.org/wiki/Index_of_coincidence",
        "Existing cipher engine: English index-of-coincidence approximation; undefined short-text estimate reported.",
        {"text": "A LONGER ENGLISH TEST INPUT FOR COINCIDENCE ANALYSIS"},
    ),
    "chi_squared": (
        "Chi-squared cipher scoring",
        "https://en.wikipedia.org/wiki/Frequency_analysis",
        "Existing cipher engine: rank every Caesar shift using English monograms; preserve all 26 attempted parameters.",
        {"text": "Wklv lv d frqyhqwlrqdo hqjolvk whvw phvvdjh"},
    ),
}


from .learned_anomalies import METHODS as LEARNED_METHODS

METHODS.update(LEARNED_METHODS)


def numbers(value: list[Any], minimum: int = 1, maximum: int = 10000) -> list[float]:
    """Validate bounded finite numerical observations."""
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"Use {minimum}–{maximum} numerical observations")
    out = [float(x) for x in value]
    if any(not math.isfinite(x) for x in out):
        raise ValueError("All observations must be finite")
    return out


def graph(method: str, data: dict[str, Any]) -> dict[str, Any]:
    """Calculate the requested score on an explicit, bounded simple graph."""
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 300 or len(edges) > 3000:
        raise ValueError("Graph limit: 1–300 nodes and 3,000 edges")
    if any(not isinstance(n, str) or not n or len(n) > 200 for n in nodes) or len(
        set(nodes)
    ) != len(nodes):
        raise ValueError("Node IDs must be unique nonempty strings")
    adj = {n: set() for n in nodes}
    for e in edges:
        a, b = e["source"], e["target"]
        if a not in adj or b not in adj or a == b:
            raise ValueError("Edges require distinct declared endpoints")
        adj[a].add(b)
        adj[b].add(a)
    n = len(nodes)
    if method in ("louvain", "cliques"):
        import networkx as nx

        g = nx.Graph()
        g.add_nodes_from(nodes)
        g.add_edges_from((a, b) for a in nodes for b in adj[a])
        if method == "cliques":
            if n > 100:
                raise ValueError("Exact clique enumeration is limited to 100 nodes")
            from itertools import islice

            groups = list(islice(nx.find_cliques(g), 1001))
            return {
                "maximal_cliques": [sorted(c) for c in groups[:1000]],
                "truncated": len(groups) > 1000,
                "library": "NetworkX " + nx.__version__,
                "warning": "Clique enumeration can grow exponentially. Co-membership is a graph property, not proof of collusion.",
            }
        resolution = float(data.get("resolution", 1))
        seed = int(data.get("seed", 42))
        if not math.isfinite(resolution) or resolution <= 0 or not 0 <= seed < 2**32:
            raise ValueError("Positive finite resolution and uint32 seed required")
        groups = (
            nx.community.louvain_communities(
                g, resolution=resolution, seed=seed, max_level=20
            )
            if g.number_of_edges()
            else [{v} for v in nodes]
        )
        return {
            "communities": sorted([sorted(c) for c in groups]),
            "modularity": nx.community.modularity(g, groups, resolution=resolution)
            if g.number_of_edges()
            else None,
            "resolution": resolution,
            "seed": seed,
            "max_levels": 20,
            "library": "NetworkX " + nx.__version__,
            "warning": "Heuristic partition depends on topology, resolution, seed and missing records; it does not verify hidden relationships or a common research team.",
        }
    common = {
        "node_count": n,
        "simple_edge_count": sum(map(len, adj.values())) // 2,
        "model": "UNDIRECTED SIMPLE GRAPH",
        "warning": "Connectivity does not establish identity, motive, wrongdoing or causal influence. Only included, cited relationships are analysed.",
    }
    if method in ("network", "closeness", "betweenness"):
        bet = dict.fromkeys(nodes, 0.0)
        close = {}
        components = []
        seen = set()
        for s in nodes:
            order = []
            pred = {v: [] for v in nodes}
            sigma = dict.fromkeys(nodes, 0.0)
            sigma[s] = 1.0
            dist = {s: 0}
            queue = deque([s])
            while queue:
                v = queue.popleft()
                order.append(v)
                for w in sorted(adj[v]):
                    if w not in dist:
                        dist[w] = dist[v] + 1
                        queue.append(w)
                    if dist[w] == dist[v] + 1:
                        sigma[w] += sigma[v]
                        pred[w].append(v)
            r = len(dist) - 1
            total = sum(dist.values())
            close[s] = (r / total) * (r / (n - 1)) if total and n > 1 else 0.0
            if s not in seen:
                components.append(sorted(dist))
                seen.update(dist)
            dependency = dict.fromkeys(nodes, 0.0)
            for w in reversed(order):
                for v in pred[w]:
                    dependency[v] += sigma[v] / sigma[w] * (1 + dependency[w])
                if w != s:
                    bet[w] += dependency[w]
        if method == "network":
            return {
                **common,
                "degree": {v: len(adj[v]) for v in nodes},
                "components": components,
            }
        if method == "closeness":
            return {
                **common,
                "centrality": close,
                "disconnected_correction": "Wasserman–Faust",
            }
        return {
            **common,
            "centrality": {
                v: bet[v] / ((n - 1) * (n - 2)) if n > 2 else 0.0 for v in nodes
            },
            "normalised": True,
        }
    if method == "kcore":
        degree = {v: len(adj[v]) for v in nodes}
        result = {}
        while degree:
            v = min(degree, key=lambda x: (degree[x], x))
            k = degree.pop(v)
            result[v] = k
            for w in adj[v]:
                if w in degree and degree[w] > k:
                    degree[w] -= 1
        return {**common, "core_number": result}
    x = {v: 1 / math.sqrt(n) for v in nodes}
    for iteration in range(1, 2001):
        y = {v: x[v] + sum(x[w] for w in adj[v]) for v in nodes}
        norm = math.sqrt(sum(t * t for t in y.values()))
        y = {v: t / norm for v, t in y.items()}
        delta = sum(abs(y[v] - x[v]) for v in nodes)
        x = y
        if delta < 1e-9:
            return {
                **common,
                "centrality": x,
                "iterations": iteration,
                "converged": True,
                "warning": common["warning"]
                + " Disconnected components may have nonunique or suppressed eigenvector weights.",
            }
    raise ValueError("Eigenvector iteration did not converge; no score asserted")


def run(method: str, data: dict[str, Any]) -> dict[str, Any]:
    """Execute a reproducible analysis with disclosed baseline assumptions."""
    if method in LEARNED_METHODS:
        from .learned_anomalies import run as learned

        return learned(method, data)
    if method in GRAPH_METHODS:
        return graph(method, data)
    if method in ("kasiski", "friedman", "chi_squared"):
        from .extended_ciphers import run as cipher

        text = data["text"]
        if not isinstance(text, str) or not 1 <= len(text) <= 10000:
            raise ValueError("Use 1–10,000 text characters")
        return json.loads(
            cipher(text, "caesar_scan" if method == "chi_squared" else method, {})
        )
    population = data.get("reference_population")
    if not isinstance(population, str) or not population.strip():
        raise ValueError("Describe the reference population, sampling and units")
    common = {
        "reference_population": population,
        "warning": "Exploratory result; assess selection bias, baseline suitability, dependence and benign explanations. An anomaly is not proof of wrongdoing.",
    }
    if method == "js":
        p = numbers(data["p"])
        q = numbers(data["q"])
        if (
            len(p) != len(q)
            or any(x < 0 for x in p + q)
            or abs(sum(p) - 1) > 1e-9
            or abs(sum(q) - 1) > 1e-9
        ):
            raise ValueError(
                "Equal-length nonnegative distributions must each sum to one"
            )
        m = [(a + b) / 2 for a, b in zip(p, q)]
        score = sum(
            x * math.log2(x / y) / 2
            for vector in (p, q)
            for x, y in zip(vector, m)
            if x
        )
        return {**common, "divergence_bits": score, "p": p, "q": q}
    if method == "dbscan":
        points = data["points"]
        if not isinstance(points, list) or not 1 <= len(points) <= 500:
            raise ValueError("Use 1–500 points")
        points = [numbers(p, 1, 10) for p in points]
        dims = len(points[0])
        eps = float(data["eps"])
        minimum = int(data["min_samples"])
        if (
            any(len(p) != dims for p in points)
            or not math.isfinite(eps)
            or eps <= 0
            or not 1 <= minimum <= len(points)
        ):
            raise ValueError(
                "Common dimensions, finite positive radius and valid min_samples required"
            )
        neighbours = [
            [j for j, q in enumerate(points) if math.dist(p, q) <= eps] for p in points
        ]
        labels = [None] * len(points)
        cluster = 0
        for i in range(len(points)):
            if labels[i] is not None:
                continue
            if len(neighbours[i]) < minimum:
                labels[i] = -1
                continue
            labels[i] = cluster
            queue = deque(neighbours[i])
            visited = set(neighbours[i])
            while queue:
                j = queue.popleft()
                if labels[j] == -1:
                    labels[j] = cluster
                if labels[j] is not None:
                    continue
                labels[j] = cluster
                if len(neighbours[j]) >= minimum:
                    for k in neighbours[j]:
                        if k not in visited:
                            visited.add(k)
                            queue.append(k)
            cluster += 1
        return {
            **common,
            "labels": labels,
            "cluster_count": cluster,
            "noise_indices": [i for i, l in enumerate(labels) if l == -1],
            "core_indices": [i for i, v in enumerate(neighbours) if len(v) >= minimum],
            "distance": "Euclidean; input units, dimensions and scaling preserved",
        }
    v = numbers(data["values"], 2)
    if method == "ks":
        q = sorted(numbers(data["comparison"], 2))
        a = sorted(v)
        i = j = 0
        d = 0
        for t in sorted(set(a + q)):
            while i < len(a) and a[i] <= t:
                i += 1
            while j < len(q) and q[j] <= t:
                j += 1
            d = max(d, abs(i / len(a) - j / len(q)))
        return {
            **common,
            "statistic_D": d,
            "sample_sizes": [len(a), len(q)],
            "p_value": None,
            "warning": common["warning"]
            + " Ties and small samples require an appropriate null distribution; no significance decision performed.",
        }
    if method == "benford":
        count = Counter()
        for x in v:
            if x:
                digit = int(format(abs(x), ".15e")[0])
                count[digit] += 1
        n = sum(count.values())
        if not n:
            raise ValueError("At least one nonzero observation required")
        rows = [
            {"digit": d, "observed": count[d], "expected": n * math.log10(1 + 1 / d)}
            for d in range(1, 10)
        ]
        return {
            **common,
            "counts": rows,
            "n_nonzero": n,
            "excluded_zeros": len(v) - n,
            "pearson_discrepancy": sum(
                (r["observed"] - r["expected"]) ** 2 / r["expected"] for r in rows
            ),
            "p_value": None,
            "warning": common["warning"]
            + " Assigned identifiers, bounded values and selected prices often do not follow Benford. No fraud inference.",
        }
    if method == "zscore":
        mean = statistics.mean(v)
        sd = statistics.stdev(v)
        threshold = float(data.get("threshold", 3))
        if not math.isfinite(threshold) or threshold <= 0:
            raise ValueError("Positive finite threshold required")
        z = [(x - mean) / sd if sd else None for x in v]
        return {
            **common,
            "mean": mean,
            "sample_sd": sd,
            "scores": z,
            "threshold": threshold,
            "outlier_indices": [
                i for i, x in enumerate(z) if x is not None and abs(x) > threshold
            ],
        }
    mean = float(data["baseline_mean"])
    sd = float(data["baseline_sd"])
    if not math.isfinite(mean) or not math.isfinite(sd) or sd <= 0:
        raise ValueError("Finite baseline mean and positive SD required")
    if method == "cusum":
        allowance = float(data.get("allowance", 0.5))
        threshold = float(data.get("threshold", 5))
        if (
            not math.isfinite(allowance)
            or allowance < 0
            or not math.isfinite(threshold)
            or threshold <= 0
        ):
            raise ValueError(
                "Finite nonnegative allowance and positive threshold required"
            )
        plus = minus = 0
        sequence = []
        for i, x in enumerate(v):
            z = (x - mean) / sd
            plus = max(0, plus + z - allowance)
            minus = max(0, minus - z - allowance)
            sequence.append(
                {
                    "index": i,
                    "upper_cusum": plus,
                    "lower_cusum": minus,
                    "signal": max(plus, minus) > threshold,
                }
            )
        return {
            **common,
            "sequence": sequence,
            "baseline_mean": mean,
            "baseline_sd": sd,
            "allowance": allowance,
            "threshold": threshold,
            "reset_on_signal": False,
        }
    if method == "ewma":
        alpha = float(data.get("alpha", 0.2))
        limit = float(data.get("limit_sigma", 3))
        if not 0 < alpha <= 1 or not math.isfinite(limit) or limit <= 0:
            raise ValueError("alpha in (0,1] and positive finite limit required")
        z = mean
        sequence = []
        for i, x in enumerate(v):
            z = alpha * x + (1 - alpha) * z
            width = (
                limit
                * sd
                * math.sqrt(alpha / (2 - alpha) * (1 - (1 - alpha) ** (2 * (i + 1))))
            )
            sequence.append(
                {
                    "index": i,
                    "ewma": z,
                    "lower": mean - width,
                    "upper": mean + width,
                    "signal": abs(z - mean) > width,
                }
            )
        return {
            **common,
            "sequence": sequence,
            "alpha": alpha,
            "baseline_mean": mean,
            "baseline_sd": sd,
            "limit_sigma": limit,
        }
    raise ValueError("Unsupported analytical method")

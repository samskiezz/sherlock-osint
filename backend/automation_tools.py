"""Typed, bounded analytical tools for evidence workflows; no code or shell evaluation.

The catalogue separates machine learning from classical transforms and statistics.
Engineering documentation is not evidence of case-level accuracy.
"""

from __future__ import annotations
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from typing import Any

import numpy as np
import scipy
from scipy import stats, signal
from scipy.spatial import distance
import networkx as nx
import sklearn
from threadpoolctl import threadpool_limits

VERSION = "0.11.0"
CATALOGUE: dict[str, dict[str, Any]] = {}
HANDLERS: dict[str, Any] = {}
DISCLAIMER = (
    "Exploratory computation, not a finding of wrongdoing, identity, causality, an authenticated message or image authenticity. "
    "Assess sampling, dependence, multiple testing, source integrity and benign explanations. Similarity is not confidence."
)


def clean(value: Any) -> Any:
    """Convert numerical output to strict JSON; disclose undefined values as null."""
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [clean(v) for v in value]
    return value


def add(
    key: str,
    title: str,
    family: str,
    reference: str,
    example: dict,
    handler: Any,
    procedure: str,
    limitations: str = DISCLAIMER,
    kind: str = "DETERMINISTIC_ANALYSIS",
) -> None:
    """Register an explicit callable procedure and its reproducible example."""
    if key in CATALOGUE:
        raise ValueError("Duplicate tool identifier: " + key)
    CATALOGUE[key] = dict(
        id=key,
        title=title,
        family=family,
        kind=kind,
        reference=reference,
        example=example,
        procedure=procedure,
        limitations=limitations,
        status="EXECUTABLE",
        version=VERSION,
    )
    HANDLERS[key] = handler


def vector(
    data: dict, key: str = "values", minimum: int = 3, maximum: int = 1000
) -> np.ndarray:
    """Require a finite bounded one-dimensional sample and its reference population."""
    if (
        not isinstance(data.get("reference_population"), str)
        or not data["reference_population"].strip()
    ):
        raise ValueError(
            "Describe reference_population, selection, independence and units"
        )
    value = data.get(key)
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{key} requires {minimum}–{maximum} finite numbers")
    result = np.asarray(value, dtype=float)
    if result.ndim != 1 or not np.isfinite(result).all():
        raise ValueError("Require a finite one-dimensional numeric sample")
    return result


def result_tuple(value: Any) -> Any:
    """Keep labelled SciPy statistics and p-values without claiming significance."""
    if hasattr(value, "statistic"):
        return clean(
            {"statistic": value.statistic, "pvalue": getattr(value, "pvalue", None)}
        )
    if hasattr(value, "_asdict"):
        return clean(
            {k: v for k, v in value._asdict().items() if not k.startswith("_")}
        )
    return clean(value)


SAMPLE = {
    "values": [2, 3, 5, 6, 8, 9, 11, 14, 18, 21, 25, 30],
    "comparison": [3, 4, 7, 8, 9, 12, 13, 15, 21, 23, 27, 33],
    "reference_population": "Labelled synthetic independent samples; arbitrary units; not case observations",
}
STATS_SINGLE = {
    "describe": (
        "Descriptive sample moments",
        lambda a: result_tuple(stats.describe(a)),
    ),
    "skew": ("Bias-corrected skewness", lambda a: stats.skew(a, bias=False)),
    "kurtosis": (
        "Bias-corrected excess kurtosis",
        lambda a: stats.kurtosis(a, bias=False),
    ),
    "trim_mean": ("Ten-percent trimmed mean", lambda a: stats.trim_mean(a, 0.1)),
    "gmean": ("Geometric mean", stats.gmean),
    "hmean": ("Harmonic mean", stats.hmean),
    "variation": (
        "Sample coefficient of variation",
        lambda a: stats.variation(a, ddof=1),
    ),
    "sem": ("Standard error of sample mean", stats.sem),
    "iqr": ("Interquartile range", stats.iqr),
    "mad": ("Median absolute deviation", stats.median_abs_deviation),
    "rankdata": ("Average ranks with ties", stats.rankdata),
    "percentileofscore": (
        "Empirical percentile ranks",
        lambda a: stats.percentileofscore(a, a),
    ),
    "shapiro": ("Shapiro–Wilk normality test", stats.shapiro),
    "normaltest": ("D’Agostino–Pearson normality test", stats.normaltest),
    "jarque_bera": ("Jarque–Bera normality test", stats.jarque_bera),
    "skewtest": ("Skewness normality component test", stats.skewtest),
    "kurtosistest": ("Kurtosis normality component test", stats.kurtosistest),
    "ttest_1samp": (
        "One-sample Student t test against zero",
        lambda a: stats.ttest_1samp(a, 0),
    ),
    "wilcoxon": ("Wilcoxon signed-rank test against zero", stats.wilcoxon),
    "theilslopes": ("Theil–Sen robust slope", stats.theilslopes),
    "siegelslopes": ("Siegel repeated-median slope", stats.siegelslopes),
    "entropy": (
        "Shannon entropy of nonnegative weights",
        lambda a: stats.entropy(a, base=2),
    ),
    "differential_entropy": (
        "Vasicek differential entropy",
        stats.differential_entropy,
    ),
    "ecdf": (
        "Empirical cumulative distribution",
        lambda a: {
            "quantiles": stats.ecdf(a).cdf.quantiles,
            "probabilities": stats.ecdf(a).cdf.probabilities,
        },
    ),
    "winsorize": (
        "Ten-percent Winsorisation",
        lambda a: stats.mstats.winsorize(a, limits=(0.1, 0.1)).data,
    ),
    "quantiles": (
        "Interpolated sample quantiles",
        lambda a: np.quantile(a, [0.025, 0.25, 0.5, 0.75, 0.975]),
    ),
}
STATS_PAIR = {
    "pearsonr": ("Pearson product-moment correlation", stats.pearsonr),
    "spearmanr": ("Spearman rank correlation", stats.spearmanr),
    "kendalltau": ("Kendall tau-b correlation", stats.kendalltau),
    "ttest_ind": (
        "Welch independent-sample t test",
        lambda a, b: stats.ttest_ind(a, b, equal_var=False),
    ),
    "ttest_rel": ("Paired-sample Student t test", stats.ttest_rel),
    "mannwhitneyu": (
        "Mann–Whitney U test",
        lambda a, b: stats.mannwhitneyu(a, b, method="auto"),
    ),
    "brunnermunzel": ("Brunner–Munzel two-sample test", stats.brunnermunzel),
    "cramervonmises_2samp": (
        "Two-sample Cramér–von Mises test",
        stats.cramervonmises_2samp,
    ),
    "wasserstein_distance": (
        "One-dimensional Wasserstein distance",
        stats.wasserstein_distance,
    ),
    "energy_distance": ("Energy distance between samples", stats.energy_distance),
    "levene": ("Median-centred Levene variance test", stats.levene),
    "fligner": ("Fligner–Killeen variance test", stats.fligner),
    "bartlett": ("Bartlett variance test", stats.bartlett),
    "kruskal": ("Kruskal–Wallis rank test", stats.kruskal),
    "f_oneway": ("One-way analysis of variance", stats.f_oneway),
    "mood": ("Mood scale test", stats.mood),
    "ansari": ("Ansari–Bradley scale test", stats.ansari),
    "ranksums": ("Wilcoxon rank-sum test", stats.ranksums),
    "linregress": ("Ordinary least-squares linear regression", stats.linregress),
    "epps_singleton_2samp": (
        "Epps–Singleton distribution test",
        stats.epps_singleton_2samp,
    ),
}


def stat_run(data: dict, key: str, paired: bool) -> dict:
    """Apply a documented statistical test; reject undefined domains explicitly."""
    a = vector(
        data,
        minimum=8
        if key in ("normaltest", "skewtest")
        else 5
        if key == "kurtosistest"
        else 3,
    )
    if key in ("gmean", "hmean") and (a <= 0).any():
        raise ValueError("Strictly positive observations required")
    if key == "entropy" and ((a < 0).any() or a.sum() <= 0):
        raise ValueError("Entropy weights must be nonnegative with a positive sum")
    if paired:
        b = vector(data, "comparison")
        if key in (
            "pearsonr",
            "spearmanr",
            "kendalltau",
            "ttest_rel",
            "linregress",
        ) and len(a) != len(b):
            raise ValueError("Paired observations require equal lengths")
        v = STATS_PAIR[key][1](a, b)
    else:
        v = STATS_SINGLE[key][1](a)
    return {
        "result": result_tuple(v),
        "n": len(a),
        "comparison_n": len(data.get("comparison", [])) if paired else None,
        "assumptions": "Inspect the cited test assumptions: independent sampling unless paired; normality/equal variance where required. p-values are unadjusted exploratory values, not posterior probabilities. Undefined quantities are null; no automatic decisions.",
        "reference_population": data["reference_population"],
    }


for key, (title, fn) in STATS_SINGLE.items():
    add(
        "stats." + key,
        title,
        "Statistics",
        "https://docs.scipy.org/doc/scipy/reference/stats.html",
        SAMPLE,
        lambda d, k=key: stat_run(d, k, False),
        "SciPy "
        + scipy.__version__
        + "; "
        + title
        + "; bounded finite input, explicit population and units.",
    )
for key, (title, fn) in STATS_PAIR.items():
    add(
        "stats." + key,
        title,
        "Statistics",
        "https://docs.scipy.org/doc/scipy/reference/stats.html",
        SAMPLE,
        lambda d, k=key: stat_run(d, k, True),
        "SciPy "
        + scipy.__version__
        + "; "
        + title
        + "; retain statistic and unadjusted p-value where supplied.",
    )

DISTANCES = [
    "braycurtis",
    "canberra",
    "chebyshev",
    "cityblock",
    "correlation",
    "cosine",
    "euclidean",
    "jensenshannon",
    "minkowski",
    "sqeuclidean",
    "hamming",
    "jaccard",
    "dice",
    "rogerstanimoto",
    "russellrao",
    "sokalsneath",
    "yule",
]


def distance_run(data: dict, key: str) -> dict:
    """Compute one named distance on explicit comparable feature vectors."""
    a = vector(data, "values", minimum=2, maximum=128)
    b = vector(data, "comparison", minimum=2, maximum=128)
    if len(a) != len(b):
        raise ValueError("Distance vectors require matching feature dimensions")
    if key in DISTANCES[10:]:
        if not np.isin(np.concatenate([a, b]), [0, 1]).all():
            raise ValueError("Boolean distance requires binary 0/1 features")
        a, b = a.astype(bool), b.astype(bool)
    if key == "jensenshannon" and (
        (a < 0).any() or (b < 0).any() or min(a.sum(), b.sum()) <= 0
    ):
        raise ValueError("Positive-sum nonnegative weights required")
    if key in ("cosine", "correlation") and (
        np.linalg.norm(a) == 0
        or np.linalg.norm(b) == 0
        or (key == "correlation" and (a.std() == 0 or b.std() == 0))
    ):
        raise ValueError("Nonzero norm and nonconstant centred vectors required")
    fn = getattr(distance, key)
    score = fn(a, b)
    return {
        "distance": clean(score),
        "features": len(a),
        "reference_population": data["reference_population"],
        "normalisation": "No automatic scaling; investigator must supply comparable units. Boolean variants require explicit binary features.",
    }


for key in DISTANCES:
    example = (
        {**SAMPLE, "values": [1, 0, 1, 1, 0, 0], "comparison": [0, 1, 1, 1, 0, 1]}
        if key in DISTANCES[10:]
        else {**SAMPLE, "values": [1, 2, 4, 8], "comparison": [2, 3, 3, 9]}
    )
    add(
        "distance." + key,
        key.replace("_", " ").title() + " distance",
        "Feature distances",
        "https://docs.scipy.org/doc/scipy/reference/spatial.distance.html",
        example,
        lambda d, k=key: distance_run(d, k),
        "SciPy spatial.distance."
        + key
        + " on explicit bounded vectors; no automatic identity or relationship assertion.",
    )

SIGNALS = {
    "periodogram": "Power spectral density by periodogram",
    "welch": "Welch power spectral density",
    "spectrogram": "Short-time spectrogram",
    "find_peaks": "Local peak detection",
    "peak_prominences": "Peak prominence measurement",
    "peak_widths": "Half-prominence peak widths",
    "detrend": "Least-squares linear detrending",
    "savgol_filter": "Savitzky–Golay smoothing",
    "medfilt": "Median signal filtering",
    "wiener": "Wiener signal denoising",
    "hilbert": "Hilbert analytic amplitude envelope",
    "resample_poly": "Polyphase downsampling by two",
    "decimate": "Anti-aliasing FIR downsampling by two",
    "autocorrelation": "Normalised temporal autocorrelation",
    "crosscorrelation": "Temporal cross-correlation",
    "coherence": "Magnitude-squared coherence",
    "csd": "Cross-spectral density",
    "butter_lowpass": "Butterworth low-pass filtering",
}


def signal_run(data: dict, key: str) -> dict:
    """Inspect a bounded time series with an explicit sampling frequency."""
    a = vector(data, minimum=16)
    fs = float(data.get("sampling_hz", 1))
    if not math.isfinite(fs) or not 0 < fs <= 1_000_000:
        raise ValueError("sampling_hz must be finite and in (0,1e6]")
    size = min(64, len(a))
    if key in ("periodogram", "welch"):
        f, p = getattr(signal, key)(
            a, fs=fs, **({"nperseg": size} if key == "welch" else {})
        )
        out = {"frequency_hz": f, "power_density": p}
    elif key == "spectrogram":
        f, t, z = signal.spectrogram(a, fs=fs, nperseg=size, noverlap=size // 2)
        out = {"frequency_hz": f, "time_seconds": t, "power_density": z}
    elif key in ("find_peaks", "peak_prominences", "peak_widths"):
        peaks, _ = signal.find_peaks(a)
        out = {"indices": peaks, "time_seconds": peaks / fs}
        if key == "peak_prominences":
            out["prominence"] = signal.peak_prominences(a, peaks)[0]
        if key == "peak_widths":
            out["width_samples"] = signal.peak_widths(a, peaks)[0]
    elif key == "hilbert":
        out = {"amplitude_envelope": np.abs(signal.hilbert(a))}
    elif key == "autocorrelation":
        a = a - a.mean()
        if not a.dot(a):
            raise ValueError("Autocorrelation requires nonconstant observations")
        out = {
            "nonnegative_lags_samples": list(range(len(a))),
            "correlation": signal.correlate(a, a, mode="full")[len(a) - 1 :] / a.dot(a),
        }
    elif key in ("crosscorrelation", "coherence", "csd"):
        b = vector(data, "comparison", minimum=16)
        if len(a) != len(b):
            raise ValueError("Synchronous series require matching sample counts")
        if key == "crosscorrelation":
            out = {
                "lags_samples": signal.correlation_lags(len(a), len(b)),
                "correlation": signal.correlate(a, b),
            }
        else:
            f, p = getattr(signal, key)(a, b, fs=fs, nperseg=size)
            out = {"frequency_hz": f, "magnitude": np.abs(p)}
    elif key == "butter_lowpass":
        cutoff = float(data.get("cutoff_hz", fs / 8))
        if not 0 < cutoff < fs / 2:
            raise ValueError("Cutoff must be below Nyquist")
        out = {
            "values": signal.sosfilt(signal.butter(4, cutoff, fs=fs, output="sos"), a),
            "cutoff_hz": cutoff,
        }
    else:
        args = {
            "savgol_filter": (5, 2),
            "medfilt": (3,),
            "wiener": (5,),
            "resample_poly": (1, 2),
            "decimate": (2,),
        }.get(key, ())
        out = {
            "values": getattr(signal, key)(
                a, *args, **({"ftype": "fir"} if key == "decimate" else {})
            )
        }
    return clean(
        {
            **out,
            "sampling_hz": fs,
            "sample_count": len(a),
            "assumptions": "Input must be uniformly sampled and observations lawful. Aliasing, noise and recording artefacts are ordinary explanations; spectral patterns do not authenticate hidden messages.",
        }
    )


for key, title in SIGNALS.items():
    a = [
        float(math.sin(i * math.pi / 8) + 0.2 * math.sin(i * math.pi / 3))
        for i in range(128)
    ]
    add(
        "signal." + key,
        title,
        "Signals",
        "https://docs.scipy.org/doc/scipy/reference/signal.html",
        {**SAMPLE, "values": a, "comparison": a, "sampling_hz": 32},
        lambda d, k=key: signal_run(d, k),
        "SciPy "
        + scipy.__version__
        + "; "
        + title
        + " with recorded sample rate and fixed bounded parameters.",
    )

GRAPH = {
    "pagerank": "PageRank random-walk centrality",
    "degree_centrality": "Normalised degree centrality",
    "harmonic_centrality": "Harmonic centrality",
    "load_centrality": "Load centrality",
    "clustering": "Local triangle clustering",
    "triangles": "Triangle counts",
    "transitivity": "Graph transitivity",
    "density": "Graph density",
    "articulation_points": "Articulation vertices",
    "bridges": "Bridge edges",
    "biconnected_components": "Biconnected components",
    "cycle_basis": "Fundamental cycle basis",
    "minimum_spanning_tree": "Minimum spanning forest",
    "greedy_modularity_communities": "Greedy modularity communities",
    "label_propagation_communities": "Semi-synchronous label propagation communities",
    "asyn_lpa_communities": "Seeded asynchronous label propagation",
    "k_truss": "Three-truss subgraph",
    "onion_layers": "Onion graph decomposition",
    "eccentricity": "Component-wise eccentricity",
    "radius": "Component-wise graph radius",
    "diameter": "Component-wise graph diameter",
    "center": "Component-wise graph centre",
    "periphery": "Component-wise graph periphery",
    "average_shortest_path_length": "Component-wise average shortest path",
    "global_efficiency": "Global graph efficiency",
    "local_efficiency": "Local graph efficiency",
    "degree_assortativity_coefficient": "Degree assortativity",
    "average_neighbor_degree": "Average neighbour degree",
    "jaccard_coefficient": "Nonedge Jaccard similarity",
    "adamic_adar_index": "Adamic–Adar nonedge score",
    "resource_allocation_index": "Resource allocation nonedge score",
    "preferential_attachment": "Preferential attachment nonedge score",
    "shortest_path": "Shortest documented path",
    "minimum_node_cut": "Minimum vertex cut",
    "edge_connectivity": "Global edge connectivity",
    "is_bipartite": "Bipartite graph test",
}
GRAPH_EXAMPLE = {
    "nodes": ["a", "b", "c", "d", "e"],
    "edges": [
        {"source": a, "target": b}
        for a, b in [("a", "b"), ("b", "c"), ("a", "c"), ("c", "d"), ("d", "e")]
    ],
    "source": "a",
    "target": "e",
    "reference_population": "Synthetic graph; no real associations",
}


def graph_run(data: dict, key: str) -> dict:
    """Bound simple-graph analysis and label predicted relationships as hypotheses."""
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    if (
        not isinstance(nodes, list)
        or not 2 <= len(nodes) <= 100
        or len(edges) > 500
        or any(not isinstance(n, str) or len(n) > 200 for n in nodes)
        or len(set(nodes)) != len(nodes)
    ):
        raise ValueError("Require 2–100 unique named nodes and at most 500 edges")
    g = nx.Graph()
    g.add_nodes_from(nodes)
    for edge in edges:
        a, b = edge["source"], edge["target"]
        if a not in g or b not in g or a == b:
            raise ValueError("Edges must name distinct declared nodes")
        g.add_edge(a, b)
    component_keys = (
        "eccentricity",
        "radius",
        "diameter",
        "center",
        "periphery",
        "average_shortest_path_length",
    )
    predictions = (
        "jaccard_coefficient",
        "adamic_adar_index",
        "resource_allocation_index",
        "preferential_attachment",
    )
    if key in component_keys:
        value = [
            {"nodes": sorted(c), "result": getattr(nx, key)(g.subgraph(c))}
            for c in nx.connected_components(g)
        ]
    elif key in predictions:
        pairs = list(nx.non_edges(g))[:500]
        value = [
            {
                "source": a,
                "target": b,
                "score": v,
                "state": "HYPOTHESIS / NOT A FACTUAL EDGE",
            }
            for a, b, v in getattr(nx, key)(g, pairs)
        ]
    elif key == "shortest_path":
        value = nx.shortest_path(
            g, data.get("source", nodes[0]), data.get("target", nodes[-1])
        )
    elif key == "k_truss":
        value = {
            "nodes": list(nx.k_truss(g, 3).nodes),
            "edges": list(nx.k_truss(g, 3).edges),
        }
    elif key == "minimum_spanning_tree":
        value = list(nx.minimum_spanning_tree(g).edges)
    elif key in (
        "greedy_modularity_communities",
        "label_propagation_communities",
        "asyn_lpa_communities",
    ):
        fn = getattr(nx.community, key)
        value = [
            sorted(c)
            for c in fn(g, **({"seed": 42} if key == "asyn_lpa_communities" else {}))
        ]
    else:
        value = getattr(nx, key)(g)
        if not isinstance(value, (dict, list, int, float, bool, str, set)):
            value = list(value)
    return clean(
        {
            "result": value,
            "nodes": g.number_of_nodes(),
            "edges": g.number_of_edges(),
            "edge_policy": data.get(
                "edge_policy",
                "User-supplied graph; documented support not verified by this pure tool",
            ),
            "prediction_truncated": key in predictions
            and len(list(nx.non_edges(g))) > 500,
            "library": "NetworkX " + nx.__version__,
        }
    )


for key, title in GRAPH.items():
    add(
        "graph." + key,
        title,
        "Graph analytics",
        "https://networkx.org/documentation/stable/reference/algorithms/index.html",
        GRAPH_EXAMPLE,
        lambda d, k=key: graph_run(d, k),
        "Unweighted undirected simple graph, parallel edges collapsed; bounds 100 nodes/500 edges. "
        + title
        + ".",
    )

TEXT_EXAMPLE = {
    "text": "The nickel alloy resisted burning. The alloy was tested in a rocket engine. This is a technical report.",
    "comparison_text": "A rocket engine test evaluated a nickel alloy. The alloy resisted burning.",
    "query": "nickel alloy",
    "texts": [
        "The nickel alloy resisted burning. A rocket engine was tested.",
        "The alloy survived oxygen exposure in an engine.",
        "A cake recipe uses flour and milk.",
    ],
    "reference_population": "Synthetic document collection; not case observations",
}
TEXTS = {
    "token_spans": "Unicode word tokens with source offsets",
    "sentence_spans": "Rule-based sentence spans",
    "word_frequency": "Casefolded word frequency",
    "bigrams": "Word bigram frequency",
    "trigrams": "Word trigram frequency",
    "character_ngrams": "Character trigram frequency",
    "lexical_diversity": "Type-token lexical diversity",
    "hapax_ratio": "Hapax legomena ratio",
    "character_entropy": "Unicode character entropy",
    "unicode_controls": "Bidirectional and invisible Unicode control inspection",
    "normalization_diff": "NFKC normalisation differences",
    "line_duplicates": "Exact duplicate line detection",
    "paragraph_duplicates": "Exact duplicate paragraph detection",
    "urls": "Literal public URL spans",
    "emails": "Literal email spans (no ownership inference)",
    "dates": "Literal ISO date spans (not historical proof)",
    "identifiers": "Patent, DOI, hash and handle spans",
    "keyword_context": "Literal keyword in context",
    "text_diff": "SequenceMatcher text difference",
    "jaccard_words": "Word-set Jaccard text similarity",
    "simhash": "64-bit token SimHash",
    "tfidf_search": "Corpus-fitted TF–IDF keyword retrieval",
    "count_matrix": "Bag-of-words count matrix",
    "tfidf_similarity": "Corpus-fitted TF–IDF cosine similarity",
    "lsa": "Truncated-SVD latent semantic analysis",
    "nmf_topics": "Nonnegative matrix factorisation topics",
    "lda_topics": "Latent Dirichlet allocation topics",
    "extractive_summary": "TF–IDF centroid sentence extraction",
    "document_clusters": "Seeded TF–IDF document K-means",
    "near_duplicates": "TF–IDF document similarity pairs",
}


def spans(text: str, pattern: str, flags: int = 0) -> list:
    """Return exact original spans with offsets, never inferred attribution."""
    return [
        {"text": m.group(), "start": m.start(), "end": m.end()}
        for m in re.finditer(pattern, text, flags)
    ][:1000]


def text_run(data: dict, key: str) -> dict:
    """Run bounded lexical or corpus-fitted analysis preserving literal source spans."""
    from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.decomposition import TruncatedSVD, NMF, LatentDirichletAllocation
    from sklearn.cluster import KMeans

    text = data.get("text", "")
    if not isinstance(text, str) or not 1 <= len(text) <= 16000:
        raise ValueError("Use 1–16,000 text characters")
    tokens = spans(text, r"\b\w+\b", re.UNICODE)
    words = [t["text"].casefold() for t in tokens]
    count = Counter(words)
    if key == "token_spans":
        value = tokens
    elif key == "sentence_spans":
        value = spans(text, r"[^.!?\n]+(?:[.!?]+|$)")
    elif key == "word_frequency":
        value = count.most_common(100)
    elif key in ("bigrams", "trigrams"):
        n = 2 if key == "bigrams" else 3
        value = Counter(
            " ".join(words[i : i + n]) for i in range(max(0, len(words) - n + 1))
        ).most_common(100)
    elif key == "character_ngrams":
        value = Counter(
            text[i : i + 3] for i in range(max(0, len(text) - 2))
        ).most_common(100)
    elif key == "lexical_diversity":
        value = len(count) / len(words) if words else None
    elif key == "hapax_ratio":
        value = sum(v == 1 for v in count.values()) / len(words) if words else None
    elif key == "character_entropy":
        n = len(text)
        value = -sum(v / n * math.log2(v / n) for v in Counter(text).values())
    elif key == "unicode_controls":
        value = [
            {
                "offset": i,
                "codepoint": f"U+{ord(c):04X}",
                "name": unicodedata.name(c, "UNNAMED"),
            }
            for i, c in enumerate(text)
            if unicodedata.category(c) in ("Cf", "Cc") and c not in "\n\r\t"
        ]
    elif key == "normalization_diff":
        normalized = unicodedata.normalize("NFKC", text)
        value = {
            "normalized": normalized,
            "changed": normalized != text,
            "warning": "Offsets refer to the original only; NFKC is a separate derivative",
        }
    elif key in ("line_duplicates", "paragraph_duplicates"):
        units = text.splitlines() if key == "line_duplicates" else text.split("\n\n")
        c = Counter(x.strip() for x in units if x.strip())
        value = [{"text": k, "occurrences": v} for k, v in c.items() if v > 1]
    elif key in ("urls", "emails", "dates"):
        value = spans(
            text,
            {
                "urls": r'https?://[^\s<>"\]]+',
                "emails": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
                "dates": r"\b\d{4}-\d{2}-\d{2}\b",
            }[key],
        )
    elif key == "identifiers":
        from .retrieval import identifiers

        value = identifiers(text)
    elif key == "keyword_context":
        q = data.get("query", "")
        if not isinstance(q, str) or not 1 <= len(q) <= 200:
            raise ValueError("Use a literal query of 1–200 characters")
        value = [
            {
                "start": m.start(),
                "end": m.end(),
                "quote": text[max(0, m.start() - 80) : m.end() + 80],
            }
            for m in list(re.finditer(re.escape(q), text, re.I))[:100]
        ]
    elif key in ("text_diff", "jaccard_words"):
        other = data.get("comparison_text", "")
        if not isinstance(other, str) or not 1 <= len(other) <= 16000:
            raise ValueError("Bound comparison_text to 1–16,000 characters")
        if key == "text_diff":
            import difflib

            value = [
                {
                    "operation": op,
                    "left_start": a,
                    "left_end": b,
                    "right_start": c,
                    "right_end": d,
                }
                for op, a, b, c, d in difflib.SequenceMatcher(
                    None, text, other, autojunk=False
                ).get_opcodes()
            ][:500]
        else:
            a = set(words)
            b = set(re.findall(r"\b\w+\b", other.casefold()))
            value = len(a & b) / len(a | b) if a | b else 1
    elif key == "simhash":
        weights = [0] * 64
        for word, n in count.items():
            h = int.from_bytes(hashlib.sha256(word.encode()).digest()[:8], "big")
            for i in range(64):
                weights[i] += n * (1 if h >> i & 1 else -1)
        value = {
            "hex": f"{sum(1 << i for i, x in enumerate(weights) if x > 0):016x}",
            "hash": "SHA-256 first 64 bits, weighted tokens; no identity inference",
        }
    else:
        texts = data.get("texts", [text])
        if key == "extractive_summary":
            texts = [s["text"].strip() for s in spans(text, r"[^.!?\n]+(?:[.!?]+|$)")]
        if (
            not isinstance(texts, list)
            or not 2 <= len(texts) <= 100
            or any(not isinstance(t, str) or not 1 <= len(t) <= 16000 for t in texts)
            or sum(map(len, texts)) > 128000
        ):
            raise ValueError(
                "Require 2–100 texts with at most 128,000 total characters"
            )
        v = (
            CountVectorizer
            if key in ("count_matrix", "lda_topics")
            else TfidfVectorizer
        )(max_features=512)
        x = v.fit_transform(texts)
        terms = v.get_feature_names_out()
        if key == "count_matrix":
            value = {"vocabulary": terms, "matrix": x.toarray()}
        elif key in ("tfidf_similarity", "near_duplicates"):
            sim = cosine_similarity(x)
            value = (
                sim
                if key == "tfidf_similarity"
                else [
                    {"left": i, "right": j, "cosine": sim[i, j]}
                    for i in range(len(texts))
                    for j in range(i + 1, len(texts))
                    if sim[i, j] >= 0.8
                ][:500]
            )
        elif key == "tfidf_search":
            query = data.get("query", "")
            if not isinstance(query, str) or not 1 <= len(query) <= 200:
                raise ValueError("Supply a bounded literal query")
            scores = cosine_similarity(v.transform([query]), x)[0]
            value = [
                {"index": int(i), "score": float(scores[i]), "text": texts[i]}
                for i in np.argsort(-scores)
            ]
        elif key == "extractive_summary":
            centroid = np.asarray(x.mean(axis=0))
            scores = cosine_similarity(x, centroid)[:, 0]
            chosen = sorted(np.argsort(-scores)[:3])
            value = [
                {
                    "sentence_index": int(i),
                    "quote": texts[i],
                    "centroid_similarity": scores[i],
                }
                for i in chosen
            ]
        elif key == "document_clusters":
            value = {
                "labels": KMeans(n_clusters=2, random_state=42, n_init=10).fit_predict(
                    x
                )
            }
        else:
            k = min(2, x.shape[0], x.shape[1] - 1)
            if k < 1:
                raise ValueError("Need at least two distinct terms")
            model = (
                {
                    "lsa": lambda: TruncatedSVD(n_components=k, random_state=42),
                    "nmf_topics": lambda: NMF(
                        n_components=k, random_state=42, max_iter=200
                    ),
                    "lda_topics": lambda: LatentDirichletAllocation(
                        n_components=k, random_state=42, max_iter=10
                    ),
                }
            )[key]()
            features = model.fit_transform(x)
            value = {
                "document_components": features,
                "top_terms": [
                    [str(terms[i]) for i in row.argsort()[-10:][::-1]]
                    for row in model.components_
                ],
            }
    return clean(
        {
            "result": value,
            "token_count": len(words),
            "normalisation": "Unicode word regex, casefolded lexical features; sentence splitting is heuristic; no inferred entity ownership",
            "model_scope": "Corpus-fitted transforms are reproducible exploratory models, not independently benchmarked case conclusions",
        }
    )


for key, title in TEXTS.items():
    learned = key in ("lsa", "nmf_topics", "lda_topics", "document_clusters")
    add(
        "text." + key,
        title,
        "Text intelligence",
        "https://scikit-learn.org/stable/modules/feature_extraction.html#text-feature-extraction"
        if key
        in (
            "tfidf_search",
            "tfidf_similarity",
            "count_matrix",
            "lsa",
            "nmf_topics",
            "lda_topics",
            "document_clusters",
            "near_duplicates",
            "extractive_summary",
        )
        else "https://docs.python.org/3/library/text.html",
        TEXT_EXAMPLE,
        lambda d, k=key: text_run(d, k),
        title + "; exact procedures and bounds disclosed in returned output.",
        kind="MACHINE_LEARNING" if learned else "DETERMINISTIC_ANALYSIS",
    )

ML = {
    "kmeans": "K-means clustering",
    "agglomerative": "Agglomerative Ward clustering",
    "birch": "BIRCH clustering",
    "optics": "OPTICS density clustering",
    "gmm": "Gaussian mixture clustering",
    "spectral": "Spectral clustering",
    "mean_shift": "Mean-shift clustering",
    "affinity_propagation": "Affinity propagation clustering",
    "minibatch_kmeans": "Mini-batch K-means clustering",
    "robust_covariance": "Minimum covariance determinant anomaly scoring",
    "gaussian_nb": "Gaussian naive Bayes holdout classification",
    "logistic": "Logistic regression holdout classification",
    "random_forest": "Random forest holdout classification",
    "extra_trees": "Extremely randomized trees holdout classification",
    "knn": "K-nearest-neighbour holdout classification",
    "linear_svc": "Linear support-vector holdout classification",
    "decision_tree": "Decision tree holdout classification",
    "ridge": "Ridge holdout regression",
    "random_forest_regression": "Random forest holdout regression",
    "huber": "Huber robust holdout regression",
    "elastic_net": "Elastic-net holdout regression",
    "quantile": "Median quantile holdout regression",
    "fastica": "Fast independent component analysis",
    "kernel_pca": "RBF kernel principal components",
    "factor_analysis": "Factor analysis",
    "nmf": "Numeric nonnegative matrix factorisation",
}
ML_EXAMPLE = {
    "baseline": [[float(i % 5), float(i // 5), float((i * 7) % 11)] for i in range(40)],
    "points": [[1.0, 2.0, 3.0], [3.0, 4.0, 2.0]],
    "labels": [i % 2 for i in range(40)],
    "holdout_labels": [0, 1],
    "feature_names": ["synthetic x", "synthetic y", "synthetic z"],
    "reference_population": "Synthetic independently supplied training/holdout rows; arbitrary units; no case performance claim",
}


def matrix(data: dict, key: str, features: int | None = None) -> np.ndarray:
    """Validate bounded row/feature counts before loading estimators."""
    a = np.asarray(data.get(key), dtype=float)
    if (
        a.ndim != 2
        or not 2 <= len(a) <= 500
        or not 1 <= a.shape[1] <= 20
        or not np.isfinite(a).all()
        or (features and a.shape[1] != features)
    ):
        raise ValueError("Require 2–500 finite rows, 1–20 matching feature columns")
    return a


def ml_run(data: dict, key: str) -> dict:
    """Fit on training rows only, evaluate independent explicit holdout rows where supplied."""
    from sklearn import (
        cluster,
        decomposition,
        mixture,
        covariance,
        preprocessing,
        metrics,
        naive_bayes,
        linear_model,
        ensemble,
        neighbors,
        svm,
        tree,
    )

    if (
        not isinstance(data.get("reference_population"), str)
        or not data["reference_population"].strip()
    ):
        raise ValueError(
            "Describe training/holdout provenance and reference_population"
        )
    x = matrix(data, "baseline")
    y = matrix(data, "points", x.shape[1])
    names = data.get("feature_names", [])
    if len(names) != x.shape[1] or any(not isinstance(n, str) or not n for n in names):
        raise ValueError("Name every feature and its units")
    if len(x) < 10:
        raise ValueError("Require at least ten training rows")
    scaling = preprocessing.StandardScaler().fit(x)
    a = scaling.transform(x)
    b = scaling.transform(y)
    clusters = {
        "kmeans": lambda: cluster.KMeans(n_clusters=2, n_init=10, random_state=42),
        "minibatch_kmeans": lambda: cluster.MiniBatchKMeans(
            n_clusters=2, n_init=3, random_state=42, batch_size=32
        ),
        "agglomerative": lambda: cluster.AgglomerativeClustering(n_clusters=2),
        "birch": lambda: cluster.Birch(n_clusters=2),
        "optics": lambda: cluster.OPTICS(min_samples=3),
        "gmm": lambda: mixture.GaussianMixture(n_components=2, random_state=42),
        "spectral": lambda: cluster.SpectralClustering(
            n_clusters=2, random_state=42, assign_labels="cluster_qr"
        ),
        "mean_shift": lambda: cluster.MeanShift(),
        "affinity_propagation": lambda: cluster.AffinityPropagation(random_state=42),
    }
    classifiers = {
        "gaussian_nb": lambda: naive_bayes.GaussianNB(),
        "logistic": lambda: linear_model.LogisticRegression(
            random_state=42, max_iter=200
        ),
        "random_forest": lambda: ensemble.RandomForestClassifier(
            n_estimators=32, random_state=42, max_depth=8, n_jobs=1
        ),
        "extra_trees": lambda: ensemble.ExtraTreesClassifier(
            n_estimators=32, random_state=42, max_depth=8, n_jobs=1
        ),
        "knn": lambda: neighbors.KNeighborsClassifier(n_neighbors=3),
        "linear_svc": lambda: svm.LinearSVC(random_state=42, max_iter=1000),
        "decision_tree": lambda: tree.DecisionTreeClassifier(
            random_state=42, max_depth=6
        ),
    }
    regressors = {
        "ridge": lambda: linear_model.Ridge(),
        "random_forest_regression": lambda: ensemble.RandomForestRegressor(
            n_estimators=32, max_depth=8, random_state=42, n_jobs=1
        ),
        "huber": lambda: linear_model.HuberRegressor(max_iter=200),
        "elastic_net": lambda: linear_model.ElasticNet(random_state=42, max_iter=1000),
        "quantile": lambda: linear_model.QuantileRegressor(
            quantile=0.5, alpha=0.01, solver="highs"
        ),
    }
    if key in clusters:
        model = clusters[key]()
        labels = model.fit_predict(a)
        result = {
            "training_labels": labels,
            "independent_prediction_supported": hasattr(model, "predict"),
        }
        if hasattr(model, "predict"):
            result["holdout_labels"] = model.predict(b)
        unique = set(labels) - {-1}
        if 1 < len(unique) < len(a) and -1 not in labels:
            result["training_silhouette"] = metrics.silhouette_score(a, labels)
    elif key == "robust_covariance":
        model = covariance.MinCovDet(random_state=42).fit(a)
        result = {
            "holdout_mahalanobis_squared": model.mahalanobis(b),
            "baseline_location": model.location_,
        }
    elif key in classifiers or key in regressors:
        labels = np.asarray(data.get("labels"), dtype=float)
        truth = np.asarray(data.get("holdout_labels"), dtype=float)
        if (
            labels.shape != (len(x),)
            or truth.shape != (len(y),)
            or not np.isfinite(labels).all()
            or not np.isfinite(truth).all()
        ):
            raise ValueError(
                "Require finite training labels and independent holdout_labels"
            )
        # Exact row overlap is an observable leakage error. Group/time leakage needs an external study design.
        if set(map(tuple, x)) & set(map(tuple, y)):
            raise ValueError("Training/holdout feature rows overlap; potential leakage")
        model = (classifiers if key in classifiers else regressors)[key]().fit(
            a, labels
        )
        pred = model.predict(b)
        result = {
            "predictions": pred,
            "holdout_labels": truth,
            "train_rows": len(x),
            "holdout_rows": len(y),
            "no_exact_row_overlap": True,
        }
        if key in classifiers:
            result.update(
                accuracy=metrics.accuracy_score(truth, pred),
                balanced_accuracy=metrics.balanced_accuracy_score(truth, pred),
                confusion_matrix=metrics.confusion_matrix(truth, pred),
            )
        else:
            result.update(
                mean_absolute_error=metrics.mean_absolute_error(truth, pred),
                mean_squared_error=metrics.mean_squared_error(truth, pred),
            )
    else:
        k = min(2, a.shape[1], a.shape[0] - 1)
        model = {
            "fastica": lambda: decomposition.FastICA(
                n_components=k, random_state=42, max_iter=300, whiten="unit-variance"
            ),
            "kernel_pca": lambda: decomposition.KernelPCA(n_components=k, kernel="rbf"),
            "factor_analysis": lambda: decomposition.FactorAnalysis(
                n_components=k, random_state=42
            ),
            "nmf": lambda: decomposition.NMF(
                n_components=k, random_state=42, max_iter=200
            ),
        }[key]()
        if key == "nmf":
            if (x < 0).any() or (y < 0).any():
                raise ValueError("NMF requires nonnegative features")
            a, b = x, y
        result = {
            "training_components": model.fit_transform(a),
            "holdout_components": model.transform(b),
        }
    return clean(
        {
            **result,
            "feature_names": names,
            "reference_population": data["reference_population"],
            "parameters": model.get_params(),
            "library": "scikit-learn " + sklearn.__version__,
            "scaling": "Training-only StandardScaler, except nonnegative NMF uses supplied features",
            "validation": "EXPLORATORY; actual holdout metrics apply only to this submitted dataset; no case accuracy established",
        }
    )


for key, title in ML.items():
    add(
        "ml." + key,
        title,
        "Machine learning",
        "https://scikit-learn.org/stable/supervised_learning.html"
        if key
        in (
            "gaussian_nb",
            "logistic",
            "random_forest",
            "extra_trees",
            "knn",
            "linear_svc",
            "decision_tree",
            "ridge",
            "random_forest_regression",
            "huber",
            "elastic_net",
            "quantile",
        )
        else "https://scikit-learn.org/stable/unsupervised_learning.html",
        ML_EXAMPLE,
        lambda d, k=key: ml_run(d, k),
        "Seed 42 where stochastic; at most 500 rows/20 columns; one native numerical thread. Fit transforms on training rows only; supplied independent holdout labels required for supervised evaluation.",
        kind="MACHINE_LEARNING",
    )


def execute(tool: str, inputs: dict) -> dict:
    """Dispatch only registered callables, record versions, reject oversized input/output."""
    if tool not in HANDLERS:
        raise ValueError("Unknown or unavailable tool")
    encoded = json.dumps(inputs, allow_nan=False, ensure_ascii=False).encode()
    if len(encoded) > 256000:
        raise ValueError("Tool input exceeds 256 KB")
    with threadpool_limits(limits=1):
        value = clean(HANDLERS[tool](inputs))
    result = {
        "tool": tool,
        "tool_version": VERSION,
        "inputs_sha256": hashlib.sha256(encoded).hexdigest(),
        "output": value,
        "limitations": CATALOGUE[tool]["limitations"],
        "libraries": {
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "sklearn": sklearn.__version__,
            "networkx": nx.__version__,
        },
    }
    if len(json.dumps(result, allow_nan=False).encode()) > 1024 * 1024:
        raise ValueError("Tool output exceeds 1 MB")
    return result


# Existing classical laboratory functions use the same audited dispatcher, not a duplicate implementation.
from .cryptanalysis import METHODS as CIPHERS, transform as cipher_transform  # noqa: E402

_CIPHER_EXAMPLES = {
    "hex": ("48656c6c6f", {}),
    "base64": ("SGVsbG8=", {}),
    "base32": ("JBSWY3DP", {}),
    "base85": ("NM&qnZv", {}),
    "ascii85": ("87cURDZ", {}),
    "binary": ("01001000 01101001", {}),
    "octal": ("110 151", {}),
    "decimal": ("72 105", {}),
    "morse": ("... --- ...", {}),
    "a1z26": ("8 5 12 12 15", {}),
    "polybius": ("23 15 31 31 34", {}),
    "bacon": ("AABBB AABAA ABABB ABABB ABBBA", {}),
    "xor": ("030e070704", {"key": "K"}),
    "snowflake": ("1738018409441308955", {}),
    "unix": ("1703203200", {}),
    "unix_ms": ("1703203200000", {}),
    "scrabble": ("listen", {"exact": True}),
    "hill2": ("HIAT", {"key": "3,3,2,5"}),
    "adfgx": ("ADFGXADFGX", {"key": "KEY", "square_key": "EXAMPLE"}),
    "playfair": ("BMODZBXDNABEKUDMUIXMMOUVIF", {"key": "PLAYFAIR EXAMPLE"}),
    "autokey": ("HELLO", {"key": "KEY"}),
    "gronsfeld": ("HELLO", {"key": "31415"}),
    "bifid": ("HELLO", {"key": "KEY", "period": 5}),
}


def cipher_run(data: dict, method: str) -> dict:
    """Preserve exact transformation and parameters; never authenticate decoded messages."""
    text = data.get("text")
    params = data.get("params", {})
    if (
        not isinstance(text, str)
        or not 1 <= len(text) <= 10000
        or not isinstance(params, dict)
    ):
        raise ValueError("Use bounded text and a parameter object")
    if len(json.dumps(params)) > 16000:
        raise ValueError("Cipher parameters exceed 16 KB")
    out = cipher_transform(text, method, params)
    return {
        "original": text,
        "parameters": params,
        "transformed": out,
        "validation": "UNVALIDATED; readable output is not evidence of intentional encoding",
        "attempts": 1,
        "controls": "No controls in a single transform. Use the existing cipher screening laboratory for shuffled controls and multiplicity; historical timestamp is not account attribution.",
    }


for key, title in CIPHERS.items():
    text, params = _CIPHER_EXAMPLES.get(
        key, ("HELLO WORLD THIS IS A LONGER ENGLISH TEST MESSAGE", {})
    )
    add(
        "cipher." + key,
        title,
        "Classical ciphers & encodings",
        "https://www.nsa.gov/History/Cryptologic-History/Historical-Publications/",
        {"text": text, "params": params},
        lambda d, k=key: cipher_run(d, k),
        "Existing SHERLOCK bounded classical laboratory. Exact original, transformation and parameters retained. Encodings and classical puzzles do not break secure modern encryption.",
        kind="CLASSICAL_TRANSFORM",
    )

# Reuse distinct earlier engines while excluding equivalent new procedures and duplicate cipher entries.
from .analytical_methods import METHODS as PRIOR, run as prior_run, GRAPH_METHODS  # noqa: E402

_EXCLUDE = {"kasiski", "friedman", "chi_squared", "js", "network"}
for key, (title, ref, procedure, example) in PRIOR.items():
    if key in _EXCLUDE:
        continue
    example = dict(example)
    if key in GRAPH_METHODS:
        example.update(GRAPH_EXAMPLE)
    add(
        "analysis." + key,
        title,
        "Established detectors",
        ref,
        example,
        lambda d, k=key: prior_run(k, d),
        procedure,
        kind="MACHINE_LEARNING"
        if key in ("isolation_forest", "lof", "one_class_svm", "pca")
        else "DETERMINISTIC_ANALYSIS",
    )

from .gematria import analyse as gematria_analyse  # noqa: E402

add(
    "gematria.all",
    "Automatic gematria / isopsephy comparison",
    "Gematria & numerical puzzles",
    "https://www.britannica.com/topic/gematria",
    {"text": "Cole Allen", "targets": ["Allen Cole", "hello"], "seed": 42},
    gematria_analyse,
    "Run all eight explicit English, Hebrew and Greek mappings; retain per-letter contributions, ignored characters, collisions, comparison counts and matched-length uniform toy controls. No numerical prediction inference.",
    kind="CLASSICAL_TRANSFORM",
)

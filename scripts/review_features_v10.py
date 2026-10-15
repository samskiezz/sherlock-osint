"""Research every callable feature against live official API documentation and installed code.

This verifies API provenance and availability, not investigative effectiveness.
Shared documentation is fetched once, while every feature retains its own record.
"""

import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlparse
import urllib.robotparser
import threading
from datetime import datetime, timezone
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.automation import catalogue  # noqa: E402
import networkx as nx  # noqa: E402
from sklearn import (  # noqa: E402
    cluster,
    decomposition,
    mixture,
    covariance,
    naive_bayes,
    linear_model,
    ensemble,
    neighbors,
    svm,
    tree,
)

MODELS = {
    "kmeans": cluster.KMeans,
    "agglomerative": cluster.AgglomerativeClustering,
    "birch": cluster.Birch,
    "optics": cluster.OPTICS,
    "gmm": mixture.GaussianMixture,
    "spectral": cluster.SpectralClustering,
    "mean_shift": cluster.MeanShift,
    "affinity_propagation": cluster.AffinityPropagation,
    "minibatch_kmeans": cluster.MiniBatchKMeans,
    "robust_covariance": covariance.MinCovDet,
    "gaussian_nb": naive_bayes.GaussianNB,
    "logistic": linear_model.LogisticRegression,
    "random_forest": ensemble.RandomForestClassifier,
    "extra_trees": ensemble.ExtraTreesClassifier,
    "knn": neighbors.KNeighborsClassifier,
    "linear_svc": svm.LinearSVC,
    "decision_tree": tree.DecisionTreeClassifier,
    "ridge": linear_model.Ridge,
    "random_forest_regression": ensemble.RandomForestRegressor,
    "huber": linear_model.HuberRegressor,
    "elastic_net": linear_model.ElasticNet,
    "quantile": linear_model.QuantileRegressor,
    "fastica": decomposition.FastICA,
    "kernel_pca": decomposition.KernelPCA,
    "factor_analysis": decomposition.FactorAnalysis,
    "nmf": decomposition.NMF,
}
TEXT_REF = {
    "tfidf_search": "sklearn.feature_extraction.text.TfidfVectorizer",
    "tfidf_similarity": "sklearn.metrics.pairwise.cosine_similarity",
    "count_matrix": "sklearn.feature_extraction.text.CountVectorizer",
    "lsa": "sklearn.decomposition.TruncatedSVD",
    "nmf_topics": "sklearn.decomposition.NMF",
    "lda_topics": "sklearn.decomposition.LatentDirichletAllocation",
    "extractive_summary": "sklearn.metrics.pairwise.cosine_similarity",
    "document_clusters": "sklearn.cluster.KMeans",
    "near_duplicates": "sklearn.metrics.pairwise.cosine_similarity",
}


def reference(tool):
    """Resolve published API URLs from explicit adapter mappings, never invented agency claims."""
    key = tool["id"].split(".", 1)[-1]
    if tool["id"].startswith("stats."):
        mapped = {
            "trim_mean": "trim_mean",
            "mad": "median_abs_deviation",
            "winsorize": "mstats.winsorize",
            "quantiles": None,
        }.get(key, key)
        return (
            "https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats."
            + mapped
            + ".html"
            if mapped
            else "https://numpy.org/doc/stable/reference/generated/numpy.quantile.html"
        )
    if tool["id"].startswith("distance."):
        return (
            "https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance."
            + key
            + ".html"
        )
    if tool["id"].startswith("signal."):
        mapped = {
            "autocorrelation": "correlate",
            "crosscorrelation": "correlate",
            "butter_lowpass": "butter",
        }.get(key, key)
        return (
            "https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal."
            + mapped
            + ".html"
        )
    if tool["id"].startswith("ml."):
        model = MODELS[key]
        module = model.__module__.split("._")[0]
        return (
            "https://scikit-learn.org/stable/modules/generated/"
            + module
            + "."
            + model.__name__
            + ".html"
        )
    if tool["id"].startswith("graph."):
        inventory = ROOT / "artifacts/graph-documentation-inventory-v10.json"
        if inventory.is_file():
            mapped = json.loads(inventory.read_text())["mapping"].get(key)
            if mapped:
                return mapped
        fn = getattr(nx, key, None) or getattr(nx.community, key)
        return (
            "https://networkx.org/documentation/stable/reference/algorithms/generated/"
            + fn.__module__
            + "."
            + fn.__name__
            + ".html"
        )
    if tool["id"].startswith("text.") and key in TEXT_REF:
        return (
            "https://scikit-learn.org/stable/modules/generated/"
            + TEXT_REF[key]
            + ".html"
        )
    if key == "text_diff":
        return "https://docs.python.org/3/library/difflib.html#difflib.SequenceMatcher"
    if key in ("unicode_controls", "normalization_diff"):
        return "https://docs.python.org/3/library/unicodedata.html"
    return tool["reference"]


locks = {}
robots = {}
stamps = {}
guard = threading.Lock()


def fetch(url):
    """Respect robots and per-domain pacing; record every acquisition failure."""
    host = urlparse(url).netloc
    with guard:
        lock = locks.setdefault(host, threading.Lock())
    record = {"url": url, "retrieved_utc": datetime.now(timezone.utc).isoformat()}
    try:
        with lock, httpx.Client(timeout=20, follow_redirects=True) as c:
            if host not in robots:
                r = c.get("https://" + host + "/robots.txt")
                parser = urllib.robotparser.RobotFileParser()
                if r.status_code in (401, 403):
                    parser.disallow_all = True
                elif r.status_code == 200:
                    parser.parse(r.text.splitlines())
                else:
                    parser.allow_all = True
                robots[host] = parser
            if not robots[host].can_fetch("SHERLOCK-OSINT", url):
                return {**record, "acquisition": "ROBOTS DISALLOWED"}
            gap = 0.2 - (time.monotonic() - stamps.get(host, 0))
            if gap > 0:
                time.sleep(gap)
            r = c.get(
                url, headers={"User-Agent": "SHERLOCK-OSINT documentation review"}
            )
            stamps[host] = time.monotonic()
        record.update(status=r.status_code, final_url=str(r.url), bytes=len(r.content))
        if r.status_code == 200 and len(r.content) <= 16_000_000:
            digest = hashlib.sha256(r.content).hexdigest()
            p = ROOT / "artifacts/feature-api-documents-v10" / digest
            p.write_bytes(r.content)
            record.update(
                acquisition="ACQUIRED", sha256=digest, file=str(p.relative_to(ROOT))
            )
        else:
            record["acquisition"] = "NOT ACQUIRED"
    except Exception as ex:
        record.update(acquisition="ACQUISITION FAILED", error=type(ex).__name__)
    return record


if __name__ == "__main__":
    directory = ROOT / "artifacts/feature-api-documents-v10"
    directory.mkdir(exist_ok=True)
    tools = catalogue()
    urls = {t["id"]: reference(t) for t in tools}
    unique = sorted(set(urls.values()))
    cache_path = ROOT / "artifacts/automation-feature-research-v10.json"
    previous = (
        json.loads(cache_path.read_text())["documents"] if cache_path.is_file() else []
    )
    cached = {r["url"]: r for r in previous if r["acquisition"] == "ACQUIRED"}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(
            pool.map(lambda url: cached[url] if url in cached else fetch(url), unique)
        )
    by_url = {r["url"]: r for r in outcomes}
    code = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [
            ROOT / "backend/automation_tools.py",
            ROOT / "backend/automation.py",
            ROOT / "backend/cryptanalysis.py",
            ROOT / "backend/analytical_methods.py",
        ]
    }
    records = [
        {
            **t,
            "api_documentation": by_url[urls[t["id"]]],
            "implementation_files_sha256": code,
            "validation_scope": "Named callable executed in tests. Engineering API/library reference; source availability is recorded separately. Not an independent benchmark or original case evidence.",
        }
        for t in tools
    ]
    result = {
        "features_researched": len(records),
        "unique_reference_urls": len(unique),
        "references_acquired": sum(x["acquisition"] == "ACQUIRED" for x in outcomes),
        "features_with_acquired_reference": sum(
            x["api_documentation"]["acquisition"] == "ACQUIRED" for x in records
        ),
        "features": records,
        "documents": outcomes,
    }
    (ROOT / "artifacts/automation-feature-research-v10.json").write_text(
        json.dumps(result, indent=2)
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("features", "documents")}
        )
    )

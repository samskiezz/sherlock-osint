"""Bounded established detectors with explicit independent training baselines and units."""

from typing import Any
import math

EXAMPLE = {
    "baseline": [
        [x / 10, y / 10]
        for x, y in [
            (0, 0),
            (1, 0),
            (0, 1),
            (1, 1),
            (-1, 0),
            (0, -1),
            (-1, -1),
            (-1, 1),
            (1, -1),
            (2, 0),
            (0, 2),
            (-2, 0),
            (0, -2),
            (2, 1),
            (1, 2),
            (-2, -1),
            (-1, -2),
            (2, -1),
            (-1, 2),
            (-2, 1),
        ]
    ],
    "points": [[0.01, 0.01], [8, 8]],
    "feature_names": [
        "synthetic feature x, arbitrary units",
        "synthetic feature y, arbitrary units",
    ],
    "reference_population": "Synthetic independent baseline, not case observations",
    "seed": 42,
}
SPECS = {
    "isolation_forest": (
        "Isolation Forest",
        "https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html",
        "Fit 64 seeded isolation trees on the explicit baseline; score independent observations using the fitted offset. No probability or guilt attribution.",
    ),
    "lof": (
        "Local Outlier Factor",
        "https://scikit-learn.org/stable/modules/generated/sklearn.neighbors.LocalOutlierFactor.html",
        "Novelty detection trained only on the baseline; fixed Euclidean neighbours and independent scored observations.",
    ),
    "one_class_svm": (
        "One-Class SVM",
        "https://scikit-learn.org/stable/modules/generated/sklearn.svm.OneClassSVM.html",
        "Baseline-only standardisation followed by RBF One-Class SVM; explicit nu and gamma, not a measured false-positive rate.",
    ),
    "pca": (
        "Principal Component Analysis",
        "https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html",
        "Baseline-only standardisation and full-SVD PCA; reconstruction errors compared against a baseline empirical quantile.",
    ),
    "mahalanobis": (
        "Mahalanobis distance",
        "https://scikit-learn.org/stable/modules/generated/sklearn.covariance.EmpiricalCovariance.html",
        "Baseline empirical covariance, reject singular or ill-conditioned matrices; square-root quadratic distances and a baseline empirical quantile.",
    ),
    "grubbs": (
        "Grubbs’ test",
        "https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h1.htm",
        "Two-sided single-outlier Grubbs statistic and Student-t critical value. Requires approximately normal independent observations; no iterative deletion.",
    ),
}
METHODS = {
    key: (
        name,
        url,
        procedure,
        EXAMPLE.copy()
        if key != "grubbs"
        else {
            "values": [9, 10, 11, 10, 9, 11, 10, 10, 9, 100],
            "alpha": 0.05,
            "reference_population": "Synthetic approximately normal sample plus a planted outlier",
        },
    )
    for key, (name, url, procedure) in SPECS.items()
}


def run(method: str, data: dict[str, Any]) -> dict[str, Any]:
    """Execute one real detector, retaining reproducible parameters and baseline assumptions."""
    import numpy as np
    import scipy
    import sklearn
    from scipy.stats import t
    from sklearn.preprocessing import StandardScaler
    from threadpoolctl import threadpool_limits

    population = data.get("reference_population")
    if not isinstance(population, str) or not population.strip():
        raise ValueError(
            "Describe the reference population, sampling and feature units"
        )
    common = {
        "reference_population": population,
        "libraries": {
            "scikit-learn": sklearn.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "validation": "EXPLORATORY / HUMAN REVIEW REQUIRED",
        "warning": "An outlier is a deviation from this supplied baseline, not wrongdoing, a hidden message or causal proof. Selection, dependence, measurement error and ordinary technical differences are alternative explanations. No case-level detection accuracy is established.",
    }
    if method == "grubbs":
        values = data.get("values")
        if not isinstance(values, list) or not 3 <= len(values) <= 1000:
            raise ValueError("Grubbs requires 3–1,000 finite observations")
        x = np.asarray(values, dtype=float)
        alpha = float(data.get("alpha", 0.05))
        if x.ndim != 1 or not np.isfinite(x).all() or not 0.0001 <= alpha <= 0.2:
            raise ValueError(
                "Use a finite one-dimensional sample and alpha in [0.0001,0.2]"
            )
        sd = float(x.std(ddof=1))
        n = len(x)
        if sd == 0:
            return {
                **common,
                "defined": False,
                "reason": "Zero sample dispersion",
                "outlier_indices": [],
            }
        index = int(np.argmax(np.abs(x - x.mean())))
        score = float(abs(x[index] - x.mean()) / sd)
        critical_t = float(t.ppf(1 - alpha / (2 * n), n - 2))
        critical = (
            (n - 1) / math.sqrt(n) * math.sqrt(critical_t**2 / (n - 2 + critical_t**2))
        )
        return {
            **common,
            "defined": True,
            "G": score,
            "critical_G": critical,
            "alpha": alpha,
            "sample_size": n,
            "outlier_indices": [index] if score > critical else [],
            "assumptions": "Approximately normally distributed, independent sample; one candidate outlier; no repeated testing correction.",
        }
    baseline = data.get("baseline")
    points = data.get("points")
    if (
        not isinstance(baseline, list)
        or not 10 <= len(baseline) <= 1000
        or not isinstance(points, list)
        or not 1 <= len(points) <= 1000
    ):
        raise ValueError(
            "Use 10–1,000 independent baseline rows and 1–1,000 observation rows"
        )
    try:
        train = np.asarray(baseline, dtype=float)
        test = np.asarray(points, dtype=float)
    except (ValueError, TypeError) as ex:
        raise ValueError("Use rectangular finite numeric feature matrices") from ex
    if (
        train.ndim != 2
        or test.ndim != 2
        or not 1 <= train.shape[1] <= 20
        or test.shape[1] != train.shape[1]
        or not np.isfinite(train).all()
        or not np.isfinite(test).all()
    ):
        raise ValueError("Both finite matrices require the same 1–20 feature columns")
    names = data.get("feature_names")
    if (
        not isinstance(names, list)
        or len(names) != train.shape[1]
        or any(not isinstance(x, str) or not x.strip() for x in names)
    ):
        raise ValueError("Name each measured feature and its units")
    if np.any(train.std(axis=0) == 0):
        raise ValueError(
            "Baseline contains a constant feature; remove it rather than asserting an anomaly"
        )
    seed = int(data.get("seed", 42))
    if not 0 <= seed <= 2**32 - 1:
        raise ValueError("Seed must be an unsigned 32-bit integer")
    scaler = StandardScaler()
    a = scaler.fit_transform(train)
    b = scaler.transform(test)
    parameters = {
        "seed": seed,
        "standardisation": "Baseline mean and population SD only; no scored-point leakage",
        "baseline_mean": scaler.mean_.tolist(),
        "baseline_scale": scaler.scale_.tolist(),
    }
    with threadpool_limits(limits=1):
        if method == "isolation_forest":
            from sklearn.ensemble import IsolationForest

            model = IsolationForest(
                n_estimators=64, random_state=seed, contamination="auto", n_jobs=1
            ).fit(a)
            scores = -model.score_samples(b)
            threshold = float(-model.offset_)
            flags = model.predict(b) == -1
            parameters.update(n_estimators=64, contamination="auto")
        elif method == "lof":
            from sklearn.neighbors import LocalOutlierFactor

            k = int(data.get("n_neighbors", min(20, len(a) - 1)))
            if not 2 <= k < len(a):
                raise ValueError(
                    "Neighbours must be at least two and fewer than baseline rows"
                )
            model = LocalOutlierFactor(
                n_neighbors=k, novelty=True, contamination="auto", n_jobs=1
            ).fit(a)
            scores = -model.score_samples(b)
            threshold = float(-model.offset_)
            flags = model.predict(b) == -1
            parameters.update(n_neighbors=k, novelty=True)
        elif method == "one_class_svm":
            from sklearn.svm import OneClassSVM

            nu = float(data.get("nu", 0.05))
            if not 0.001 <= nu <= 0.5:
                raise ValueError("nu must be in [0.001,0.5]")
            model = OneClassSVM(kernel="rbf", nu=nu, gamma="scale").fit(a)
            scores = -model.decision_function(b)
            threshold = 0.0
            flags = scores > threshold
            parameters.update(nu=nu, gamma="scale", kernel="rbf")
        elif method in ("pca", "mahalanobis"):
            quantile = float(data.get("quantile", 0.99))
            if not 0.9 <= quantile <= 0.999:
                raise ValueError("Empirical threshold quantile must be in [0.9,0.999]")
            if method == "pca":
                from sklearn.decomposition import PCA

                components = int(data.get("components", max(1, train.shape[1] - 1)))
                if not 1 <= components < train.shape[1]:
                    raise ValueError(
                        "PCA reconstruction screening requires fewer components than input features"
                    )
                model = PCA(n_components=components, svd_solver="full").fit(a)
                score = lambda x: np.mean(
                    (x - model.inverse_transform(model.transform(x))) ** 2, axis=1
                )
                baseline_scores = score(a)
                scores = score(b)
                parameters.update(
                    components=components,
                    explained_variance_ratio=model.explained_variance_ratio_.tolist(),
                )
            else:
                from sklearn.covariance import EmpiricalCovariance

                if len(a) <= train.shape[1] + 1:
                    raise ValueError(
                        "Covariance requires more baseline rows than dimensions plus one"
                    )
                covariance = np.cov(a, rowvar=False, bias=True)
                covariance = np.atleast_2d(covariance)
                if np.linalg.cond(covariance) > 1e10:
                    raise ValueError(
                        "Baseline covariance is singular or ill-conditioned"
                    )
                model = EmpiricalCovariance().fit(a)
                baseline_scores = np.sqrt(np.maximum(0, model.mahalanobis(a)))
                scores = np.sqrt(np.maximum(0, model.mahalanobis(b)))
            threshold = float(np.quantile(baseline_scores, quantile))
            flags = scores > threshold
            parameters.update(
                quantile=quantile,
                threshold_interpretation="Empirical baseline quantile; not a population false-positive guarantee or calibrated p-value",
            )
        else:
            raise ValueError("Unsupported learned detector")
    if not np.isfinite(scores).all():
        raise ValueError("Detector produced undefined scores; no flags asserted")
    return {
        **common,
        "feature_names": names,
        "baseline_rows": len(a),
        "observation_rows": len(b),
        "parameters": parameters,
        "threshold": threshold,
        "score_interpretation": "Higher values indicate greater deviation under this detector",
        "scores": scores.tolist(),
        "outlier_indices": np.flatnonzero(flags).tolist(),
        "baseline_validation": "User supplied; independence, representativeness and provenance require review",
    }

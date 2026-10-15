"""Evidence-bound analytical records and explicit method maturity. No agency capability claims."""

import json
import math
import re
import statistics
from collections import Counter, defaultdict
from fastapi import HTTPException
from pydantic import BaseModel, Field
from .analytical_methods import METHODS as COMPUTATIONAL, GRAPH_METHODS, run as compute
from .learned_anomalies import METHODS as LEARNED_METHODS

PRIMER = "https://www.cia.gov/resources/csi/static/955180a45afe3f5013772c313b16face/Tradecraft-Primer-apr09.pdf"
HEUER = (
    "https://www.cia.gov/resources/csi/static/Pyschology-of-Intelligence-Analysis.pdf"
)
NIST = "https://nvlpubs.nist.gov/nistpubs/legacy/sp/nistspecialpublication800-86.pdf"
CIA = [
    (
        "assumptions",
        "Key Assumptions Check",
        [
            "What is assumed rather than observed?",
            "What evidence could invalidate each assumption?",
        ],
    ),
    (
        "quality",
        "Quality of Information Check",
        [
            "What is the original source and access?",
            "Are reports independent or copied?",
            "What is missing or contradicted?",
        ],
    ),
    (
        "signposts",
        "Indicators or Signposts of Change",
        [
            "Which observation would change this assessment?",
            "What is the monitoring source and threshold?",
            "What benign change could trigger the indicator?",
        ],
    ),
    (
        "ach",
        "Analysis of Competing Hypotheses",
        [
            "List mutually distinguishable hypotheses.",
            "Rate evidence for consistency and inconsistency.",
            "Which observation best discriminates the hypotheses?",
        ],
    ),
    (
        "devil",
        "Devil’s Advocacy",
        [
            "What is the strongest opposing explanation?",
            "What counterevidence would the prevailing analysis predict?",
        ],
    ),
    (
        "team_ab",
        "Team A/Team B",
        [
            "Record two assessments independently.",
            "Where do inputs or assumptions overlap?",
            "Preserve dissent and specify a discriminating collection task.",
        ],
    ),
    (
        "high_impact",
        "High-Impact/Low-Probability Analysis",
        [
            "What is the low-probability scenario?",
            "What assumption makes it unlikely?",
            "What indicator would warrant reassessment?",
        ],
    ),
    (
        "what_if",
        "What If? Analysis",
        [
            "If the explanation were true, what else should be observable?",
            "Which expected observations are absent?",
        ],
    ),
    (
        "brainstorm",
        "Brainstorming",
        [
            "Generate conventional and alternative explanations.",
            "Separate generation from evaluation.",
        ],
    ),
    (
        "outside_in",
        "Outside-In Thinking",
        [
            "Which external technical, social or institutional constraints matter?",
            "Could the observed pattern reflect routine processes?",
        ],
    ),
    (
        "red_team",
        "Red Team Analysis",
        [
            "Which alternative actor model is being tested?",
            "What publicly documented constraints oppose that model?",
            "Where could mirror imaging bias the assessment?",
        ],
    ),
    (
        "futures",
        "Alternative Futures Analysis",
        [
            "Define the most uncertain drivers.",
            "Construct distinct scenarios and observable signposts.",
        ],
    ),
    ("diagnostic_family", "Diagnostic Techniques", []),
    ("contrarian_family", "Contrarian Techniques", []),
    ("imaginative_family", "Imaginative Thinking Techniques", []),
]

EXECUTABLE = {
    "ach": (
        "Evidence inconsistency matrix",
        "Human-rated evidence/hypothesis matrix; dependency groups count once. Inconsistency totals are not probabilities.",
    ),
    "bayes": (
        "Bayesian hypothesis updating",
        "Likelihoods are investigator-supplied assumptions; correlated evidence must not be multiplied as independent.",
    ),
    "mad": (
        "Median Absolute Deviation / modified Z-score",
        "Numerical reference population must be specified; small samples and zero dispersion limit interpretation.",
    ),
    "iqr": (
        "Interquartile Range analysis",
        "Reference population is supplied; outlier status is a lead, not wrongdoing.",
    ),
    "calibration": (
        "Brier score calibration",
        "Requires resolved outcomes and probabilities; a small or selected set is not a model benchmark.",
    ),
    "information_gain": (
        "Expected information gain",
        "Conditional outcome probabilities and prior are user-supplied. Prioritisation is conditional on those assumptions.",
    ),
    "source_dependence": (
        "Source dependence screening",
        "Exact extract duplicates and shared shingles suggest textual dependence, not necessarily a shared original or deception.",
    ),
    "traffic": (
        "Lawful communications metadata / interval analysis",
        "Works on public or authorised event records; timing cannot establish content, intent or covert communications.",
    ),
}
PRIMARY_METHODS = {
    "source_dependence": "https://nlp.stanford.edu/IR-book/html/htmledition/near-duplicates-and-shingling-1.html",
    "bayes": "https://doi.org/10.1098/rstl.1763.0053",
    "information_gain": "https://doi.org/10.1002/j.1538-7305.1948.tb01338.x",
    "calibration": "https://scikit-learn.org/stable/modules/model_evaluation.html#brier-score-loss",
    "mad": "https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm",
    "iqr": "https://www.itl.nist.gov/div898/handbook/eda/section3/boxplot.htm",
    "traffic": "https://www.nsa.gov/portals/75/documents/about/cryptologic-heritage/historical-figures-publications/publications/misc/traffic_analysis.pdf",
}

REFERENCE_NAMES = """PEACE interviewing framework|Cognitive Interview|Crime script analysis|Geographic profiling|Behavioural investigative advice|Forensic DNA profiling|Bloodstain pattern analysis|Forensic toxicology|Forensic document examination|Social Network Analysis|Betweenness centrality|Closeness centrality|Eigenvector centrality|Louvain community detection|Leiden community detection|K-core decomposition|Beneficial ownership analysis|Trade-based money laundering analysis|Forensic accounting|Procurement collusion analysis|Denial and deception analysis|Counterintelligence analysis|Base-rate analysis|Counterfactual reasoning|Abductive reasoning|Causal inference|Process tracing|Negative evidence analysis|Missing-data mechanism analysis|Selection bias analysis|Confirmation bias mitigation|Hindsight bias mitigation|Signal detection theory|Pre-mortem analysis|Morphological analysis|Cross-impact analysis|Delphi method|Grubbs’ test|Mahalanobis distance|Principal Component Analysis|Isolation Forest|Local Outlier Factor|One-Class SVM|DBSCAN|HDBSCAN|Change-point detection|CUSUM|EWMA control charts|Benford’s Law analysis|Jensen–Shannon divergence|Kolmogorov–Smirnov testing|Forensic disk imaging|File carving|PDF object analysis|Image sensor pattern noise analysis|Geolocation by visual landmarks|Chronolocation|Shadow geometry analysis|Certificate Transparency analysis|DNS historical analysis|Kasiski examination|Friedman test|Chi-squared cipher scoring|Known-plaintext analysis|Differential cryptanalysis|Linear cryptanalysis|Side-channel analysis|Static binary analysis|Disassembly|Decompilation|Symbolic execution|Protocol state-machine inference|Software Bill of Materials analysis|Prior-art searching|Patent landscape analysis|Patent citation analysis|Patent family analysis|Patent claim charting|Freedom-to-operate analysis|Scientific citation network analysis|Systematic literature review|Meta-analysis|Replication analysis|Technology readiness level assessment""".split(
    "|"
)


def analyse(method, data):
    if method in COMPUTATIONAL:
        return compute(method, data)
    if method == "ach":
        hypotheses = data.get("hypotheses", [])
        matrix = data.get("matrix", [])
        if not 2 <= len(hypotheses) <= 20 or len(matrix) > 100:
            raise ValueError("Use 2–20 hypotheses and at most 100 evidence rows")
        scores = [0] * len(hypotheses)
        groups = defaultdict(list)
        ratings = []
        for row in matrix:
            values = row.get("ratings", [])
            if len(values) != len(hypotheses) or any(
                v not in (-2, -1, 0, 1, 2) for v in values
            ):
                raise ValueError(
                    "Each matrix row needs one rating -2 to 2 per hypothesis"
                )
            groups[row.get("dependency_group") or row["evidence_id"]].append(values)
            ratings.append(
                {
                    "evidence_id": row["evidence_id"],
                    "diagnostic_spread": max(values) - min(values),
                    "explanation": row.get("explanation", ""),
                }
            )
        for values in groups.values():
            for i in range(len(scores)):
                scores[i] += max(max(0, -v[i]) for v in values)
        return {
            "hypotheses": [
                {"name": h, "inconsistency": scores[i]}
                for i, h in enumerate(hypotheses)
            ],
            "diagnostic_evidence": sorted(
                ratings, key=lambda r: -r["diagnostic_spread"]
            ),
            "independent_groups": len(groups),
            "probability": None,
            "warning": "Inconsistency ratings are human judgments. A low score does not prove a hypothesis; source dependence and missing evidence matter.",
        }
    if method == "bayes":
        prior = float(data["prior"])
        yes = float(data["likelihood_if_true"])
        no = float(data["likelihood_if_false"])
        if any(not 0 <= n <= 1 for n in (prior, yes, no)):
            raise ValueError("Probabilities must be 0–1")
        denominator = prior * yes + (1 - prior) * no
        if denominator == 0:
            raise ValueError("Observation has zero probability under both explanations")
        return {
            "posterior": prior * yes / denominator,
            "assumptions": data,
            "warning": "Conditional calculation, not an independently measured case probability.",
        }
    if method in ("mad", "iqr"):
        numbers = [float(n) for n in data["values"]]
        if not 4 <= len(numbers) <= 10000 or any(not math.isfinite(n) for n in numbers):
            raise ValueError("Use 4–10,000 finite reference values")
        if not data.get("reference_population"):
            raise ValueError("Describe the reference population")
        median = statistics.median(numbers)
        if method == "mad":
            mad = statistics.median(abs(n - median) for n in numbers)
            scores = [0.67448975 * (n - median) / mad if mad else None for n in numbers]
            return {
                "reference_population": data["reference_population"],
                "median": median,
                "mad": mad,
                "modified_z": scores,
                "outlier_indices": [
                    i for i, v in enumerate(scores) if v is not None and abs(v) > 3.5
                ],
                "warning": "MAD is zero; score undefined, no outliers asserted."
                if not mad
                else "Threshold |modified Z| > 3.5 is exploratory; population choice and selection bias require review.",
            }
        q1, _, q3 = statistics.quantiles(numbers, n=4, method="inclusive")
        spread = q3 - q1
        return {
            "reference_population": data["reference_population"],
            "q1": q1,
            "q3": q3,
            "iqr": spread,
            "outlier_indices": [
                i
                for i, n in enumerate(numbers)
                if n < q1 - 1.5 * spread or n > q3 + 1.5 * spread
            ],
            "warning": "Quartiles use inclusive interpolation and 1.5×IQR fences. A statistical outlier does not establish misconduct.",
        }
    if method == "calibration":
        pairs = data["predictions"]
        if not 1 <= len(pairs) <= 10000 or any(
            not 0 <= float(x["probability"]) <= 1 or x["outcome"] not in (0, 1)
            for x in pairs
        ):
            raise ValueError("Use probabilities 0–1 and resolved outcomes 0/1")
        return {
            "brier_score": sum(
                (float(x["probability"]) - x["outcome"]) ** 2 for x in pairs
            )
            / len(pairs),
            "n": len(pairs),
            "warning": "Selected outcomes are not an independent benchmark; report the sampling process.",
        }
    if method == "information_gain":
        prior = [float(v) for v in data["prior"]]
        conditional = data["outcomes"]
        if (
            not 2 <= len(prior) <= 20
            or any(n < 0 or not math.isfinite(n) for n in prior)
            or abs(sum(prior) - 1) > 1e-6
        ):
            raise ValueError("Prior probabilities must be finite and sum to one")
        if not 1 <= len(conditional) <= 20 or any(
            len(row) != len(prior) for row in conditional
        ):
            raise ValueError(
                "Each outcome requires one conditional likelihood per hypothesis"
            )
        if any(not 0 <= v <= 1 for row in conditional for v in row) or any(
            abs(sum(row[i] for row in conditional) - 1) > 1e-6
            for i in range(len(prior))
        ):
            raise ValueError("Outcome likelihoods must sum to one for each hypothesis")

        def entropy(v):
            return -sum(x * math.log2(x) for x in v if x)

        expected = 0
        outcomes = []
        for row in conditional:
            joint = [a * b for a, b in zip(prior, row)]
            p = sum(joint)
            posterior = [n / p for n in joint] if p else []
            expected += p * entropy(posterior)
            outcomes.append({"probability": p, "posterior": posterior})
        return {
            "expected_information_gain_bits": entropy(prior) - expected,
            "outcomes": outcomes,
            "warning": "Collection priority depends on assumed priors and likelihoods, not a guaranteed reduction in uncertainty.",
        }
    if method == "traffic":
        records = data["records"]
        stamps = []
        links = Counter()
        if len(records) > 5000:
            raise ValueError("At most 5,000 authorised metadata records")
        for r in records:
            stamp = __import__("datetime").datetime.fromisoformat(
                r["timestamp"].replace("Z", "+00:00")
            )
            if not stamp.tzinfo:
                raise ValueError("Timestamps must include UTC offsets")
            stamps.append(stamp.timestamp())
            links[(r["source"], r["destination"])] += 1
        stamps.sort()
        intervals = [b - a for a, b in zip(stamps, stamps[1:])]
        return {
            "record_count": len(records),
            "links": [
                {"source": a, "destination": b, "count": n}
                for (a, b), n in links.items()
            ],
            "intervals_seconds": intervals,
            "median_interval": statistics.median(intervals) if intervals else None,
            "warning": "Public/authorised metadata only; no packet capture, content inference or covert surveillance performed.",
        }
    raise ValueError("No executable implementation for this method")


def install(core):
    core.execute(
        "CREATE TABLE IF NOT EXISTS method_registry(id TEXT PRIMARY KEY,data TEXT)"
    )
    core.execute(
        "CREATE TABLE IF NOT EXISTS analytic_pins(record_id TEXT,board_id TEXT,evidence_id TEXT,PRIMARY KEY(record_id,board_id))"
    )
    core.execute(
        "CREATE TABLE IF NOT EXISTS analytic_records(id TEXT PRIMARY KEY,method TEXT,created TEXT,data TEXT)"
    )
    for mid, name, questions in CIA:
        family = mid.endswith("_family")
        data = {
            "id": mid,
            "name": name,
            "discipline": "Structured intelligence analysis",
            "classification": "TECHNIQUE FAMILY" if family else "TECHNIQUE",
            "implementation": "FAMILY / REFERENCE"
            if family
            else "EXECUTABLE MATRIX"
            if mid == "ach"
            else "GUIDED HUMAN WORKFLOW",
            "primary_url": PRIMER,
            "questions": questions,
            "required_inputs": "Source-backed observations, assumptions, alternative explanations and human judgments.",
            "procedure": questions,
            "limitations": "A documented analytic practice is not a validated forensic test or an agency endorsement.",
            "validation": "Review source citations, preserve dissent and independently test predictions.",
            "false_positives": "Selection bias, dependent reporting and incomplete evidence can mimic confirmation.",
            "false_negatives": "Missing or unavailable evidence can conceal relevant alternatives.",
            "libraries": ["Python standard library"],
            "authorisation": "Public or authorised evidence only. No agency-specific privileged access.",
            "human_review": "REQUIRED",
        }
        core.execute(
            "INSERT INTO method_registry VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (mid, json.dumps(data)),
        )
    for mid, (name, limitations) in EXECUTABLE.items():
        if mid == "ach":
            continue
        data = {
            "id": mid,
            "name": name,
            "classification": "COMPUTATIONAL METHOD",
            "implementation": "EXECUTABLE",
            "discipline": "Statistics / evidence analysis",
            "primary_url": PRIMARY_METHODS[mid],
            "required_inputs": limitations,
            "procedure": "Deterministic calculation with saved inputs, parameters and evidence references.",
            "limitations": limitations,
            "validation": "Known-vector regression tests; human assessment of population and model assumptions.",
            "libraries": ["Python standard library"],
            "human_review": "REQUIRED",
            "authorisation": "Public or authorised records only.",
            "false_positives": "Poor baseline or dependence can produce misleading signals.",
            "false_negatives": "Power is limited by missing data and small sample sizes.",
        }
        core.execute(
            "INSERT INTO method_registry VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (mid, json.dumps(data)),
        )
    implemented_names = {value[0]: key for key, value in COMPUTATIONAL.items()}
    for i, name in enumerate(REFERENCE_NAMES):
        mid = f"reference-{i:03d}"
        slug = implemented_names.get(name)
        data = {
            "id": mid,
            "name": name,
            "classification": "COMPUTATIONAL METHOD"
            if slug
            else "CANDIDATE / RESEARCH REQUIRED",
            "implementation": "EXECUTABLE" if slug else "NOT IMPLEMENTED",
            "discipline": "Graph / statistics / cryptanalysis"
            if slug
            else "Investigator-supplied taxonomy",
            "primary_url": COMPUTATIONAL[slug][1]
            if slug and "wikipedia.org" not in COMPUTATIONAL[slug][1]
            else None,
            "reference_url": COMPUTATIONAL[slug][1] if slug else None,
            "required_inputs": "Cited, integrity-checked board relationships"
            if slug in GRAPH_METHODS
            else "Exact acquired text citation"
            if slug in ("kasiski", "friedman", "chi_squared")
            else "Finite observations, explicit reference population and parameters"
            if slug
            else "Method-specific specialist inputs not yet integrated.",
            "procedure": COMPUTATIONAL[slug][2] if slug else None,
            "limitations": "Results depend on the recorded inputs and assumptions; no attribution, guilt, causality or hidden-message authentication."
            if slug
            else "Listed as a research target, not source-verified or executable.",
            "validation": "Known-vector and pathological-input regression tests; human baseline review"
            if slug
            else "Primary-source verification and test fixtures required before activation.",
            "human_review": "REQUIRED",
            "authorisation": "Public or explicitly authorised material only.",
            "false_positives": "Sampling, baseline and correlated observations can create apparent anomalies."
            if slug
            else "Not assessed.",
            "false_negatives": "Missing records and weak statistical power can conceal patterns."
            if slug
            else "Not assessed.",
            "libraries": ["scikit-learn 1.9.1", "SciPy 1.18.1", "NumPy 2.5.4"]
            if slug in LEARNED_METHODS
            else ["NetworkX 3.7"]
            if slug in ("louvain", "cliques")
            else ["Python standard library"]
            if slug
            else [],
            "engine": slug,
            "example": COMPUTATIONAL[slug][3] if slug else None,
        }
        core.execute(
            "INSERT INTO method_registry VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (mid, json.dumps(data)),
        )
    for slug, (name, url, procedure, example) in COMPUTATIONAL.items():
        if name in REFERENCE_NAMES:
            continue
        core.execute(
            "INSERT INTO method_registry VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (
                slug,
                json.dumps(
                    {
                        "id": slug,
                        "name": name,
                        "classification": "COMPUTATIONAL METHOD",
                        "implementation": "EXECUTABLE",
                        "discipline": "Statistics",
                        "primary_url": url,
                        "reference_url": url,
                        "procedure": procedure,
                        "required_inputs": "Finite values with explicit sampling population and parameters",
                        "example": example,
                        "engine": slug,
                        "limitations": "Exploratory scores depend on the baseline, sampling and assumptions; not an allegation.",
                        "validation": "Known-vector and edge-case regression tests; human population review",
                        "libraries": ["Python standard library"],
                        "authorisation": "Public or authorised data only",
                        "human_review": "REQUIRED",
                        "false_positives": "Selection bias and poor baseline",
                        "false_negatives": "Low statistical power and missing records",
                    }
                ),
            ),
        )

    def citation_check(citations):
        verified = []
        for c in citations:
            if not c.get("quote"):
                raise ValueError("An exact source passage is required")
            e, meta, digest = core.forensics["source"](c["evidence_id"])
            page = c.get("page")
            text = (
                e["text"]
                if not page
                else next(
                    (x["text"] for x in meta.get("pages", []) if x["page"] == page), ""
                )
            )
            if c["quote"] not in text:
                raise ValueError(
                    "Citation passage is absent at the specified source location"
                )
            verified.append({**c, "sha256": e["sha256"], "text_sha256": digest})
        return verified

    def registry():
        methods = [
            json.loads(r["data"])
            for r in core.rows("SELECT data FROM method_registry ORDER BY rowid")
        ]
        sources = core.rows(
            "SELECT id,url,metadata,text FROM evidence WHERE sha256 IS NOT NULL AND status='ORIGINAL VERIFIED'"
        )
        for m in methods:
            m.setdefault("aliases", [])
            m["primary_evidence"] = []
            if m.get("primary_url"):
                for s in sources:
                    if s["url"].split("?")[0] == m["primary_url"].split("?")[0]:
                        meta = json.loads(s["metadata"])
                        needle = re.sub("[^a-z0-9]", "", m["name"].lower())
                        matches = [
                            p
                            for p in meta.get("pages", [])
                            if needle in re.sub("[^a-z0-9]", "", p["text"].lower())
                        ]
                        found = next(
                            (p for p in matches if p["page"] > 5),
                            matches[0] if matches else None,
                        )
                        m["primary_evidence"].append(
                            {
                                "evidence_id": s["id"],
                                "page": found["page"] if found else None,
                                "status": "NAME LOCATED IN ACQUIRED PRIMARY"
                                if found
                                else "PRIMARY ACQUIRED; METHOD CITATION REVIEW REQUIRED",
                            }
                        )
            m["verification"] = (
                "PRIMARY SOURCE ACQUIRED"
                if m["primary_evidence"]
                else "REFERENCE NOT ACQUIRED"
                if m.get("primary_url")
                else "UNVERIFIED TAXONOMY ENTRY"
            )
        return methods

    class Run(BaseModel):
        method: str
        inputs: dict = Field(default_factory=dict)
        citations: list[dict] = Field(default_factory=list, max_length=100)
        notes: str = Field(default="", max_length=10000)
        authorisation: str = Field(min_length=5, max_length=1000)

    @core.app.get("/api/tradecraft")
    def listing():
        return {
            "methods": registry(),
            "records": [
                {**r, "data": json.loads(r["data"])}
                for r in core.rows(
                    "SELECT * FROM analytic_records ORDER BY created DESC LIMIT 100"
                )
            ],
            "standard": "Source-backed records, disclosed assumptions and retained dissent; no 500-method verification claim.",
        }

    @core.app.post("/api/tradecraft/run")
    def run(value: Run):
        if len(json.dumps(value.model_dump())) > 250000:
            raise HTTPException(422, "Analysis input exceeds limit")
        methods = {m["id"]: m for m in registry()}
        if value.method not in methods or methods[value.method]["implementation"] in (
            "NOT IMPLEMENTED",
            "FAMILY / REFERENCE",
        ):
            raise HTTPException(
                422, "This entry has no executable or guided implementation"
            )
        try:
            citations = citation_check(value.citations)
            if value.method == "ach":
                ids = {c["evidence_id"] for c in citations}
                if any(
                    row.get("evidence_id") not in ids
                    for row in value.inputs.get("matrix", [])
                ):
                    raise ValueError(
                        "Every ACH row requires an exact acquired-source citation"
                    )
            if value.method == "source_dependence":
                if not 2 <= len(citations) <= 20:
                    raise ValueError("Compare 2–20 source extracts")
                sources = [
                    core.forensics["source"](c["evidence_id"])[0] for c in citations
                ]
                pairs = []

                def shingles(text):
                    words = re.findall(r"\w+", text.lower())[:10000]
                    return set(
                        tuple(words[i : i + 5]) for i in range(max(0, len(words) - 4))
                    )

                for i, a in enumerate(sources):
                    for b in sources[i + 1 :]:
                        sa, sb = shingles(a["text"]), shingles(b["text"])
                        pairs.append(
                            {
                                "left": a["id"],
                                "right": b["id"],
                                "byte_identical": a["sha256"] == b["sha256"],
                                "five_word_shingle_jaccard": len(sa & sb) / len(sa | sb)
                                if sa | sb
                                else None,
                            }
                        )
                output = {
                    "pairs": pairs,
                    "warning": "Textual similarity is a dependence lead, not proof of copying, independence, truth or deception.",
                }
            elif methods[value.method].get("engine"):
                engine = methods[value.method]["engine"]
                if engine in GRAPH_METHODS:
                    if value.inputs.get("board_id"):
                        board_graph = core.workspaces["graph"](
                            value.inputs["board_id"], documented_only=True
                        )
                        bound_edges = []
                        derived_citations = []
                        for edge in board_graph["edges"]:
                            verified = citation_check(
                                [
                                    {"evidence_id": c["id"], "quote": c["quote"]}
                                    for c in edge["data"]["evidence"]
                                ]
                            )
                            derived_citations.extend(verified)
                            bound_edges.append(
                                {
                                    "source": edge["source"],
                                    "target": edge["target"],
                                    "state": edge["data"]["state"],
                                    "evidence_id": verified[0]["evidence_id"],
                                }
                            )
                        citations = derived_citations
                        value.inputs = {
                            **value.inputs,
                            "nodes": [n["id"] for n in board_graph["nodes"]],
                            "edges": bound_edges,
                            "layer": "CITATION-VERIFIED DOCUMENTED / CORROBORATED ONLY",
                        }
                    else:
                        ids = {c["evidence_id"] for c in citations}
                        if any(
                            e.get("evidence_id") not in ids
                            or e.get("state") not in ("DOCUMENTED", "CORROBORATED")
                            for e in value.inputs.get("edges", [])
                        ):
                            raise ValueError(
                                "Every graph edge needs an exact acquired-source citation and documented review state"
                            )
                elif engine in ("kasiski", "friedman", "chi_squared"):
                    if not citations or not any(
                        value.inputs.get("text", "")
                        in core.forensics["source"](c["evidence_id"])[0]["text"]
                        for c in citations
                    ):
                        raise ValueError(
                            "Cipher analysis input must occur exactly in a cited, integrity-checked original"
                        )
                output = compute(engine, value.inputs)
            elif value.method in EXECUTABLE:
                output = analyse(value.method, value.inputs)
            else:
                questions = methods[value.method]["questions"]
                answers = value.inputs.get("answers", [])
                if len(answers) != len(questions) or any(
                    not isinstance(a, str) or not a.strip() for a in answers
                ):
                    raise ValueError(
                        "Answer every structured question; retain uncertainty and dissent"
                    )
                output = {
                    "assessment": list(zip(questions, answers)),
                    "dissent": value.inputs.get("dissent", []),
                    "collection_gaps": value.inputs.get("collection_gaps", []),
                    "human_review": "REQUIRED",
                }
        except (ValueError, TypeError, KeyError, OverflowError) as ex:
            raise HTTPException(422, str(ex))
        rid = core.uid("ANALYSIS")
        result = {
            **value.model_dump(),
            "citations": citations,
            "output": output,
            "validation": "PROVISIONAL",
            "method_version": "1.1",
            "ai_generated": False,
            "software": "SHERLOCK deterministic calculation / user-authored judgments",
            "limitations": methods[value.method]["limitations"],
        }
        core.execute(
            "INSERT INTO analytic_records VALUES(?,?,?,?)",
            (rid, value.method, core.now(), json.dumps(result)),
        )
        core.log("tradecraft_analysis_saved", {"id": rid, "method": value.method})
        return {"id": rid, **result}

    @core.app.post("/api/tradecraft/records/{rid}/pin")
    def pin(rid: str, value: dict):
        from .app import Annotation

        bid = value.get("board_id")
        with core.lock:
            records = core.rows("SELECT * FROM analytic_records WHERE id=?", (rid,))
            boards = core.rows("SELECT data FROM boards WHERE id=?", (bid,))
            if not records or not boards:
                raise HTTPException(404, "Analysis or board missing")
            prior = core.rows(
                "SELECT evidence_id FROM analytic_pins WHERE record_id=? AND board_id=?",
                (rid, bid),
            )
            if prior:
                return {
                    "board_id": bid,
                    "evidence_id": prior[0]["evidence_id"],
                    "state": "HYPOTHESIS",
                    "reused": True,
                }
            record = json.loads(records[0]["data"])
            try:
                citations = citation_check(record["citations"])
            except ValueError as ex:
                raise HTTPException(422, str(ex))
            text = (
                "PROVISIONAL ANALYSIS · "
                + records[0]["method"]
                + "\n"
                + json.dumps(record["output"], indent=2)
                + "\nDissent / notes: "
                + record["notes"]
                + "\n"
                + record["limitations"]
            )[:18000]
            note = core.annotate(
                Annotation(
                    title="Analysis · " + records[0]["method"],
                    kind="hypothesis",
                    text=text,
                    citations=[
                        {
                            "id": c["evidence_id"],
                            "quote": c["quote"],
                            "page": c.get("page"),
                        }
                        for c in citations
                    ],
                )
            )
            meta = note["metadata"]
            meta.update(
                {
                    "analysis_id": rid,
                    "validation": "PROVISIONAL",
                    "source": "Deterministic analysis / user-authored judgments; not original evidence",
                }
            )
            core.execute(
                "UPDATE evidence SET status='HYPOTHESIS',metadata=? WHERE id=?",
                (json.dumps(meta), note["id"]),
            )
            board = json.loads(boards[0]["data"])
            node_id = "analysis-" + rid
            next_x = (
                max(
                    (n.get("position", {}).get("x", 0) for n in board["nodes"]),
                    default=0,
                )
                + 450
            )
            board["nodes"].append(
                {
                    "id": node_id,
                    "type": "evidence",
                    "position": {"x": next_x, "y": 180},
                    "data": {"evidenceId": note["id"]},
                }
            )
            for c in citations:
                target = next(
                    (
                        n["id"]
                        for n in board["nodes"]
                        if n.get("data", {}).get("evidenceId") == c["evidence_id"]
                    ),
                    None,
                )
                if not target:
                    target = "source-" + c["evidence_id"]
                    board["nodes"].append(
                        {
                            "id": target,
                            "type": "evidence",
                            "position": {
                                "x": next_x + 450,
                                "y": 100 + len(board["nodes"]) * 100,
                            },
                            "data": {"evidenceId": c["evidence_id"]},
                        }
                    )
                board["edges"].append(
                    {
                        "id": core.uid("EDGE"),
                        "source": node_id,
                        "target": target,
                        "label": "Analytical input · provisional interpretation",
                        "data": {
                            "state": "HYPOTHESIS",
                            "relationship": "Analytical input",
                            "claim": "This source passage was used in a provisional analysis, not proof of the hypothesis.",
                            "evidence": [
                                {
                                    "id": c["evidence_id"],
                                    "quote": c["quote"],
                                    "page": c.get("page"),
                                }
                            ],
                            "method": "Saved deterministic analysis / human judgment",
                            "confidence": "UNVALIDATED",
                        },
                    }
                )
            core.execute(
                "UPDATE boards SET data=? WHERE id=?", (json.dumps(board), bid)
            )
            core.execute(
                "INSERT INTO analytic_pins VALUES(?,?,?)", (rid, bid, note["id"])
            )
            core.log(
                "tradecraft_analysis_pinned",
                {"record": rid, "board": bid, "state": "HYPOTHESIS"},
            )
            return {
                "board_id": bid,
                "evidence_id": note["id"],
                "state": "HYPOTHESIS",
                "reused": False,
            }

    return {"registry": registry, "run": lambda value: run(Run(**value))}

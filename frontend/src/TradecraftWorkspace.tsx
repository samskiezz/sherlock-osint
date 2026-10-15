import { useEffect, useState } from "react";
import { api, post } from "./api";
import { Play, BookOpen, ShieldCheck } from "lucide-react";
import "./collection.css";

const examples: Record<string, any> = {
  bayes: { prior: 0.1, likelihood_if_true: 0.8, likelihood_if_false: 0.2 },
  mad: {
    values: [10, 11, 12, 13, 99],
    reference_population: "Illustrative test fixture, not case evidence",
  },
  iqr: {
    values: [10, 11, 12, 13, 99],
    reference_population: "Illustrative test fixture, not case evidence",
  },
  calibration: {
    predictions: [
      { probability: 0.8, outcome: 1 },
      { probability: 0.2, outcome: 0 },
    ],
  },
  information_gain: {
    prior: [0.5, 0.5],
    outcomes: [
      [0.9, 0.1],
      [0.1, 0.9],
    ],
  },
  traffic: {
    records: [
      {
        source: "PUBLIC-A",
        destination: "PUBLIC-B",
        timestamp: "2026-01-01T12:00:00Z",
      },
      {
        source: "PUBLIC-A",
        destination: "PUBLIC-B",
        timestamp: "2026-01-01T12:05:00Z",
      },
    ],
  },
  source_dependence: {},
};
export default function TradecraftWorkspace({
  evidence,
  selectEvidence,
  notify,
  boards,
  onPin,
}: any) {
  const [data, setData] = useState<any>({ methods: [], records: [] }),
    [query, setQuery] = useState(""),
    [method, setMethod] = useState("ach"),
    [input, setInput] = useState("{}"),
    [eid, setEid] = useState(""),
    [quote, setQuote] = useState(""),
    [citations, setCitations] = useState<any[]>([]),
    [answers, setAnswers] = useState<string[]>([]),
    [dissent, setDissent] = useState(""),
    [result, setResult] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [destination, setDestination] = useState(""),
    [catalogue, setCatalogue] = useState(false),
    [monitors, setMonitors] = useState<any[]>([]);
  const refresh = () =>
    api("/tradecraft")
      .then(setData)
      .catch((e) => notify(e.message));
  useEffect(() => {
    refresh();
    const poll = () =>
      api("/analysis-monitors")
        .then(setMonitors)
        .catch((e) => notify(e.message));
    poll();
    const timer = setInterval(poll, 5000);
    return () => clearInterval(timer);
  }, []);
  const selected = data.methods.find((m: any) => m.id === method),
    originals = evidence.filter((e: any) => e.fileUrl && e.text),
    isGuided = selected?.implementation === "GUIDED HUMAN WORKFLOW";
  const choose = (mid: string) => {
    setMethod(mid);
    setAnswers([]);
    setInput(
      JSON.stringify(
        mid === "ach"
          ? {
              hypotheses: [
                "Conventional explanation",
                "Alternative explanation",
              ],
              matrix: [],
            }
          : data.methods.find((m: any) => m.id === mid)?.example ||
              examples[mid] ||
              {},
        null,
        2,
      ),
    );
  };
  const addCitation = () => {
    if (!eid || !quote.trim())
      return notify("Choose an original and exact passage");
    setCitations([...citations, { evidence_id: eid, quote }]);
    if (method === "ach") {
      try {
        const d = JSON.parse(input);
        d.matrix = [
          ...(d.matrix || []),
          {
            evidence_id: eid,
            dependency_group: eid,
            ratings: (d.hypotheses || []).map(() => 0),
            explanation:
              "Unrated: replace zero ratings with justified consistency judgments.",
          },
        ];
        setInput(JSON.stringify(d, null, 2));
      } catch {
        notify("Fix the analysis JSON first");
      }
    }
  };
  return (
    <div className="page-scroll collection-workspace">
      <div className="section-title">
        <h2>Tradecraft, competing hypotheses & analytical dissent</h2>
        <span className="status amber">PROVISIONAL · HUMAN REVIEW</span>
      </div>
      <div className="notice">
        <ShieldCheck size={18} />A documented analytic practice is distinct from
        a validated forensic test. Three CIA entries are method families.
        Unimplemented taxonomy entries remain explicitly unverified.
      </div>
      <div className="collection-actions">
        <button
          className={"button " + (!catalogue ? "primary" : "")}
          onClick={() => setCatalogue(false)}
        >
          Run analysis
        </button>
        <button
          className={"button " + (catalogue ? "primary" : "")}
          onClick={() => setCatalogue(true)}
        >
          <BookOpen size={14} /> Method catalogue · {data.methods.length}{" "}
          records
        </button>
      </div>
      {catalogue ? (
        <>
          <input
            className="field"
            placeholder="Search discipline, method or implementation state"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="method-catalogue">
            {data.methods
              .filter((m: any) =>
                (m.name + " " + m.discipline + " " + m.implementation)
                  .toLowerCase()
                  .includes(query.toLowerCase()),
              )
              .map((m: any) => (
                <details key={m.id}>
                  <summary>
                    {m.name}{" "}
                    <span className="status amber">{m.implementation}</span>
                  </summary>
                  <p>
                    {m.classification} · {m.verification}
                  </p>
                  <dl>
                    <dt>Discipline</dt>
                    <dd>{m.discipline}</dd>
                    <dt>Required inputs</dt>
                    <dd>{m.required_inputs}</dd>
                    <dt>Procedure</dt>
                    <dd>{JSON.stringify(m.procedure)}</dd>
                    <dt>Limitations</dt>
                    <dd>{m.limitations}</dd>
                    <dt>Validation</dt>
                    <dd>{m.validation}</dd>
                    <dt>False positives / negatives</dt>
                    <dd>
                      {m.false_positives} / {m.false_negatives}
                    </dd>
                    <dt>Authorisation</dt>
                    <dd>{m.authorisation}</dd>
                    <dt>Human review</dt>
                    <dd>{m.human_review}</dd>
                  </dl>
                  {m.primary_url && (
                    <a href={m.primary_url} target="_blank" rel="noreferrer">
                      Method reference URL
                    </a>
                  )}
                  {m.primary_evidence.map((p: any) => (
                    <button
                      className="button"
                      key={p.evidence_id}
                      onClick={() => selectEvidence(p.evidence_id)}
                    >
                      Acquired primary · {p.status} · page {p.page ?? "review"}
                    </button>
                  ))}
                </details>
              ))}
          </div>
        </>
      ) : (
        <>
          <label>
            Executable method / guided workflow
            <select
              className="field"
              value={method}
              onChange={(e) => choose(e.target.value)}
            >
              {data.methods
                .filter(
                  (m: any) =>
                    !["NOT IMPLEMENTED", "FAMILY / REFERENCE"].includes(
                      m.implementation,
                    ),
                )
                .map((m: any) => (
                  <option value={m.id} key={m.id}>
                    {m.name} · {m.implementation}
                  </option>
                ))}
            </select>
          </label>
          <p className="muted">{selected?.limitations}</p>
          <div className="two-col">
            <section>
              <h3>Observation and exact source citation</h3>
              <select
                className="field"
                value={eid}
                onChange={(e) => {
                  setEid(e.target.value);
                  setQuote(
                    originals
                      .find((x: any) => x.id === e.target.value)
                      ?.text?.slice(0, 350) || "",
                  );
                }}
              >
                <option value="">Choose an acquired original extract</option>
                {originals.map((e: any) => (
                  <option key={e.id} value={e.id}>
                    {e.title}
                  </option>
                ))}
              </select>
              <textarea
                className="field"
                value={quote}
                onChange={(e) => setQuote(e.target.value)}
                placeholder="Exact passage from stored source"
              />
              <button className="button" onClick={addCitation}>
                Add cited observation
              </button>
              {citations.map((c, i) => (
                <div className="cited-observation" key={i}>
                  <button onClick={() => selectEvidence(c.evidence_id)}>
                    {c.evidence_id}
                  </button>
                  <p>{c.quote}</p>
                </div>
              ))}
            </section>
            <section>
              <h3>
                {isGuided
                  ? "Structured procedure"
                  : "Inputs, ratings and assumptions · editable JSON"}
              </h3>
              {selected?.required_inputs ===
                "Cited, integrity-checked board relationships" && (
                <label>
                  Analyse sourced board relationships
                  <select
                    className="field"
                    value={(() => {
                      try {
                        return JSON.parse(input).board_id || "";
                      } catch {
                        return "";
                      }
                    })()}
                    onChange={(e) =>
                      setInput(
                        JSON.stringify({ board_id: e.target.value }, null, 2),
                      )
                    }
                  >
                    <option value="">Choose a board</option>
                    {(boards || []).map((b: any) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                  <p className="muted">
                    Only currently verified documented and corroborated edges
                    are included. Hypothesis edges are excluded. The record
                    preserves the full graph snapshot and exact source
                    citations.
                  </p>
                </label>
              )}
              {isGuided ? (
                selected.questions.map((q: string, i: number) => (
                  <label key={q}>
                    {q}
                    <textarea
                      className="field"
                      value={answers[i] || ""}
                      onChange={(e) => {
                        const a = [...answers];
                        a[i] = e.target.value;
                        setAnswers(a);
                      }}
                    />
                  </label>
                ))
              ) : (
                <textarea
                  className="field analysis-json"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                />
              )}
              <label>
                Alternative explanations / dissent
                <textarea
                  className="field"
                  value={dissent}
                  onChange={(e) => setDissent(e.target.value)}
                  placeholder="Retain the strongest opposing explanation and missing observations."
                />
              </label>
            </section>
          </div>
          <button
            className="button primary"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const value = isGuided
                  ? { answers, dissent: [dissent] }
                  : JSON.parse(input);
                setResult(
                  await post("/tradecraft/run", {
                    method,
                    inputs: value,
                    citations,
                    notes: dissent,
                    authorisation:
                      "Publicly acquired evidence or investigator-authorised test inputs; no private collection.",
                  }),
                );
                refresh();
              } catch (e: any) {
                notify(e.message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Play size={14} /> Execute & preserve analysis
          </button>
          {result && (
            <div className="experiment-result">
              <span className="status amber">{result.validation}</span>
              <h3>{result.id}</h3>
              <pre className="forensic-json">
                {JSON.stringify(result.output, null, 2)}
              </pre>
              <p>{result.limitations}</p>
              {result.inputs?.board_id && (
                <button
                  className="button"
                  onClick={async () => {
                    try {
                      await post(`/tradecraft/records/${result.id}/monitor`, {
                        interval_minutes: 15,
                      });
                      setMonitors(await api("/analysis-monitors"));
                      notify(
                        "Board graph monitored every 15 minutes; unchanged inputs create no duplicate analysis.",
                      );
                    } catch (e: any) {
                      notify(e.message);
                    }
                  }}
                >
                  Monitor this sourced graph every 15 minutes
                </button>
              )}
              <div className="collection-actions">
                <select
                  className="field"
                  value={destination}
                  onChange={(e) => setDestination(e.target.value)}
                >
                  <option value="">Choose evidence board</option>
                  {(boards || []).map((b: any) => (
                    <option value={b.id} key={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
                <button
                  className="button"
                  disabled={!destination}
                  onClick={async () => {
                    try {
                      await post(`/tradecraft/records/${result.id}/pin`, {
                        board_id: destination,
                      });
                      notify(
                        "Analysis pinned as HYPOTHESIS with source citations",
                      );
                      if (onPin) await onPin(destination);
                    } catch (e: any) {
                      notify(e.message);
                    }
                  }}
                >
                  Pin provisional analysis to board
                </button>
              </div>
            </div>
          )}
          <h3>Continuous source-board analysis</h3>
          {monitors.map((m: any) => (
            <article key={m.id} className="cited-observation">
              <strong>
                {m.board_id} · {m.method}
              </strong>
              <p>
                {m.enabled ? "RUNNING" : "PAUSED"} · {m.data.status} · next{" "}
                {new Date(m.next_due * 1000).toISOString()} ·{" "}
                {m.data.last_record_id}
              </p>
              {m.data.error && <p>{m.data.error}</p>}
              <button
                className="button"
                onClick={async () => {
                  try {
                    await api(`/analysis-monitors/${m.id}`, {
                      method: "PATCH",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ enabled: !m.enabled }),
                    });
                    setMonitors(await api("/analysis-monitors"));
                  } catch (e: any) {
                    notify(e.message);
                  }
                }}
              >
                {m.enabled ? "Pause monitor" : "Resume monitor"}
              </button>
            </article>
          ))}
          <h3>Persistent analysis records and dissent</h3>
          {data.records.map((r: any) => (
            <button
              className="experiment-history"
              key={r.id}
              onClick={() => setResult({ id: r.id, ...r.data })}
            >
              <span>
                {r.method}
                <small>{r.id}</small>
              </span>
              <span className="status amber">{r.data.validation}</span>
            </button>
          ))}
        </>
      )}
    </div>
  );
}

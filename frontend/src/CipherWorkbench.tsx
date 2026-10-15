import { useEffect, useState } from "react";
import { api, post } from "./api";
import {
  FlaskConical,
  Play,
  ScanEye,
  Pause,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import "./forensics.css";
import CryptoWorkbench from "./CryptoWorkbench";

export default function CipherWorkbench({ evidence, notify }: any) {
  const [tab, setTab] = useState("cipher"),
    [methods, setMethods] = useState<Record<string, string>>({}),
    [input, setInput] = useState("436f6c6520416c6c656e"),
    [control, setControl] = useState("52616e646f6d206e616d65"),
    [method, setMethod] = useState("hex"),
    [eid, setEid] = useState(""),
    [params, setParams] = useState<any>({
      shift: 13,
      key: "KEY",
      rails: 3,
      a: 5,
      b: 8,
      offset: 1,
      period: 5,
      square_keyword: "",
    }),
    [holdout, setHoldout] = useState(""),
    [expected, setExpected] = useState(""),
    [result, setResult] = useState<any>(null),
    [history, setHistory] = useState<any[]>([]),
    [data, setData] = useState<any>({ runs: [], settings: { enabled: true } }),
    [selected, setSelected] = useState(""),
    [view, setView] = useState("original"),
    [right, setRight] = useState(""),
    [comparison, setComparison] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [run, setRun] = useState<any>(null);
  const refresh = () =>
    api("/forensics")
      .then(setData)
      .catch((e) => notify(e.message));
  useEffect(() => {
    api("/cipher/methods").then((x) => setMethods(x.methods));
    api("/experiments").then(setHistory);
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);
  const images = evidence.filter(
      (e: any) => e.mime?.startsWith("image/") && e.fileUrl,
    ),
    image = images.find((e: any) => e.id === selected) || images[0],
    analysis = image?.metadata?.image_forensics;
  const execute = async (fn: () => Promise<any>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e: any) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page-scroll forensic-workspace">
      <div className="section-title">
        <h2>Cipher & digital forensics laboratory</h2>
        <span className="status purple">REPRODUCIBLE · SOURCE PRESERVED</span>
      </div>
      <div className="forensic-tabs">
        {[
          ["cipher", "Ciphers & word puzzles"],
          ["images", "Image diagnostics"],
          ["crypto", "Modern encryption"],
          ["automation", "Automatic screening"],
        ].map(([v, l]) => (
          <button
            key={v}
            className={"button " + (tab === v ? "primary" : "")}
            onClick={() => setTab(v)}
          >
            {v === "images" ? (
              <ScanEye size={16} />
            ) : (
              <FlaskConical size={16} />
            )}{" "}
            {l}
          </button>
        ))}
      </div>
      <div className="notice">
        <ShieldCheck size={18} /> Results remain unvalidated. Readable words,
        unusual pixels, or a matching test vector do not prove a hidden message
        or image manipulation.
      </div>
      {tab === "cipher" && (
        <>
          <form
            className="cipher-form"
            onSubmit={(e) => {
              e.preventDefault();
              execute(async () => {
                setResult(
                  await post("/cipher", {
                    input,
                    control,
                    method,
                    evidence_id: eid || null,
                    parameters: params,
                    holdout_input: holdout,
                    holdout_expected: expected,
                  }),
                );
                setHistory(await api("/experiments"));
              });
            }}
          >
            <div className="two-col">
              <label>
                Source evidence
                <select
                  className="field"
                  value={eid}
                  onChange={(e) => {
                    setEid(e.target.value);
                    if (e.target.value)
                      setInput(
                        evidence
                          .find((x: any) => x.id === e.target.value)
                          ?.text?.slice(0, 4000) || "",
                      );
                  }}
                >
                  <option value="">Manual test input</option>
                  {evidence
                    .filter((e: any) => e.fileUrl)
                    .map((e: any) => (
                      <option value={e.id} key={e.id}>
                        {e.title}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Transformation · {Object.keys(methods).length} methods
                <select
                  className="field"
                  value={method}
                  onChange={(e) => {
                    const next = e.target.value;
                    setMethod(next);
                    setParams((old: any) => ({
                      ...old,
                      key:
                        next === "hill2"
                          ? "3,3,2,5"
                          : next === "gronsfeld"
                            ? "31415"
                            : next === "playfair"
                              ? "MONARCHY"
                              : next === "autokey"
                                ? "QUEENLY"
                                : "KEY",
                    }));
                  }}
                >
                  {Object.entries(methods).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="two-col">
              <label>
                Exact original input
                <textarea
                  className="field code-input"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                />
              </label>
              <label>
                Unrelated negative control
                <textarea
                  className="field code-input"
                  value={control}
                  onChange={(e) => setControl(e.target.value)}
                />
              </label>
            </div>
            <div className="parameter-grid">
              {(method === "rot"
                ? ["shift"]
                : [
                      "vigenere",
                      "beaufort",
                      "columnar",
                      "xor",
                      "playfair",
                      "hill2",
                      "gronsfeld",
                      "autokey",
                    ].includes(method)
                  ? ["key"]
                  : method === "bifid"
                    ? ["square_keyword", "period"]
                    : method === "adfgx"
                      ? ["key", "square_keyword"]
                      : method === "rail_fence"
                        ? ["rails"]
                        : method === "affine"
                          ? ["a", "b"]
                          : method === "nth_letters"
                            ? ["offset"]
                            : []
              ).map((k) => (
                <label key={k}>
                  {k}
                  <input
                    className="field"
                    type={
                      ["key", "square_keyword"].includes(k) ? "text" : "number"
                    }
                    value={params[k]}
                    onChange={(e) =>
                      setParams({
                        ...params,
                        [k]: ["key", "square_keyword"].includes(k)
                          ? e.target.value
                          : Number(e.target.value),
                      })
                    }
                  />
                </label>
              ))}
            </div>
            {[
              "hill2",
              "playfair",
              "gronsfeld",
              "autokey",
              "bifid",
              "adfgx",
            ].includes(method) && (
              <p className="muted">
                {method === "hill2"
                  ? "Matrix key: four comma-separated integers; determinant must be invertible modulo 26. Even-length letters required."
                  : method === "gronsfeld"
                    ? "Numeric key only; the repeated digit sequence defines the shifts."
                    : method === "autokey"
                      ? "ASCII-letter initial key; recovered plaintext extends the key."
                      : method === "adfgx"
                        ? "Columnar transposition key plus I/J Polybius square keyword; ciphertext uses only A, D, F, G, X."
                        : method === "bifid"
                          ? "I/J square keyword and block period (1–100); period changes the coordinate regrouping."
                          : "I/J square keyword; digraph padding remains in the decoded output."}
              </p>
            )}
            {method === "scrabble" && (
              <>
                <label>
                  Optional dictionary · whitespace-separated words
                  <textarea
                    className="field"
                    placeholder="Leave empty for the curated demonstration lexicon. Supply your own dictionary for wider coverage."
                    value={params.dictionary || ""}
                    onChange={(e) =>
                      setParams({ ...params, dictionary: e.target.value })
                    }
                  />
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={!!params.exact}
                    onChange={(e) =>
                      setParams({ ...params, exact: e.target.checked })
                    }
                  />{" "}
                  Use every rack tile · ? is a blank. Tile scores exclude board
                  multipliers.
                </label>
              </>
            )}
            <details>
              <summary>
                Holdout test · use unseen input with the same parameters
              </summary>
              <div className="two-col">
                <label>
                  Holdout input
                  <textarea
                    className="field"
                    value={holdout}
                    onChange={(e) => setHoldout(e.target.value)}
                  />
                </label>
                <label>
                  Expected output
                  <textarea
                    className="field"
                    value={expected}
                    onChange={(e) => setExpected(e.target.value)}
                  />
                </label>
              </div>
            </details>
            <button disabled={busy} className="button primary">
              <Play size={14} /> Run & preserve experiment
            </button>
          </form>
          {result && (
            <div className="experiment-result">
              <span className="eyebrow">
                {result.id} · ATTEMPT {result.attempt_number} · ENGINE{" "}
                {result.engine_version}
              </span>
              <div className="two-col">
                <div>
                  <h4>Transformed output</h4>
                  <pre>{result.output}</pre>
                </div>
                <div>
                  <h4>Control output</h4>
                  <pre>{result.control_output || "No control supplied"}</pre>
                </div>
              </div>
              <span className="status amber">
                UNVALIDATED · HOLDOUT {result.holdout?.status || "NOT RUN"}
              </span>
              <p>
                Entropy {result.entropy.toFixed(3)} bits/character · Coincidence
                index{" "}
                {result.statistics?.index_of_coincidence?.toFixed(4) || "—"}
              </p>
              <p>{result.warning}</p>
              {result.holdout?.output && <pre>{result.holdout.output}</pre>}
              {result.source_record && (
                <small>
                  Exact extract offset {result.source_record.offset} ·{" "}
                  {result.source_record.sha256}
                </small>
              )}
            </div>
          )}
          <h3 className="history-title">
            Experiment history{" "}
            <small>{history.length} preserved attempts</small>
          </h3>
          {history.slice(0, 60).map((h) => (
            <button
              key={h.id}
              className="experiment-history"
              onClick={() => setResult(h)}
            >
              <FlaskConical size={15} />
              <span>
                {h.method.toUpperCase()}
                <small>{h.id}</small>
              </span>
              <code>{h.output.slice(0, 90)}</code>
              <span className="status amber">{h.validation}</span>
            </button>
          ))}
        </>
      )}
      {tab === "crypto" && <CryptoWorkbench notify={notify} />}
      {tab === "images" && (
        <>
          <div className="two-col">
            <label>
              Preserved image
              <select
                className="field"
                value={image?.id || ""}
                onChange={(e) => {
                  setSelected(e.target.value);
                  setView("original");
                }}
              >
                {images.map((e: any) => (
                  <option key={e.id} value={e.id}>
                    {e.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Inspection view
              <select
                className="field"
                value={view}
                onChange={(e) => setView(e.target.value)}
              >
                {["original", ...(analysis?.views || [])].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </label>
          </div>
          {image ? (
            <>
              <div className="diagnostic-image">
                <img
                  alt={`${view} diagnostic for ${image.title}`}
                  src={
                    view === "original"
                      ? image.fileUrl
                      : `/api/evidence/${image.id}/diagnostic/${view}`
                  }
                />
                <span>
                  {image.title} · {view.toUpperCase()} ·{" "}
                  {image.metadata.dimensions?.join(" × ")} · original SHA-256{" "}
                  {image.sha256}
                </span>
              </div>
              {analysis ? (
                <>
                  <div className="forensic-metrics">
                    {analysis.channel_statistics.map((c: any) => (
                      <article key={c.channel}>
                        <h4>{c.channel.toUpperCase()} CHANNEL</h4>
                        <p>
                          Mean {c.mean.toFixed(2)} · σ{" "}
                          {c.standard_deviation.toFixed(2)}
                        </p>
                        <p>Entropy {c.entropy.toFixed(3)} bits</p>
                        <p>
                          Sampled LSB ones{" "}
                          {(
                            100 * analysis.lsb.channels[c.channel].one_fraction
                          ).toFixed(2)}
                          %
                        </p>
                      </article>
                    ))}
                  </div>
                  <div className="notice">
                    {view === "lsb"
                      ? analysis.lsb.warning
                      : analysis.jpeg_residual.warning}
                  </div>
                  <details>
                    <summary>
                      Technical checks & benign recompression controls
                    </summary>
                    <pre className="forensic-json">
                      {JSON.stringify(analysis, null, 2)}
                    </pre>
                  </details>
                </>
              ) : (
                <p>
                  Digital diagnostics have not been generated for this original.
                  Existing files need reprocessing; newly acquired images are
                  analysed automatically.
                </p>
              )}
              <div className="two-col">
                <label>
                  Compare another original
                  <select
                    className="field"
                    value={right}
                    onChange={(e) => setRight(e.target.value)}
                  >
                    <option value="">Choose image</option>
                    {images.map((e: any) => (
                      <option key={e.id} value={e.id}>
                        {e.title}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="button"
                  disabled={!right || busy}
                  onClick={() =>
                    execute(async () =>
                      setComparison(
                        await api(
                          `/forensics/compare?left=${image.id}&right=${right}`,
                        ),
                      ),
                    )
                  }
                >
                  Compare hashes & dimensions
                </button>
              </div>
              {comparison && (
                <pre className="forensic-json">
                  {JSON.stringify(comparison, null, 2)}
                </pre>
              )}
            </>
          ) : (
            <p>No original images acquired.</p>
          )}
        </>
      )}
      {tab === "automation" && (
        <>
          <div className="automation-header">
            <div>
              <h3>Continuous forensic screening</h3>
              <p>
                Checks new attested evidence every 30 seconds. Completed input
                fingerprints survive restarts and prevent duplicate runs.
              </p>
            </div>
            <button
              className="button"
              onClick={() =>
                execute(async () => {
                  await api("/forensics/settings", {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      ...data.settings,
                      enabled: !data.settings.enabled,
                    }),
                  });
                  refresh();
                })
              }
            >
              {data.settings.enabled ? <Pause size={14} /> : <Play size={14} />}{" "}
              {data.settings.enabled
                ? "Pause automatic screening"
                : "Resume automatic screening"}
            </button>
          </div>
          <div className="forensic-metrics">
            <article>
              <h4>{data.settings.enabled ? "RUNNING" : "PAUSED"}</h4>
              <p>Durable automatic worker</p>
            </article>
            <article>
              <h4>{data.runs.length} runs</h4>
              <p>
                {data.attempts_total} transformations attempted in displayed
                runs
              </p>
            </article>
            <article>
              <h4>51 rules / text</h4>
              <p>
                19 shuffled controls per transformation rule · bounded
                4,000-character input
              </p>
            </article>
          </div>
          <label>
            Screen an acquired original
            <select
              className="field"
              value={eid}
              onChange={(e) => setEid(e.target.value)}
            >
              <option value="">Select evidence</option>
              {evidence
                .filter((e: any) => e.fileUrl)
                .map((e: any) => (
                  <option key={e.id} value={e.id}>
                    {e.title}
                  </option>
                ))}
            </select>
          </label>
          <button
            className="button"
            disabled={!eid || busy}
            onClick={() =>
              execute(async () => {
                setRun(await post(`/forensics/${eid}/screen`, {}));
                refresh();
              })
            }
          >
            <RefreshCw size={14} /> Screen & preserve result
          </button>
          <h3>Screening history</h3>
          {data.runs.map((r: any) => (
            <button
              key={r.id}
              className="experiment-history"
              onClick={() =>
                api(`/forensics/runs/${r.id}`)
                  .then(setRun)
                  .catch((e) => notify(e.message))
              }
            >
              <ScanEye size={15} />
              <span>
                {evidence.find((e: any) => e.id === r.evidence_id)?.title ||
                  r.evidence_id}
                <small>{r.id}</small>
              </span>
              <span>{r.data.attempt_count || 0} attempts</span>
              <span className="status amber">{r.status}</span>
            </button>
          ))}
          {run && (
            <div className="experiment-result">
              <h3>
                {run.id} · {run.status}
              </h3>
              <p>{run.data.warning}</p>
              <p>
                Input offset {run.data.input_offset} ·{" "}
                {run.data.input_truncated ? "TRUNCATED" : "COMPLETE INPUT"} ·
                Original unchanged: {String(run.data.original_unchanged)}
              </p>
              {run.data.attempts
                ?.filter((a: any) => ["OUTPUT", "ANALYSIS"].includes(a.status))
                .map((a: any, i: number) => (
                  <details key={i}>
                    <summary>
                      {a.method} {JSON.stringify(a.parameters)} · exploratory
                      score {a.readability ?? "not applicable"} · adjusted p{" "}
                      {a.adjusted_p ?? "not available"}
                    </summary>
                    <pre>{a.output}</pre>
                    <small>
                      {a.controls.length} attempted controls ·{" "}
                      {a.controls.filter((x: any) => x !== null).length} valid ·
                      seed {run.data.seed}
                    </small>
                  </details>
                ))}
              <details>
                <summary>Every attempt, failure & control</summary>
                <pre className="forensic-json">
                  {JSON.stringify(run.data, null, 2)}
                </pre>
              </details>
            </div>
          )}
        </>
      )}
    </div>
  );
}

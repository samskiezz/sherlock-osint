import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  Activity,
  ArrowRight,
  Download,
  FileText,
  Search,
  Upload,
  Wrench,
} from "lucide-react";
import { api, post } from "./api";
import "./results.css";

const label = (s: string) => s.replaceAll("_", " ").replaceAll(".", " · ");
const stateLabel = (s: string) =>
  ({
    COMPLETE: "Analysis complete",
    PARTIAL: "Complete with issues",
    BLOCKED: "Needs attention",
    PENDING: "Analysis pending",
    QUEUED: "Queued",
    RUNNING: "Analyzing",
    PAUSED: "Paused",
    FAILED: "Analysis failed",
  })[s] || label(s);

export function ReadableValue({
  value,
  depth = 0,
}: {
  value: any;
  depth?: number;
}) {
  const [all, setAll] = useState(false);
  if (value === null || value === undefined)
    return <span className="result-muted">No value reported</span>;
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>;
  if (Array.isArray(value)) {
    if (!value.length)
      return <p className="result-negative">No matches in the tested input.</p>;
    const rows = all ? value : value.slice(0, 15);
    const columns = value.every(
      (v) => v && typeof v === "object" && !Array.isArray(v),
    )
      ? [...new Set(value.flatMap((v) => Object.keys(v)))].slice(0, 8)
      : [];
    return (
      <div className="readable-list">
        {columns.length && depth < 4 ? (
          <div className="result-table-scroll">
            <table>
              <thead>
                <tr>
                  {columns.map((k) => (
                    <th key={k}>{label(k)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((v, i) => (
                  <tr key={i}>
                    {columns.map((k) => (
                      <td key={k}>
                        <ReadableValue value={v[k]} depth={depth + 1} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <ul>
            {rows.map((v, i) => (
              <li key={i}>
                <ReadableValue value={v} depth={depth + 1} />
              </li>
            ))}
          </ul>
        )}
        {!all && value.length > 15 && (
          <button className="result-link" onClick={() => setAll(true)}>
            Show all {value.length} entries
          </button>
        )}
      </div>
    );
  }
  if (typeof value === "object") {
    if (depth > 6)
      return (
        <details>
          <summary>Nested details</summary>
          <pre>{JSON.stringify(value, null, 2)}</pre>
        </details>
      );
    return (
      <dl className="readable-fields">
        {Object.entries(value).map(([k, v]) => (
          <div key={k}>
            <dt>{label(k)}</dt>
            <dd>
              <ReadableValue value={v} depth={depth + 1} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }
  return <span className="readable-text">{String(value)}</span>;
}

function CheckResult({ check }: { check: any }) {
  return (
    <details
      className={`result-check ${check.status === "COMPLETE" ? "" : "result-warning"}`}
    >
      <summary>
        <span>
          <strong>{check.title}</strong>
          <small>{check.summary}</small>
        </span>
        <span className="result-tag">{label(check.status)}</span>
      </summary>
      <div className="result-check-body">
        {check.error && <p role="alert">{check.error}</p>}
        {check.status === "COMPLETE" && <ReadableValue value={check.output} />}
        {check.limitations && (
          <div className="result-caveat">
            <strong>Interpretation limits</strong>
            <ReadableValue value={check.limitations} />
          </div>
        )}
        <small>
          {check.tool}
          {check.finished
            ? ` · ${new Date(check.finished).toLocaleString()}`
            : ""}
        </small>
      </div>
    </details>
  );
}

function Notebook({
  report,
  openEvidence,
  navigate,
  retry,
  reprocess,
  busy,
}: any) {
  const s = report.source;
  return (
    <article className="source-notebook" aria-label="Source analysis report">
      <div className="result-section-head">
        <span
          className={`result-tag ${report.state === "BLOCKED" || report.state === "PARTIAL" ? "warning" : ""}`}
        >
          {stateLabel(report.state)}
        </span>
        <small>
          {report.integrity === "VERIFIED"
            ? "Source hashes verified"
            : "Source unavailable"}
        </small>
      </div>
      <h2>{s.title}</h2>
      {s.preview_url && s.mime.startsWith("image/") && (
        <img
          className="result-source-preview"
          src={s.preview_url}
          alt={`Preserved source preview: ${s.title}`}
        />
      )}
      <div className="result-actions">
        {report.can_reprocess && (
          <button className="button" onClick={reprocess} disabled={busy}>
            Retry extraction and analysis
          </button>
        )}
        <button
          className="button"
          onClick={retry}
          disabled={
            busy ||
            ["QUEUED", "RUNNING", "PAUSED"].includes(report.state) ||
            report.integrity !== "VERIFIED"
          }
        >
          Retry automatic analysis
        </button>
        <button className="button" onClick={() => openEvidence(s.id)}>
          <FileText size={14} />
          Read original
        </button>
        <a
          className="button"
          href={`/api/results/${encodeURIComponent(s.id)}/report`}
          download
        >
          <Download size={14} />
          Download report
        </a>
        <button
          className="button"
          onClick={() => navigate("tools", { source: s.id })}
        >
          <Wrench size={14} />
          All tools for this source
        </button>
      </div>
      <p className="result-muted">
        {s.mime} · {(s.size / 1024).toFixed(1)} KB · acquired{" "}
        {new Date(s.created).toLocaleDateString()}
      </p>
      {report.reason && <p className="result-notice">{report.reason}</p>}
      <section className="source-reading" aria-label="Source reading">
        <h3>What the source says</h3>
        <p className="result-muted">
          Exact excerpts from the preserved extract. Source statements remain
          attributed to their author.
        </p>
        {report.reading.length ? (
          report.reading.map((p: any) => (
            <figure key={p.start}>
              <blockquote>{p.quote}</blockquote>
              <figcaption>
                <button
                  className="result-link"
                  onClick={() => openEvidence(s.id, p.quote)}
                >
                  Read passage in context <ArrowRight size={12} />
                </button>
                <span>
                  Characters {p.start}–{p.end}
                </span>
              </figcaption>
            </figure>
          ))
        ) : (
          <p className="result-negative">
            No verified text is available for reading. See the attention items
            below.
          </p>
        )}
      </section>
      {report.issues.length > 0 && (
        <section className="result-notice" aria-label="Attention needed">
          <h3>Attention needed</h3>
          <ul>
            {report.issues.map((v: string, i: number) => (
              <li key={i}>{v}</li>
            ))}
          </ul>
        </section>
      )}
      <section aria-label="Extracted information">
        <h3>Extracted information</h3>
        {report.information.length ? (
          <div className="extracted-information">
            {report.information.map((v: any) => (
              <details key={v.label} open>
                <summary>{v.label}</summary>
                <ReadableValue value={v.value} />
              </details>
            ))}
          </div>
        ) : (
          <p className="result-muted">
            Literal identifiers, dates, links and terms appear here as their
            checks finish.
          </p>
        )}
      </section>
      <section aria-label="All saved analysis results">
        {report.active_pass && (
          <p className="result-muted">
            Current automatic pass:{" "}
            {report.active_pass.total - report.active_pass.remaining}/
            {report.active_pass.total} steps finished. Previous valid outputs
            stay readable below.
          </p>
        )}
        <div className="result-section-head">
          <h3>Analysis results</h3>
          <span>
            {report.progress.complete} completed · {report.progress.failed}{" "}
            failed or withheld · {report.progress.total} planned/saved
          </span>
        </div>
        {report.progress.total > 0 && (
          <progress
            aria-label="Completed analysis checks"
            value={
              report.progress.complete +
              report.progress.failed +
              report.progress.skipped
            }
            max={report.progress.total}
          />
        )}
        <p className="result-muted">
          Open any check to read its full saved output, including negative
          results. Opening a result never reruns it.
        </p>
        {report.checks.map((c: any) => (
          <CheckResult key={c.id} check={c} />
        ))}
        {!report.checks.length && (
          <p className="result-negative">
            No tool receipts yet. The source reading above is available while
            automatic analysis is queued.
          </p>
        )}
        {report.extra_results_truncated && (
          <p className="result-notice">
            The newest 100 additional specialist checks are shown. Older
            receipts remain in workflow history.
          </p>
        )}
      </section>
      <details className="result-provenance">
        <summary>Provenance, coverage and machine-readable data</summary>
        <dl>
          <dt>Evidence ID</dt>
          <dd>{s.id}</dd>
          <dt>Original SHA-256</dt>
          <dd>{s.sha256}</dd>
          <dt>Extract SHA-256</dt>
          <dd>{s.text_sha256}</dd>
          <dt>Source</dt>
          <dd>{s.url || "User import"}</dd>
        </dl>
        <p>{report.scope}</p>
        <button className="result-link" onClick={() => navigate("entities")}>
          Open entity and lineage browser
        </button>
        <a
          className="result-link"
          href={`/api/results/${encodeURIComponent(s.id)}/report?format=json`}
          download
        >
          Download full JSON report
        </a>
        <details>
          <summary>
            Automatic applicability decisions ({report.coverage.length})
          </summary>
          <ReadableValue value={report.coverage} />
        </details>
      </details>
    </article>
  );
}

export default function ResultsWorkspace({
  openEvidence,
  navigate,
  onAcquire,
  onChange,
}: any) {
  const [data, setData] = useState<any>(null),
    [report, setReport] = useState<any>(null);
  const [brief, setBrief] = useState<any>(null),
    [briefError, setBriefError] = useState("");
  const [source, setSource] = useState(
    new URLSearchParams(location.search).get("source") || "",
  );
  const [query, setQuery] = useState(""),
    [filter, setFilter] = useState(""),
    [offset, setOffset] = useState(0);
  const [error, setError] = useState(""),
    [reportError, setReportError] = useState("");
  const [revision, setRevision] = useState(0),
    [busy, setBusy] = useState("");
  useEffect(() => {
    let active = true,
      timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const v = await api("/case/briefing");
        if (active) {
          setBrief(v);
          setBriefError("");
        }
      } catch (e: any) {
        if (active) setBriefError(e.message);
      }
      if (active) timer = setTimeout(refresh, 20000);
    }
    refresh();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [revision]);
  useEffect(() => {
    let active = true,
      timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const value = await api(
          `/results?q=${encodeURIComponent(filter)}&offset=${offset}`,
        );
        if (active) {
          setData(value);
          setError("");
        }
      } catch (e: any) {
        if (active) setError(e.message);
      }
      if (active) timer = setTimeout(refresh, 5000);
    }
    refresh();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [filter, offset, revision]);
  useEffect(() => {
    if (!source && data?.items.length) setSource(data.items[0].source.id);
  }, [data, source]);
  useEffect(() => {
    const pop = () =>
      setSource(new URLSearchParams(location.search).get("source") || "");
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, []);
  useEffect(() => {
    if (!source) {
      setReport(null);
      return;
    }
    let active = true,
      timer: ReturnType<typeof setTimeout>;
    setReport(null);
    setReportError("");
    async function refresh() {
      try {
        const value = await api(`/results/${encodeURIComponent(source)}`);
        if (active) {
          setReport(value);
          setReportError("");
        }
      } catch (e: any) {
        if (active) setReportError(e.message);
      }
      if (active) timer = setTimeout(refresh, 5000);
    }
    refresh();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [source, revision]);
  function select(id: string) {
    setSource(id);
    const u = new URL(location.href);
    u.searchParams.set("view", "results");
    u.searchParams.set("source", id);
    history.pushState({}, "", u);
  }
  async function importFiles(files: FileList | null) {
    if (!files?.length) return;
    try {
      for (const [i, file] of Array.from(files).entries()) {
        if (file.size > 25 * 1024 * 1024)
          throw new Error(`${file.name}: the file limit is 25 MB`);
        setBusy(
          `Preserving and extracting ${i + 1}/${files.length}: ${file.name}`,
        );
        const form = new FormData();
        form.append("file", file);
        const e = await api("/upload", { method: "POST", body: form });
        select(e.id);
        setRevision((v) => v + 1);
      }
      await onChange();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }
  async function recover() {
    setBusy("Queuing pending compatible analysis…");
    try {
      await post("/autopilot/scan", { limit: 50 });
      setRevision((v) => v + 1);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }
  async function retrySource() {
    setBusy(
      "Queuing a fresh automatic pass; previous receipts stay in workflow history…",
    );
    try {
      await post("/autopilot/scan", {
        evidence_id: source,
        limit: 1,
        force: true,
      });
      setRevision((v) => v + 1);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }
  async function reprocessSource() {
    setBusy(
      "Re-extracting the preserved original; compatible analysis follows automatically…",
    );
    try {
      await post(`/evidence/${encodeURIComponent(source)}/process`, {});
      setRevision((v) => v + 1);
      await onChange();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }
  return (
    <div className="page-scroll results-workspace">
      <div className="results-intro">
        <div>
          <span className="result-eyebrow">
            EVIDENCE → ANALYSIS → READABLE RESULTS
          </span>
          <h2>Your case results</h2>
          <p>
            Add an original. Extraction and compatible analysis run
            automatically. Read the source, findings and limits together here.
          </p>
        </div>
        <div className="result-actions">
          <label className={`button primary ${busy ? "disabled" : ""}`}>
            <Upload size={15} />
            Add files
            <input
              type="file"
              multiple
              hidden
              disabled={!!busy}
              onChange={(e) => {
                importFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </label>
          <button className="button" onClick={onAcquire}>
            Add public URL
          </button>
          <a className="button" href="/api/results/report" download>
            <Download size={14} />
            Case report
          </a>
        </div>
      </div>
      {busy && (
        <p role="status" className="result-notice">
          <Activity size={15} /> {busy}
        </p>
      )}
      {error && (
        <div role="alert" className="result-notice">
          {error}
          <button
            className="result-link"
            onClick={() => setRevision((v) => v + 1)}
          >
            Retry loading results
          </button>
        </div>
      )}
      {!data && !error && <p role="status">Loading saved results…</p>}
      {data && (
        <>
          <div className="results-metrics">
            <div>
              <strong>{data.summary.originals}</strong>
              <span>preserved originals</span>
            </div>
            <div>
              <strong>{data.summary.saved_checks}</strong>
              <span>saved checks · verified on opening</span>
            </div>
            <div>
              <strong>{data.summary.pending_acquisitions}</strong>
              <span>sources being acquired</span>
            </div>
            <div>
              <strong>{data.automation.enabled ? "On" : "Paused"}</strong>
              <span>
                automatic analysis{" "}
                {data.automation.worker_alive
                  ? "· worker active"
                  : "· worker not reporting"}
              </span>
            </div>
          </div>
          <section
            className="case-results-findings"
            aria-label="Case conclusions and questions"
          >
            <div className="result-section-head">
              <h3>Case findings</h3>
              {brief && (
                <span>
                  {brief.documented_count} documented · {brief.measured_count}{" "}
                  measured · {brief.proposal_count} AI proposals
                </span>
              )}
            </div>
            {briefError && (
              <p role="alert">Case findings could not load: {briefError}</p>
            )}
            {brief?.findings.length === 0 && (
              <p className="result-muted">
                No source-verified case conclusions are saved yet. The source
                readings and completed checks below remain available; missing
                originals and proposed claims are listed separately.
              </p>
            )}
            {brief?.findings.map((f: any) => (
              <details className="result-check" key={f.id}>
                <summary>
                  <span>
                    <strong>{f.statement}</strong>
                    <small>
                      {f.kind}
                      {f.kind === "AI PROPOSAL"
                        ? " · Interpretation requires review"
                        : ""}
                    </small>
                  </span>
                </summary>
                <div className="result-check-body">
                  <p>{f.limits}</p>
                  {f.sources.map((s: any) => (
                    <figure key={s.evidence_id + s.quote}>
                      <blockquote>{s.quote}</blockquote>
                      <button
                        className="result-link"
                        onClick={() => openEvidence(s.evidence_id, s.quote)}
                      >
                        {s.title} · Read supporting passage
                      </button>
                    </figure>
                  ))}
                </div>
              </details>
            ))}
            {!!brief?.open_questions.length && (
              <details className="open-case-questions">
                <summary>
                  {brief.open_questions.length} open case questions — read what
                  is still unverified
                </summary>
                {brief.open_questions.map((q: any, i: number) => (
                  <div key={i}>
                    <h4>{q.statement}</h4>
                    <p>{q.reason}</p>
                  </div>
                ))}
              </details>
            )}
          </section>
          <div className="results-toolbar">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setFilter(query);
                setOffset(0);
              }}
            >
              <Search size={15} />
              <input
                aria-label="Search source results"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search source titles or extracted text"
              />
              <button type="submit" className="button">
                Search
              </button>
            </form>
            <button className="button" disabled={!!busy} onClick={recover}>
              Analyze pending now
            </button>
            <button className="button" onClick={() => navigate("tools")}>
              Browse all tools & workspaces
            </button>
          </div>
          <div className="results-layout">
            <section
              className="result-source-list"
              aria-label="Analysed sources"
            >
              {data.items.map((r: any) => (
                <button
                  key={r.source.id}
                  onClick={() => select(r.source.id)}
                  className={`result-source-card ${source === r.source.id ? "selected" : ""}`}
                >
                  <span className="result-tag">{stateLabel(r.state)}</span>
                  <h3>{r.source.title}</h3>
                  <p>
                    {r.reading[0]?.quote ||
                      r.reason ||
                      r.issues[0] ||
                      "Waiting for an attested extract"}
                  </p>
                  <small>
                    {r.progress.complete}/{r.progress.total} checks complete
                    {r.progress.failed
                      ? ` · ${r.progress.failed} need attention`
                      : ""}
                  </small>
                  <span className="result-link">
                    Read results <ArrowRight size={13} />
                  </span>
                </button>
              ))}
              {!data.items.length && (
                <div className="result-empty">
                  <FileText size={26} />
                  <h3>
                    {filter ? "No matching source" : "Add your first original"}
                  </h3>
                  <p>
                    {filter
                      ? "Try another phrase or clear the search."
                      : "There are no acquired originals to analyse. Add a file or a public URL; notes and seed claims are not research results."}
                  </p>
                </div>
              )}
              <div className="result-pagination">
                <button
                  className="button"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - 12))}
                >
                  Previous
                </button>
                <span>
                  {data.total
                    ? `${offset + 1}–${Math.min(offset + 12, data.total)} of ${data.total}`
                    : "0 sources"}
                </span>
                <button
                  className="button"
                  disabled={data.next_offset === null}
                  onClick={() => setOffset(data.next_offset)}
                >
                  Next
                </button>
              </div>
            </section>
            <div className="results-reader">
              {reportError ? (
                <p role="alert" className="result-notice">
                  {reportError}
                </p>
              ) : report ? (
                <Notebook
                  report={report}
                  openEvidence={openEvidence}
                  navigate={navigate}
                  retry={retrySource}
                  reprocess={reprocessSource}
                  busy={!!busy}
                />
              ) : source ? (
                <p role="status">Loading source reading and saved checks…</p>
              ) : (
                <div className="result-empty">
                  <h3>Results appear here automatically</h3>
                  <p>
                    You do not need to select and run each analytical method.
                    Optional specialist controls are available under All tools.
                  </p>
                </div>
              )}
            </div>
          </div>
          <section
            className="results-gaps"
            aria-label="Case gaps and acquisition failures"
          >
            <h3>What is still missing</h3>
            <p>
              {data.summary.notes_without_originals} notes or proposed claims
              have no acquired original. They remain accessible in the case
              threads and evidence library; they are excluded from completed
              source analysis.
            </p>
            {data.acquisition_failures.map((j: any) => (
              <details key={j.id}>
                <summary>
                  {j.objective} · {j.status}
                </summary>
                <p>
                  {j.error || "Acquisition did not produce a usable original"}
                </p>
                <button
                  className="result-link"
                  onClick={() => navigate("queue")}
                >
                  Open acquisition queue
                </button>
              </details>
            ))}
            <p className="result-muted">{data.scope}</p>
          </section>
        </>
      )}
    </div>
  );
}

export function ToolsWorkspace({ navigate }: any) {
  const [historyPage, setHistoryPage] = useState<any>(null),
    [historyOffset, setHistoryOffset] = useState(0);
  const initialRun = useRef(new URLSearchParams(location.search).get("run"));
  const [data, setData] = useState<any>(null),
    [sources, setSources] = useState<any[]>([]);
  const [query, setQuery] = useState(""),
    [family, setFamily] = useState("");
  const [source, setSource] = useState(
    new URLSearchParams(location.search).get("source") || "",
  );
  const [selected, setSelected] = useState<any>(null),
    [values, setValues] = useState<Record<string, string>>({});
  const [run, setRun] = useState<any>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    api(
      `/results/tools${source ? `?evidence_id=${encodeURIComponent(source)}` : ""}`,
    )
      .then((v) => {
        if (active) setData(v);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    api("/results?limit=100")
      .then((v) => {
        if (active) setSources(v.items);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [source]);
  useEffect(() => {
    if (
      !run?.id ||
      ["COMPLETE", "FAILED", "PARTIAL", "CANCELLED"].includes(run.status)
    )
      return;
    let active = true;
    const t = setTimeout(
      () =>
        api(`/results/runs/${encodeURIComponent(run.id)}`)
          .then((v) => {
            if (active) setRun(v);
          })
          .catch((e) => {
            if (active) setError(e.message);
          }),
      2000,
    );
    return () => {
      active = false;
      clearTimeout(t);
    };
  }, [run]);
  function choose(t: any) {
    const url = new URL(location.href);
    url.searchParams.delete("run");
    history.replaceState({}, "", url);
    setSelected(t);
    setRun(null);
    setError("");
    setValues(
      Object.fromEntries(
        Object.entries(t.example || {}).map(([k, v]) => [
          k,
          typeof v === "number" || typeof v === "boolean" ? String(v) : "",
        ]),
      ),
    );
  }
  useEffect(() => {
    let active = true;
    api(`/results/runs?offset=${historyOffset}`)
      .then((v) => {
        if (active) setHistoryPage(v);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [historyOffset, run?.id, run?.status]);
  useEffect(() => {
    if (data && initialRun.current) {
      const id = initialRun.current;
      initialRun.current = null;
      showRun(id).catch((e) => setError(e.message));
    }
  }, [data]);
  function rememberRun(id: string, boundSource: string) {
    const url = new URL(location.href);
    url.searchParams.set("view", "tools");
    url.searchParams.set("run", id);
    if (boundSource) url.searchParams.set("source", boundSource);
    else url.searchParams.delete("source");
    history.replaceState({}, "", url);
  }
  async function showRun(id: string) {
    const saved = await api(`/results/runs/${encodeURIComponent(id)}`);
    const tool = saved.data?.plan?.steps?.[0]?.tool;
    const definition = data?.tools.find((t: any) => t.id === tool);
    if (definition) choose(definition);
    const bound =
      saved.data?.bindings?.evidence_id ||
      saved.receipts?.[0]?.data?.inputs?.evidence_id ||
      saved.data?.plan?.steps?.[0]?.inputs?.evidence_id;
    const boundId = typeof bound === "string" ? bound : "";
    setSource(boundId);
    setRun(saved);
    rememberRun(id, boundId);
  }
  async function execute(e: FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const inputs: any = {};
      for (const [k, example] of Object.entries(selected.example || {})) {
        if (source && ["text", "evidence_id"].includes(k)) continue;
        const v = values[k];
        if (v === "" || v === undefined) continue;
        inputs[k] =
          typeof example === "object" || typeof example === "boolean"
            ? JSON.parse(v)
            : typeof example === "number"
              ? Number(v)
              : v;
      }
      if (source) inputs.evidence_id = source;
      const queued = await post("/automation/run", {
        tool: selected.id,
        inputs,
        authorisation:
          "User-selected registered analysis using the supplied inputs and preserved source",
      });
      setRun(queued);
      rememberRun(queued.id, source);
    } catch (ex: any) {
      setError(ex.message);
    } finally {
      setBusy(false);
    }
  }
  const shown = (data?.tools || []).filter(
    (t: any) =>
      (!family || t.family === family) &&
      `${t.id} ${t.title} ${t.procedure}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <div className="page-scroll results-workspace">
      <div className="results-intro">
        <div>
          <span className="result-eyebrow">
            BACKEND CAPABILITIES, AVAILABLE HERE
          </span>
          <h2>All tools and workspaces</h2>
          <p>
            Compatible checks run automatically. Use this directory to inspect
            every registered tool or supply the extra inputs a specialist method
            requires.
          </p>
        </div>
        <button
          className="button"
          onClick={() => navigate("results", source ? { source } : {})}
        >
          Return to results
        </button>
      </div>
      {error && (
        <p role="alert" className="result-notice">
          {error}
        </p>
      )}
      <details className="saved-run-history">
        <summary>
          Saved execution history · {historyPage?.total ?? "…"} runs
        </summary>
        <p className="result-muted">
          Reopen previous results, including tools run without a source. Reading
          never reruns a tool.
        </p>
        {historyPage?.items.map((r: any) => (
          <button
            key={r.id}
            onClick={() => showRun(r.id).catch((e) => setError(e.message))}
          >
            <span>{r.name || r.id}</span>
            <span>{stateLabel(r.status)}</span>
          </button>
        ))}
        <div className="result-pagination">
          <button
            className="button"
            disabled={!historyOffset}
            onClick={() => setHistoryOffset(Math.max(0, historyOffset - 20))}
          >
            Newer runs
          </button>
          <button
            className="button"
            disabled={
              !historyPage ||
              historyOffset + historyPage.items.length >= historyPage.total
            }
            onClick={() => setHistoryOffset(historyOffset + 20)}
          >
            Older runs
          </button>
        </div>
      </details>
      <section aria-label="Available workspaces">
        <h3>Open a workspace</h3>
        <div className="workspace-directory">
          {data?.workspaces.map((w: any) => (
            <button key={w.id} onClick={() => navigate(w.id)}>
              {w.label}
              <ArrowRight size={12} />
            </button>
          ))}
        </div>
      </section>
      <div className="results-toolbar">
        <input
          aria-label="Search all tools"
          placeholder="Search every registered function…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          aria-label="Tool family"
          value={family}
          onChange={(e) => setFamily(e.target.value)}
        >
          <option value="">All families</option>
          {[
            ...new Set<string>((data?.tools || []).map((t: any) => t.family)),
          ].map((f) => (
            <option key={f}>{f}</option>
          ))}
        </select>
        <select
          aria-label="Source for specialist tools"
          value={source}
          onChange={(e) => {
            setSource(e.target.value);
            setRun(null);
          }}
        >
          <option value="">No source — explicit inputs</option>
          {source &&
            data?.source &&
            !sources.some((r) => r.source.id === source) && (
              <option value={source}>{data.source.title}</option>
            )}
          {sources.map((r) => (
            <option key={r.source.id} value={r.source.id}>
              {r.source.title}
            </option>
          ))}
        </select>
        <span>
          {shown.length} of {data?.tools.length ?? "…"} tools
        </span>
      </div>
      <div className="tool-directory-layout">
        <section className="tool-directory" aria-label="Registered tools">
          {shown.map((t: any) => (
            <button
              key={t.id}
              className={selected?.id === t.id ? "selected" : ""}
              onClick={() => choose(t)}
            >
              <strong>{t.title}</strong>
              <code>{t.id}</code>
              <span>
                {t.saved_status
                  ? label(t.saved_status)
                  : t.automatic?.state === "SCHEDULED"
                    ? "Automatically selected"
                    : "Specialist inputs"}
              </span>
            </button>
          ))}
        </section>
        <section className="tool-runner" aria-label="Tool inputs and output">
          {!selected ? (
            <div className="result-empty">
              <Wrench size={26} />
              <h3>Choose a tool to inspect or run</h3>
              <p>
                Every registered backend adapter is listed. Example source text
                and datasets are never silently substituted for your evidence.
              </p>
            </div>
          ) : (
            <>
              <h3>{selected.title}</h3>
              <p>{selected.procedure}</p>
              <p className="result-caveat">
                {selected.automatic?.reason || selected.requirements}
              </p>
              <form onSubmit={execute}>
                {source && (
                  <p className="result-notice">
                    Text is taken from the selected preserved source and bound
                    to its hashes.
                  </p>
                )}
                {Object.entries(selected.example || {})
                  .filter(
                    ([k]) => !source || !["text", "evidence_id"].includes(k),
                  )
                  .map(([k, v]) => (
                    <label key={k}>
                      {label(k)}
                      {typeof v === "object" ? (
                        <textarea
                          aria-label={label(k)}
                          placeholder="Supply your actual data as JSON"
                          value={values[k] || ""}
                          onChange={(e) =>
                            setValues({ ...values, [k]: e.target.value })
                          }
                        />
                      ) : (
                        <input
                          aria-label={label(k)}
                          type={typeof v === "number" ? "number" : "text"}
                          value={values[k] || ""}
                          onChange={(e) =>
                            setValues({ ...values, [k]: e.target.value })
                          }
                        />
                      )}
                    </label>
                  ))}
                <button
                  className="button primary"
                  disabled={
                    busy ||
                    (!!run &&
                      !["COMPLETE", "PARTIAL", "FAILED", "CANCELLED"].includes(
                        run.status,
                      ))
                  }
                  type="submit"
                >
                  {busy ? "Queuing…" : "Run selected tool"}
                </button>
              </form>
              {run && (
                <div className="tool-live-result" aria-live="polite">
                  <h3>{stateLabel(run.status)}</h3>
                  {run.data?.error && <p role="alert">{run.data.error}</p>}
                  {run.receipts?.map((r: any) => (
                    <CheckResult
                      key={r.id}
                      check={{
                        id: r.id,
                        title:
                          data?.tools.find((t: any) => t.id === r.data.tool)
                            ?.title || r.data.tool,
                        tool: r.data.tool,
                        status: r.status,
                        error: r.data.error,
                        summary: r.data.error || "Saved execution receipt",
                        output: r.data.result?.output,
                        limitations: r.data.result?.limitations,
                        finished: r.data.finished_utc,
                      }}
                    />
                  ))}
                  {source && (
                    <button
                      className="result-link"
                      onClick={() => navigate("results", { source })}
                    >
                      Read this source's updated report
                    </button>
                  )}
                </div>
              )}
              <details>
                <summary>Method limitations</summary>
                <ReadableValue value={selected.limitations} />
              </details>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

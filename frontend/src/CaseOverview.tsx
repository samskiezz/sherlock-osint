import { useEffect, useState } from "react";
import { Activity, ExternalLink, Pause, Play, CheckCheck } from "lucide-react";
import { api } from "./api";
import "./case-overview.css";

const readKey = "looking-glass-briefing-read-v1";
const when = (value: string | null) =>
  value
    ? new Date(value).toLocaleString("en-AU", {
        timeZone: "Australia/Sydney",
        dateStyle: "medium",
        timeStyle: "short",
      }) + " Sydney"
    : "No records yet";
export default function CaseOverview({ notify, selectEvidence }: any) {
  const [brief, setBrief] = useState<any>(null),
    [state, setState] = useState<any>(null);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [read, setRead] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(readKey) || "[]");
    } catch {
      return [];
    }
  });
  const [filter, setFilter] = useState("Results"),
    [browse, setBrowse] = useState(false),
    [page, setPage] = useState(0),
    [media, setMedia] = useState<any>(null);
  useEffect(() => {
    let active = true,
      timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      // Independent requests: the briefing appears before slower operational diagnostics.
      await Promise.allSettled([
        api("/case/briefing")
          .then((x) => {
            if (active) {
              setBrief(x);
              setError("");
            }
          })
          .catch((e) => {
            if (active) setError(e.message);
          }),
        api("/case/overview").then((x) => {
          if (active) setState(x);
        }),
      ]);
      if (active) timer = setTimeout(refresh, 20000);
    }
    refresh();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);
  useEffect(() => {
    if (!browse) return;
    let active = true;
    api(`/media/reports?limit=12&offset=${page * 12}`)
      .then((x) => {
        if (active) setMedia(x);
      })
      .catch((e) => notify(e.message));
    return () => {
      active = false;
    };
  }, [browse, page]);
  async function toggle() {
    setBusy(true);
    try {
      const a = await api("/autopilot");
      await api("/autopilot/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...a.settings, enabled: !a.settings.enabled }),
      });
      setState((s: any) => ({ ...s, enabled: !s.enabled }));
    } catch (e: any) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  const unread = brief?.findings.filter((f: any) => !read.includes(f.id)) || [];
  const visible =
    brief?.findings.filter((f: any) =>
      filter === "Unread"
        ? !read.includes(f.id)
        : filter === "AI proposals"
          ? f.kind === "AI PROPOSAL"
          : f.kind !== "AI PROPOSAL",
    ) || [];
  return (
    <div className="case-overview briefing-home">
      <header className="briefing-heading">
        <div>
          <span className="case-kicker">
            PROJECT LOOKING GLASS · CASE BRIEFING
          </span>
          <h2>What the evidence tells us</h2>
          <p>
            Conclusions, unresolved questions and newly collected sources in one
            place.
          </p>
        </div>
        <span className="briefing-live">
          <Activity size={14} />
          {state
            ? state.enabled
              ? "Analysis running"
              : "Analysis paused"
            : "Checking service"}
        </span>
      </header>
      {error && (
        <p role="alert" className="briefing-error">
          Briefing could not refresh: {error}.{" "}
          {brief
            ? "Showing the last loaded results."
            : "Retrying automatically."}
        </p>
      )}
      {!brief ? (
        <p role="status">Reading saved investigation results…</p>
      ) : (
        <>
          <div className="briefing-scoreboard">
            <div>
              <strong>{brief.documented_count}</strong>
              <span>documented statements</span>
            </div>
            <div>
              <strong>{brief.measured_count}</strong>
              <span>measured results</span>
            </div>
            <div>
              <strong>{brief.open_questions.length}</strong>
              <span>unresolved claims</span>
            </div>
            <div>
              <strong>{unread.length}</strong>
              <span>unread results</span>
            </div>
          </div>
          <div className="briefing-layout">
            <section
              className="briefing-results"
              aria-label="Investigation results"
            >
              <div className="briefing-section-head">
                <h3>What we know</h3>
                <button
                  onClick={() => {
                    const ids = brief.findings.map((f: any) => f.id);
                    localStorage.setItem(readKey, JSON.stringify(ids));
                    setRead(ids);
                  }}
                >
                  <CheckCheck size={14} /> Mark results read
                </button>
              </div>
              <div className="briefing-filters" aria-label="Result filters">
                {["Results", "Unread", "AI proposals"].map((f) => (
                  <button
                    className={filter === f ? "selected" : ""}
                    key={f}
                    onClick={() => setFilter(f)}
                  >
                    {f}
                    {f === "Unread"
                      ? ` (${unread.length})`
                      : f === "AI proposals"
                        ? ` (${brief.proposal_count})`
                        : ""}
                  </button>
                ))}
              </div>
              {!visible.length && (
                <div className="briefing-empty">
                  {filter === "Unread"
                    ? "You’ve read all saved results. New source-backed results will appear here automatically."
                    : filter === "AI proposals"
                      ? "No source-checked AI proposals saved."
                      : "No source-checked conclusions are established yet. Collection activity is shown separately below."}
                </div>
              )}
              {visible.map((f: any) => (
                <article
                  className="briefing-result"
                  key={f.id}
                  data-result-kind={f.kind}
                >
                  <div className="briefing-result-meta">
                    <span
                      className={
                        f.kind === "DOCUMENTED" ? "documented" : "provisional"
                      }
                    >
                      {f.kind === "DOCUMENTED"
                        ? "Documented statement"
                        : f.kind === "AI PROPOSAL"
                          ? "AI proposal · unreviewed"
                          : "Measured result · provisional"}
                    </span>
                    {!read.includes(f.id) && (
                      <span className="unread-dot">Unread</span>
                    )}
                  </div>
                  <h4>{f.statement}</h4>
                  <p className="briefing-result-context">{f.topic}</p>
                  {f.sources.slice(0, 2).map((s: any) => (
                    <div
                      className="briefing-citation"
                      key={s.evidence_id + s.quote}
                    >
                      <blockquote>
                        {s.quote.length > 260
                          ? s.quote.slice(0, 260) + "…"
                          : s.quote}
                      </blockquote>
                      <button
                        onClick={() => selectEvidence(s.evidence_id, s.quote)}
                      >
                        <ExternalLink size={13} />
                        {s.title}
                        <span>{s.location}</span>
                      </button>
                    </div>
                  ))}
                  <p className="briefing-limit">{f.limits}</p>
                  <details>
                    <summary>Method and provenance</summary>
                    <p>{f.method}</p>
                    <p>
                      Saved {when(f.recorded_at)}. This is a saved result date,
                      not a prediction or source publication date.
                    </p>
                    {f.sources.map((s: any) => (
                      <p key={s.evidence_id}>
                        {s.domain} · Retrieved {when(s.retrieved_at)} ·{" "}
                        {s.publication_date
                          ? `Publication: ${s.publication_date}`
                          : "Publication date not established"}
                      </p>
                    ))}
                  </details>
                </article>
              ))}
            </section>
            <aside className="briefing-sidebar">
              <section>
                <span className="case-kicker">STILL UNRESOLVED</span>
                <h3>What we don’t know</h3>
                <p>These claims have not become established facts.</p>
                {brief.open_questions.slice(0, 5).map((q: any, i: number) => (
                  <article key={i}>
                    <h4>{q.statement}</h4>
                    <p>{q.reason}</p>
                    {q.sources.slice(0, 1).map((s: any) => (
                      <button
                        key={s.evidence_id}
                        onClick={() => selectEvidence(s.evidence_id, s.quote)}
                      >
                        Inspect cited source <ExternalLink size={12} />
                      </button>
                    ))}
                    {q.counterevidence.length > 0 && (
                      <p className="briefing-counter">
                        Counterevidence: {q.counterevidence.join("; ")}
                      </p>
                    )}
                  </article>
                ))}
                {brief.open_questions.length > 5 && (
                  <details>
                    <summary>
                      {brief.open_questions.length - 5} more unresolved claims
                    </summary>
                    {brief.open_questions.slice(5).map((q: any, i: number) => (
                      <article key={i}>
                        <h4>{q.statement}</h4>
                        <p>{q.reason}</p>
                      </article>
                    ))}
                  </details>
                )}
              </section>
              <section className="briefing-recent">
                <span className="case-kicker">LATEST COLLECTION</span>
                <h3>Newly added evidence</h3>
                <p>
                  Collected recently; its content may be older. Acquisition
                  alone is not a finding.
                </p>
                {brief.recent_evidence.map((e: any) => (
                  <button
                    key={e.evidence_id}
                    onClick={() => selectEvidence(e.evidence_id)}
                  >
                    <strong>{e.title}</strong>
                    <span>
                      {e.domain} · {when(e.retrieved_at)}
                    </span>
                  </button>
                ))}
              </section>
            </aside>
          </div>
          {brief.withheld.length > 0 && (
            <p className="briefing-error">
              {brief.withheld.length} saved statements withheld because their
              supporting file or passage could not be verified.
            </p>
          )}
          <details className="case-audit">
            <summary>How this briefing is assembled</summary>
            <p>{brief.scope}</p>
            <p>
              Unread is remembered in this browser after you mark results read.
              It does not mean a newly discovered historical fact. Repeated
              processing does not create a new result.
            </p>
          </details>
        </>
      )}
      {state && (
        <details className="case-audit">
          <summary>
            Automatic collection and processing · {state.watches} scheduled
            watches · {state.attention.length} issues
          </summary>
          <div className="case-running">
            <div>
              <h3>
                {state.enabled
                  ? "Investigation running"
                  : "Automatic dispatch paused"}
              </h3>
              <p>
                {state.originals} preserved originals ·{" "}
                {state.acquisitions_in_progress} acquisitions in progress
              </p>
              <p>{state.service_scope}</p>
            </div>
            <button className="case-pause" disabled={busy} onClick={toggle}>
              {state.enabled ? <Pause size={14} /> : <Play size={14} />}{" "}
              {state.enabled ? "Pause new analysis" : "Resume analysis"}
            </button>
          </div>
          {state.active.map((r: any) => (
            <p key={r.id}>
              {r.title} · {r.completed_steps}/{r.total_steps} checks
            </p>
          ))}
          {state.attention.map((b: any) => (
            <p key={b.title}>
              <strong>{b.title}</strong>: {b.reason}
            </p>
          ))}
        </details>
      )}
      <details
        className="case-audit"
        onToggle={(e) => setBrowse(e.currentTarget.open)}
      >
        <summary>Browse acquired images and saved diagnostics</summary>
        {media && (
          <>
            <div className="media-review-grid">
              {media.items.map((item: any) => (
                <article className="media-review-card" key={item.evidence_id}>
                  <button
                    className="media-image"
                    onClick={() => selectEvidence(item.evidence_id)}
                  >
                    <img
                      src={item.preview_url}
                      alt={item.title}
                      loading="lazy"
                    />
                  </button>
                  <div className="media-review-body">
                    <small>
                      {item.source_domain} · {item.status}
                    </small>
                    <h3>{item.title}</h3>
                    {item.origins?.some(
                      (o: any) => o.collection_role === "REFERENCE_MATERIAL",
                    ) && (
                      <p className="media-reference-label">
                        Reference material · off-topic search result
                      </p>
                    )}
                    <p>
                      {item.report?.summary ||
                        item.error ||
                        "Awaiting automatic review."}
                    </p>
                    <button onClick={() => selectEvidence(item.evidence_id)}>
                      Inspect original and diagnostics{" "}
                      <ExternalLink size={12} />
                    </button>
                  </div>
                </article>
              ))}
            </div>
            <div className="media-pagination">
              <button disabled={!page} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <span>Page {page + 1}</span>
              <button
                disabled={!media.has_more}
                onClick={() => setPage(page + 1)}
              >
                Next
              </button>
            </div>
          </>
        )}
        {!media && <p>Loading saved image results…</p>}
      </details>
    </div>
  );
}

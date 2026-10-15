import { useEffect, useState, type ReactNode } from "react";
import { Activity, ExternalLink } from "lucide-react";
import { api } from "./api";
import "./case-overview.css";

const automaticTabs = new Set([
  "lab",
  "automation",
  "knowledge",
  "patents",
  "photos",
  "tradecraft",
  "research",
  "onion",
  "watch",
  "cipher",
  "archives",
  "agents",
]);
export const isAutomaticView = (view: string) => automaticTabs.has(view);

export default function AutomaticWorkspace({
  view,
  selectEvidence,
  children,
}: {
  view: string;
  selectEvidence: (id: string, quote?: string) => void;
  children: ReactNode;
}) {
  if (!automaticTabs.has(view)) return <>{children}</>;
  return (
    <AutomaticResults key={view} view={view} selectEvidence={selectEvidence}>
      {children}
    </AutomaticResults>
  );
}
function AutomaticResults({
  view,
  selectEvidence,
  children,
}: {
  view: string;
  selectEvidence: (id: string, quote?: string) => void;
  children: ReactNode;
}) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState("");
  const [advanced, setAdvanced] = useState(false),
    [photos, setPhotos] = useState<any>(null),
    [brief, setBrief] = useState<any>(null);
  useEffect(() => {
    let active = true,
      timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      const requests = [
        api(`/case/workspaces/${view}`)
          .then((x) => {
            if (active) {
              setData(x);
              setError("");
            }
          })
          .catch((e) => {
            if (active) setError(e.message);
          }),
      ];
      if (view === "photos" || view === "lab")
        requests.push(
          api("/media/reports?limit=12").then((x) => {
            if (active) setPhotos(x);
          }),
        );
      if (view === "agents" || view === "tradecraft")
        requests.push(
          api("/case/briefing").then((x) => {
            if (active) setBrief(x);
          }),
        );
      await Promise.allSettled(requests);
      if (active) timer = setTimeout(refresh, 20000);
    }
    refresh();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [view]);
  return (
    <div className="case-overview automatic-results">
      <header className="briefing-heading">
        <div>
          <span className="case-kicker">
            PROJECT LOOKING GLASS · AUTOMATIC WORKSPACE
          </span>
          <h2>{data?.title || "Reading automatic results…"}</h2>
          <p>
            Saved outputs appear here as background workers process acquired
            evidence.
          </p>
        </div>
        <span className="briefing-live">
          <Activity size={14} />
          {data
            ? data.enabled
              ? "Analysis enabled"
              : "Analysis paused"
            : "Connecting"}
        </span>
      </header>
      {error && (
        <p className="briefing-error" role="alert">
          Unable to refresh this workspace: {error}. Retrying automatically.
        </p>
      )}
      {data && (
        <>
          <div className="automatic-status">
            <span>
              {data.pending.length} source profiles queued / running · latest
              100
            </span>
            <span>
              {data.watches.filter((w: any) => w.enabled).length} relevant
              scheduled watches
            </span>
          </div>
          {data.blockers.map((b: string) => (
            <p key={b} className="briefing-error">
              {b}
            </p>
          ))}
          {data.watches.length > 0 && (
            <section
              className="automatic-watches"
              aria-label="Automatic collection"
            >
              <h3>Collecting without manual searches</h3>
              {data.watches.map((w: any) => (
                <div key={w.id}>
                  <strong>{w.name}</strong>
                  <span>
                    {w.enabled ? "Scheduled" : "Paused"}
                    {w.enabled && w.next_due
                      ? ` · Next due ${new Date(w.next_due * 1000).toLocaleString("en-AU", { timeZone: "Australia/Sydney", dateStyle: "medium", timeStyle: "short" })} Sydney`
                      : ""}
                  </span>
                </div>
              ))}
            </section>
          )}
          {brief && (
            <section aria-label="Saved conclusions">
              <h3>
                {view === "agents"
                  ? "Source-backed statements and analyst proposals"
                  : "Documented statements and open hypotheses"}
              </h3>
              {brief.findings
                .filter(
                  (f: any) => view !== "agents" || f.kind === "AI PROPOSAL",
                )
                .map((f: any) => (
                  <article className="briefing-result" key={f.id}>
                    <small>{f.kind}</small>
                    <h4>{f.statement}</h4>
                    <p className="briefing-limit">{f.limits}</p>
                    {f.sources.map((s: any) => (
                      <button
                        className="automatic-source"
                        key={s.evidence_id}
                        onClick={() => selectEvidence(s.evidence_id, s.quote)}
                      >
                        <ExternalLink size={13} />
                        {s.title} · {s.location}
                      </button>
                    ))}
                  </article>
                ))}
              {view === "tradecraft" &&
                brief.open_questions.map((q: any, i: number) => (
                  <article className="briefing-result" key={i}>
                    <small>UNRESOLVED · {q.state}</small>
                    <h4>{q.statement}</h4>
                    <p className="briefing-limit">{q.reason}</p>
                  </article>
                ))}
            </section>
          )}
          {photos && (
            <section aria-label="Automatic image review">
              <h3>Images already reviewed</h3>
              <div className="media-review-grid">
                {photos.items.map((item: any) => (
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
                        Open original and saved diagnostics
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          )}
          <section
            className="automatic-output"
            aria-label="Completed automatic results"
          >
            <h3>Saved results</h3>
            {!data.results.length && (
              <p className="briefing-empty">
                No completed source-bound results are available in this
                workspace yet. Eligible collected originals are handled by the
                background workers. Missing inputs and transport failures remain
                visible below.
              </p>
            )}
            {data.results.map((r: any) => (
              <article className="briefing-result" key={r.id}>
                <div className="briefing-result-meta">
                  <span>
                    {r.status === "COMPLETE"
                      ? "Completed check · interpretation provisional"
                      : r.status}
                  </span>
                  <span>{r.method}</span>
                </div>
                <h4>{r.title}</h4>
                {r.source_scope && (
                  <p className="briefing-result-context">{r.source_scope}</p>
                )}
                <p className="automatic-summary">{r.summary}</p>
                {r.method && <SavedOutput receiptId={r.id} />}
                <button
                  className="automatic-source"
                  onClick={() => selectEvidence(r.evidence_id)}
                >
                  <ExternalLink size={13} /> Open source and full saved analysis
                </button>
                {r.limitations && (
                  <p className="briefing-limit">{r.limitations}</p>
                )}
              </article>
            ))}
          </section>
          <details className="case-audit">
            <summary>
              Processing coverage and methods awaiting inputs ·{" "}
              {data.unavailable.length}
            </summary>
            <p>{data.scope}</p>
            {data.unavailable.map((u: any) => (
              <p key={u.method}>
                <strong>{u.method}</strong>: {u.reason}
              </p>
            ))}
          </details>
        </>
      )}
      <details
        className="case-audit automatic-advanced"
        onToggle={(e) => setAdvanced(e.currentTarget.open)}
      >
        <summary>
          Advanced configuration and optional specialist controls
        </summary>
        <p>
          Routine compatible analysis runs without these controls. Changes to
          sources, credentials, comparison designs or human assessments are
          optional here.
        </p>
        {advanced && children}
      </details>
    </div>
  );
}

function SavedOutput({ receiptId }: { receiptId: string }) {
  const [result, setResult] = useState<any>(null),
    [error, setError] = useState("");
  return (
    <details
      className="saved-automatic-output"
      onToggle={async (e) => {
        if (!e.currentTarget.open || result) return;
        try {
          setResult(
            await api("/case/receipts/" + encodeURIComponent(receiptId)),
          );
        } catch (e: any) {
          setError(e.message);
        }
      }}
    >
      <summary>View saved output and reproducible parameters</summary>
      {error && <p role="alert">{error}</p>}
      {result ? (
        <>
          {result.tool === "decoder.auto" && (
            <>
              <p>
                Engine: {result.output.engine} ·{" "}
                {result.output.returned_candidates} candidate(s)
              </p>
              {result.output.candidates?.map((c: any, i: number) => (
                <div key={i}>
                  <strong>
                    {c.useful
                      ? "Candidate transformation · unvalidated"
                      : "No useful transformation"}
                  </strong>
                  <pre>{c.data}</pre>
                  <p>Recipe: {JSON.stringify(c.recipe)}</p>
                </div>
              ))}
              <p>{result.output.validation}</p>
            </>
          )}
          {result.tool === "gematria.all" && (
            <>
              <p>Input: {result.output.input}</p>
              <table>
                <thead>
                  <tr>
                    <th>Mapping</th>
                    <th>Total</th>
                    <th>Digital root</th>
                  </tr>
                </thead>
                <tbody>
                  {result.output.results?.map((r: any) => (
                    <tr key={r.table}>
                      <td>{r.table}</td>
                      <td>{r.sum}</td>
                      <td>{r.digital_root}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p>{result.output.normalisation}</p>
              <p>
                These scores do not authenticate hidden messages, identity or
                predictions.
              </p>
            </>
          )}
          <details>
            <summary>Complete execution receipt</summary>
            <pre>{JSON.stringify(result, null, 2)}</pre>
          </details>
        </>
      ) : (
        !error && <p>Loading saved receipt…</p>
      )}
    </details>
  );
}

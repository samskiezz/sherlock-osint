import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  ExternalLink,
  FileText,
  Network,
  ScanEye,
} from "lucide-react";
import { api } from "./api";
import "./case-breakdown.css";
const stamp = (v: string) =>
  v
    ? new Date(v).toLocaleDateString("en-AU", {
        timeZone: "Australia/Sydney",
        dateStyle: "medium",
      })
    : "Not established";
const currentTopic = () => {
  try {
    return decodeURIComponent(location.hash.match(/^#case\/(.*)$/)?.[1] || "");
  } catch {
    return "";
  }
};
export default function CaseBreakdown({ selectEvidence, onBoard }: any) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState("");
  const [selected, setSelected] = useState(currentTopic),
    [tab, setTab] = useState("Connections"),
    [report, setReport] = useState<any>(null);
  useEffect(() => {
    let active = true,
      timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const d = await api("/case/breakdown");
        if (active) {
          setData(d);
          setError("");
        }
      } catch (e: any) {
        if (active) setError(e.message);
      }
      if (active) timer = setTimeout(refresh, 30000);
    }
    refresh();
    const hash = () => {
      setSelected(currentTopic());
      setReport(null);
    };
    window.addEventListener("hashchange", hash);
    return () => {
      active = false;
      clearTimeout(timer);
      window.removeEventListener("hashchange", hash);
    };
  }, []);
  function open(id: string, section = "Connections") {
    setSelected(id);
    setTab(section);
    setReport(null);
    history.replaceState(
      null,
      "",
      id
        ? `#case/${encodeURIComponent(id)}`
        : location.pathname + location.search,
    );
    const reportElement = document.querySelector(".case-breakdown");
    const boardScroller = reportElement?.closest(".board-and-breakdown");
    if (boardScroller && reportElement)
      boardScroller.scrollTo({
        top:
          (reportElement as HTMLElement).offsetTop -
          (boardScroller as HTMLElement).offsetTop -
          50,
      });
    else reportElement?.scrollTo({ top: 0 });
  }
  const topic = data?.topics.find((t: any) => t.id === selected);
  return (
    <div className="case-breakdown">
      <header className="breakdown-heading">
        <div>
          <span className="case-kicker">PROJECT LOOKING GLASS</span>
          <h2>{topic ? topic.title : "The case, broken down"}</h2>
          <p>
            {topic
              ? topic.question
              : "Pick a thread. See the connections, read the proof, and open the analysis behind each claim."}
          </p>
        </div>
        {topic && (
          <button className="breakdown-back" onClick={() => open("")}>
            <ArrowLeft size={15} /> All case threads
          </button>
        )}
      </header>
      {error && (
        <p className="briefing-error" role="alert">
          Couldn’t refresh the case: {error}. Retrying automatically.
        </p>
      )}
      {!data && <p>Loading saved case connections and source records…</p>}
      {data && !topic && (
        <>
          <div className="case-thread-grid">
            {data.topics.map((t: any, i: number) => (
              <article className="case-thread" key={t.id}>
                <div className="case-thread-top">
                  <span>{String(i + 1).padStart(2, "0")}</span>
                  <small
                    className={
                      t.status === "DOCUMENTED CONNECTIONS"
                        ? "supported"
                        : "unresolved"
                    }
                  >
                    {t.status === "DOCUMENTED CONNECTIONS"
                      ? "Source-backed connections"
                      : t.status === "PROVISIONAL ANALYSIS"
                        ? "Measured · still provisional"
                        : "Unresolved"}
                  </small>
                </div>
                <button
                  className="case-thread-title"
                  onClick={() => open(t.id)}
                >
                  <h3>{t.title}</h3>
                  <ArrowRight size={18} />
                </button>
                <p>{t.takeaway}</p>
                <div className="case-thread-actions">
                  <button onClick={() => open(t.id, "Connections")}>
                    <Network size={14} /> Connections{" "}
                    <b>{t.connections.length}</b>
                  </button>
                  <button onClick={() => open(t.id, "Proof")}>
                    <FileText size={14} /> Proof <b>{t.documents.length}</b>
                  </button>
                  <button onClick={() => open(t.id, "Analysis")}>
                    <ScanEye size={14} /> Analysis <b>{t.analyses.length}</b>
                  </button>
                </div>
              </article>
            ))}
          </div>
          <p className="case-routing-note">
            The sections include documented records and disputed claims. “Proof”
            opens the records; it does not mean every allegation is proven.
            Sections update from saved work automatically.
          </p>
        </>
      )}
      {topic && (
        <>
          <div className="thread-bottom-line">
            <span
              className={
                topic.supported_connections ? "supported" : "unresolved"
              }
            >
              {topic.status.replaceAll("_", " ")}
            </span>
            <strong>{topic.takeaway}</strong>
          </div>
          <nav className="case-report-tabs" aria-label="Case report sections">
            {["Connections", "Proof", "Analysis"].map((label) => (
              <button
                className={tab === label ? "selected" : ""}
                key={label}
                onClick={() => {
                  setTab(label);
                  setReport(null);
                }}
              >
                {label}
                <b>
                  {label === "Connections"
                    ? topic.connections.length
                    : label === "Proof"
                      ? topic.documents.length
                      : topic.analyses.length}
                </b>
              </button>
            ))}
          </nav>
          {tab === "Connections" && (
            <section
              className="case-connections"
              aria-label="Connections in this thread"
            >
              {!topic.connections.length && (
                <div className="case-gap">
                  <h3>No sourced connection is established here yet.</h3>
                  <p>
                    This thread has {topic.documents.length} collected records
                    and {topic.analyses.length} saved analyses. Those are
                    available under Proof and Analysis; their existence alone
                    does not establish the proposed relationship.
                  </p>
                  <button onClick={() => setTab("Analysis")}>
                    Read available analysis <ArrowRight size={14} />
                  </button>
                </div>
              )}
              {topic.connections.map((c: any) => (
                <article key={c.id} className="case-connection">
                  <div className="connection-route">
                    <span>{c.from}</span>
                    <ArrowRight size={17} />
                    <span>{c.to}</span>
                  </div>
                  <small
                    className={c.source_checked ? "supported" : "unresolved"}
                  >
                    {c.source_checked ? "Source passage checked" : c.state}
                  </small>
                  <h3>{c.claim}</h3>
                  <div className="connection-explanation">
                    <strong>Why this connection exists</strong>
                    <p>{c.analysis}</p>
                  </div>
                  <div className="connection-proof">
                    <strong>Proof behind this claim</strong>
                    {c.proof.length ? (
                      c.proof.map((p: any) => (
                        <blockquote key={p.evidence_id + p.quote}>
                          <p>{p.quote}</p>
                          <button
                            onClick={() =>
                              selectEvidence(p.evidence_id, p.quote)
                            }
                          >
                            <ExternalLink size={13} />
                            {p.title} · {p.location}
                          </button>
                        </blockquote>
                      ))
                    ) : (
                      <p className="unresolved">
                        No acquired supporting passage is attached. This is a
                        lead, not an established connection.
                      </p>
                    )}
                  </div>
                  {c.limits && (
                    <p className="briefing-limit">Limit: {c.limits}</p>
                  )}
                  {c.counterevidence.length > 0 && (
                    <div className="connection-counter">
                      <strong>Counterevidence / unresolved problems</strong>
                      {c.counterevidence.map((v: string, i: number) => (
                        <p key={i}>{v}</p>
                      ))}
                    </div>
                  )}
                  <div className="connection-actions">
                    <button
                      onClick={() => {
                        setTab("Analysis");
                        setReport(null);
                      }}
                    >
                      Read this thread’s saved analysis <ScanEye size={14} />
                    </button>
                    {onBoard && (
                      <button onClick={() => onBoard(c.board_id)}>
                        View on evidence board <Network size={14} />
                      </button>
                    )}
                  </div>
                </article>
              ))}
              <div className="case-gap">
                <h3>What remains unproven</h3>
                <p>{topic.assessment.not_established}</p>
                {topic.notes.length > 0 && (
                  <>
                    <p>Imported notes are investigative leads:</p>
                    {topic.notes.map((n: any) => (
                      <button
                        className="case-note"
                        key={n.id}
                        onClick={() => selectEvidence(n.id)}
                      >
                        {n.title}
                        <small>{n.status} · open note</small>
                        {n.summary && (
                          <span className="case-note-summary">{n.summary}</span>
                        )}
                      </button>
                    ))}
                  </>
                )}
              </div>
            </section>
          )}
          {tab === "Proof" && (
            <section aria-label="Proof and original records">
              <p className="case-section-intro">
                Originals and archived records associated with this thread. A
                document supports a specific claim only where a cited passage
                establishes it.
              </p>
              {!topic.documents.length && (
                <div className="case-gap">
                  <h3>
                    No original supporting files have been acquired for this
                    thread.
                  </h3>
                  <p>
                    Imported dossier statements remain unverified leads. No
                    source has been substituted with an AI-written description.
                  </p>
                </div>
              )}
              {topic.documents.map((d: any) => (
                <article className="case-document" key={d.id}>
                  <FileText size={21} />
                  <div>
                    <small>
                      {d.cited_in_connection
                        ? "Cited in a source-checked connection"
                        : "Collected research material · interpretation requires review"}
                    </small>
                    <h3>{d.title}</h3>
                    <p>
                      {d.domain} · {d.mime} · {d.status}
                    </p>
                    <p>
                      Publication: {stamp(d.publication_date)} · Retrieved:{" "}
                      {stamp(d.retrieved_at)}
                      {d.archive_capture_date
                        ? ` · Archive capture: ${stamp(d.archive_capture_date)}`
                        : ""}
                    </p>
                    <details>
                      <summary>Preserved file identity</summary>
                      <code>SHA-256 {d.sha256}</code>
                    </details>
                  </div>
                  <button onClick={() => selectEvidence(d.id)}>
                    Open original <ExternalLink size={14} />
                  </button>
                </article>
              ))}
              {topic.discovery_records?.length > 0 && (
                <details className="case-routing-note">
                  <summary>
                    {topic.discovery_records.length} discovery and catalogue
                    responses
                  </summary>
                  <p>
                    These preserve how sources were found. They are excluded
                    from the proof-file count.
                  </p>
                  {topic.discovery_records.map((d: any) => (
                    <p key={d.id}>
                      <button onClick={() => selectEvidence(d.id)}>
                        {d.title} <ExternalLink size={12} />
                      </button>
                    </p>
                  ))}
                </details>
              )}
            </section>
          )}
          {tab === "Analysis" && (
            <section aria-label="Saved case analysis">
              {report ? (
                <AnalysisReader
                  key={report.id}
                  record={report}
                  selectEvidence={selectEvidence}
                  onClose={() => setReport(null)}
                />
              ) : (
                <>
                  <p className="case-section-intro">
                    Read the actual saved test or review: what was examined, the
                    result, supporting passages and limitations. Repeated runs
                    are grouped; an AI proposal remains provisional.
                  </p>
                  {!topic.analyses.length && (
                    <div className="case-gap">
                      <h3>
                        No source-bound analysis report has been saved for this
                        thread.
                      </h3>
                      <p>
                        There is no completed conclusion to show. The available
                        claims and missing proof are listed under Connections.
                      </p>
                    </div>
                  )}
                  {topic.analyses.map((a: any) => (
                    <article className="case-analysis-card" key={a.id}>
                      <small>{a.state}</small>
                      <h3>{a.title}</h3>
                      <p>{a.summary}</p>
                      <button onClick={() => setReport(a)}>
                        Read full analysis <ArrowRight size={15} />
                      </button>
                    </article>
                  ))}
                </>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
function AnalysisReader({ record, selectEvidence, onClose }: any) {
  const [saved, setSaved] = useState<any>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api(record.href)
      .then((x) => {
        if (active) setSaved(x);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [record.href]);
  const d = saved?.data || saved?.output;
  return (
    <article className="case-analysis-reader">
      <button className="breakdown-back" onClick={onClose}>
        <ArrowLeft size={14} /> All analyses in this thread
      </button>
      <small>{record.state}</small>
      <h3>{record.title}</h3>
      {error && (
        <p className="briefing-error" role="alert">
          The saved report could not be opened: {error}
        </p>
      )}
      {!saved && !error && <p>Checking sources and loading saved analysis…</p>}
      {saved && (
        <>
          <section>
            <h4>Result</h4>
            <p>{d?.summary || record.summary}</p>
            {d?.findings?.map((f: any, i: number) => (
              <blockquote key={i}>
                <strong>Proposed finding · review required</strong>
                <p>{f.claim}</p>
                <p>{f.quote}</p>
                <button onClick={() => selectEvidence(f.evidence_id, f.quote)}>
                  Inspect cited passage <ExternalLink size={13} />
                </button>
              </blockquote>
            ))}
          </section>
          {d?.steps && (
            <section>
              <h4>How the analysis reached this result</h4>
              {d.steps.map((s: any, i: number) => (
                <div key={i} className="analysis-step">
                  <span>{i + 1}</span>
                  <div>
                    <strong>{s.title}</strong>
                    <p>{s.detail}</p>
                  </div>
                </div>
              ))}
            </section>
          )}
          {d?.sequence && (
            <div className="case-image-sequence">
              {d.sequence.map((s: any) => (
                <figure key={s.panel}>
                  <img
                    src={s.image_url}
                    alt={`Measured panel ${s.panel + 1}`}
                  />
                  <figcaption>
                    {Math.round(s.artwork_weight * 100)}% reference · RGB error{" "}
                    {(s.rmse * 255).toFixed(1)}/255
                  </figcaption>
                </figure>
              ))}
            </div>
          )}
          {d?.photo_reference && (
            <section>
              <h4>Matched publisher photograph</h4>
              <p>{d.photo_reference.caption}</p>
              <p>
                {d.photo_reference.geometry?.ransac_inliers} geometric inliers.
                The attribution comes from the publisher caption.
              </p>
              <button
                onClick={() => selectEvidence(d.photo_reference.evidence_id)}
              >
                Open the acquired photograph <ExternalLink size={13} />
              </button>
            </section>
          )}
          {d?.candidates && (
            <section>
              <h4>Candidate transformations</h4>
              {d.candidates.map((c: any, i: number) => (
                <div key={i}>
                  <strong>
                    {c.useful
                      ? "Candidate · not authenticated"
                      : "No useful candidate"}
                  </strong>
                  <pre>{c.data}</pre>
                  <p>Recipe: {JSON.stringify(c.recipe)}</p>
                </div>
              ))}
              <p>{d.validation}</p>
            </section>
          )}
          {saved.tool === "gematria.all" && (
            <section>
              <h4>Gematria results</h4>
              <p>Input: {d.input}</p>
              <table>
                <thead>
                  <tr>
                    <th>Mapping</th>
                    <th>Total</th>
                    <th>Digital root</th>
                  </tr>
                </thead>
                <tbody>
                  {d.results?.map((r: any) => (
                    <tr key={r.table}>
                      <td>{r.table}</td>
                      <td>{r.sum}</td>
                      <td>{r.digital_root}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p>{d.normalisation}</p>
              <p>
                Numerical coincidences do not authenticate messages or
                predictions.
              </p>
            </section>
          )}
          {d?.sources?.length > 0 && (
            <section>
              <h4>Sources actually examined</h4>
              {d.sources.map((s: any, i: number) => (
                <blockquote key={i}>
                  <p>{s.quote}</p>
                  <button
                    onClick={() =>
                      selectEvidence(s.evidence_id || s.id, s.quote)
                    }
                  >
                    {s.title || s.evidence_id || s.id} ·{" "}
                    {s.location || "Exact source passage"}{" "}
                    <ExternalLink size={13} />
                  </button>
                </blockquote>
              ))}
            </section>
          )}
          {d?.relationships?.length > 0 && (
            <section>
              <h4>Relationships reviewed</h4>
              {d.relationships.map((r: any, i: number) => (
                <div key={i}>
                  <p>{r.claim}</p>
                  <small>
                    {r.state} ·{" "}
                    {r.citation_valid
                      ? "Citation matched"
                      : "Citation not verified"}
                  </small>
                </div>
              ))}
            </section>
          )}
          {d?.chronology?.length > 0 && (
            <section>
              <h4>Chronology audit</h4>
              {d.chronology.map((r: any, i: number) => (
                <div key={i}>
                  <strong>{r.title}</strong>
                  <p>
                    Publication: {stamp(r.publication_date)} · Archive:{" "}
                    {stamp(r.archive_capture_date)} · Retrieval:{" "}
                    {stamp(r.retrieved_utc)}
                  </p>
                </div>
              ))}
            </section>
          )}
          <section className="case-gap">
            <h4>Limits and counterevidence</h4>
            <p>
              {d?.limits ||
                d?.limitations ||
                saved.limitations ||
                "This saved computation does not independently establish intent, identity, causality or a prediction."}
            </p>
            {d?.rejected_findings?.length > 0 && (
              <p>
                {d.rejected_findings.length} proposed findings were rejected by
                the citation auditor.
              </p>
            )}
          </section>
          <details>
            <summary>Complete stored record and reproducibility data</summary>
            <pre>{JSON.stringify(saved, null, 2)}</pre>
          </details>
        </>
      )}
    </article>
  );
}

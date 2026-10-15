import { useEffect, useState } from "react";
import { api, post } from "./api";
import {
  Database,
  Download,
  FileText,
  Play,
  ShieldCheck,
  Image as ImageIcon,
} from "lucide-react";
import "./collection.css";
const bytes = (n: number) => `${(n / 1024 / 1024).toFixed(2)} MB`;

export function VaultWorkspace({ selectEvidence, notify }: any) {
  const [data, setData] = useState<any>(null),
    [query, setQuery] = useState(""),
    [foundation, setFoundation] = useState<any>(null);
  useEffect(() => {
    const refresh = () =>
      api("/vault")
        .then(setData)
        .catch((e) => notify(e.message));
    const refreshFoundation = () =>
      api("/v1/system")
        .then(setFoundation)
        .catch(() => {});
    refresh();
    refreshFoundation();
    const t = setInterval(() => {
      refresh();
      refreshFoundation();
    }, 5000);
    return () => clearInterval(t);
  }, []);
  if (!data)
    return <div className="page-scroll">Reading persistent vault…</div>;
  return (
    <div className="page-scroll collection-workspace">
      <div className="section-title">
        <h2>Growing evidence database</h2>
        <span className="status green">PERSISTENT · LOCAL FILES</span>
      </div>
      {foundation && (
        <div className="collection-paths">
          <h3>PostgreSQL foundation · growing metadata database</h3>
          <p>
            {foundation.metadata_records} evidence records ·{" "}
            {foundation.entity_records} source-specific entities ·{" "}
            {foundation.case_records} cases · {foundation.collection_jobs}{" "}
            durable collection jobs
          </p>
          <p>
            Synchronises with the original vault every{" "}
            {foundation.metadata_sync_seconds} seconds.{" "}
            {foundation.original_storage}.
          </p>
        </div>
      )}
      <div className="collection-metrics">
        <article>
          <Database />
          <h3>{data.original_files}</h3>
          <p>Physical original files · {bytes(data.original_bytes)}</p>
        </article>
        <article>
          <FileText />
          <h3>{bytes(data.derivative_bytes)}</h3>
          <p>Separate forensic derivatives</p>
        </article>
        <article>
          <ShieldCheck />
          <h3>{bytes(data.database_bytes)}</h3>
          <p>SQLite case records + {bytes(data.wal_bytes)} WAL</p>
        </article>
        <article>
          <Download />
          <h3>{bytes(data.disk_free_bytes)}</h3>
          <p>Available disk · collection cap {bytes(data.vault_limit_bytes)}</p>
        </article>
      </div>
      <div className="collection-paths">
        <h3>Actual storage locations</h3>
        <code>{data.database_path}</code>
        <code>{data.originals_path}</code>
        <code>{data.derivatives_path}</code>
        <div className="collection-actions">
          <a className="button" href="/api/vault/database">
            <Download size={14} /> Download consistent database snapshot
          </a>
          <a className="button" href="/api/audit/anchor">
            Download audit hash anchor
          </a>
          <button
            className="button"
            onClick={async () => {
              try {
                const r = await api("/audit/verify");
                notify(
                  r.valid
                    ? `Audit chain verified: ${r.events_checked} events`
                    : `AUDIT INTEGRITY FAILURE: ${r.issues.length} issues`,
                );
              } catch (e: any) {
                notify(e.message);
              }
            }}
          >
            Verify audit chain
          </button>
          <a className="button" href="/api/vault/manifest" target="_blank">
            Verify original-file SHA-256 manifest
          </a>
        </div>
      </div>
      <h3>Collector and scheduler health</h3>
      <div className="heartbeat-grid">
        {data.heartbeats.map((h: any) => (
          <article key={h.name}>
            <span
              className={"status " + (h.state === "ALIVE" ? "green" : "amber")}
            >
              {h.state}
            </span>
            <strong>{h.name}</strong>
            <small>Heartbeat {h.age_seconds}s ago</small>
          </article>
        ))}
      </div>
      <div className="notice">
        Schedules need an awake host and running service. Source or Tor access
        failures remain visible; a search catalogue is counted separately from
        an acquired paper or photograph.
      </div>
      <div className="two-col">
        <section>
          <h3>Acquisition growth · UTC retrieval dates</h3>
          {data.acquisition_by_day.map((d: any) => (
            <div className="growth-row" key={d.day}>
              <code>{d.day}</code>
              <div style={{ width: `${Math.max(5, d.records * 5)}px` }} />
              <span>
                {d.records} records · {bytes(d.bytes || 0)}
              </span>
            </div>
          ))}
        </section>
        <section>
          <h3>Queue state</h3>
          {data.jobs.map((j: any) => (
            <div className="queue-count" key={j.status}>
              <span>{j.status}</span>
              <strong>{j.count}</strong>
            </div>
          ))}
          <p>
            Tor: <span className="status amber">{data.tor.state}</span>
          </p>
        </section>
      </div>
      <h3>Stored artefacts and investigative notes</h3>
      <input
        className="field"
        placeholder="Filter inventory by title, type or evidence ID"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <div className="inventory-table">
        <table>
          <thead>
            <tr>
              <th>Evidence / source</th>
              <th>Collection role</th>
              <th>Bytes</th>
              <th>Acquisition</th>
            </tr>
          </thead>
          <tbody>
            {data.records
              .filter((e: any) =>
                (e.title + " " + e.id + " " + e.mime)
                  .toLowerCase()
                  .includes(query.toLowerCase()),
              )
              .map((e: any) => (
                <tr key={e.id}>
                  <td>
                    <button onClick={() => selectEvidence(e.id)}>
                      {e.title}
                    </button>
                    <small>
                      {e.id} · {e.mime}
                    </small>
                  </td>
                  <td>{e.role}</td>
                  <td>{e.file_exists ? bytes(e.size) : "—"}</td>
                  <td>
                    <span
                      className={
                        "status " + (e.file_exists ? "green" : "amber")
                      }
                    >
                      {e.file_exists ? "BYTES PRESENT" : e.status}
                    </span>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <p className="muted">{data.coverage}</p>
    </div>
  );
}

export function PatentWorkspace({ selectEvidence, notify }: any) {
  const [data, setData] = useState<any>({ records: [] }),
    [selected, setSelected] = useState(""),
    [query, setQuery] = useState("Mondaloy");
  const refresh = () =>
    api("/patents")
      .then(setData)
      .catch((e) => notify(e.message));
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10000);
    return () => clearInterval(t);
  }, []);
  const record =
      data.records.find((r: any) => r.evidence_id === selected) ||
      data.records.find((r: any) =>
        r.data.publication_number?.includes("US:20100266442:A1"),
      ) ||
      data.records[0],
    p = record?.data;
  return (
    <div className="page-scroll collection-workspace">
      <div className="section-title">
        <h2>Mondaloy patent intelligence</h2>
        <span className="status amber">
          DISCLOSURES ≠ DEMONSTRATED PERFORMANCE
        </span>
      </div>
      <div className="notice">{data.warning}</div>
      <div className="collection-actions">
        <input
          className="field"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          className="button primary"
          onClick={async () => {
            try {
              const c = await post("/research", {
                name: "Patent landscape · " + query,
                question:
                  "Acquire original patent disclosures, citation links and technical evidence for " +
                  query,
                queries: [query],
                providers: ["patents", "public_web"],
                max_downloads: 12,
                follow_patents: true,
                cron_expression: "17 */6 * * *",
              });
              notify("Recurring patent campaign created: " + c.id);
            } catch (e: any) {
              notify(e.message);
            }
          }}
        >
          <Play size={14} /> Start recurring patent search
        </button>
      </div>
      <div className="patent-layout">
        <div className="patent-list">
          {data.records.map((r: any) => (
            <button
              className={r.evidence_id === p?.evidence_id ? "active" : ""}
              key={r.evidence_id}
              onClick={() => setSelected(r.evidence_id)}
            >
              <strong>
                {r.data.publication_number?.join(", ") || r.evidence_id}
              </strong>
              <span>{r.data.title?.join(" ")}</span>
              <small>
                Priority {r.data.priority_date || "unknown"} ·{" "}
                {r.data.inventors?.join(" / ")}
              </small>
            </button>
          ))}
        </div>
        {p ? (
          <article className="patent-detail">
            <span className="eyebrow">
              {p.publication_number?.join(", ")} · {p.review_state}
            </span>
            <h3>{p.title?.join(" ")}</h3>
            <div className="collection-actions">
              <button
                className="button"
                onClick={() => selectEvidence(p.evidence_id)}
              >
                Inspect acquired source & provenance
              </button>
              {p.pdf_urls?.map((url: string) => (
                <button
                  className="button"
                  key={url}
                  onClick={async () => {
                    try {
                      await post("/jobs", {
                        url,
                        title:
                          p.publication_number.join(" ") + " · Original PDF",
                      });
                      notify("Original patent PDF queued");
                    } catch (e: any) {
                      notify(e.message);
                    }
                  }}
                >
                  Acquire original PDF
                </button>
              ))}
            </div>
            <dl>
              <dt>Inventors as printed</dt>
              <dd>{p.inventors.join(" · ")}</dd>
              <dt>Assignee catalogue labels</dt>
              <dd>{p.assignees.join(" · ")}</dd>
              <dt>Priority / filing / publication</dt>
              <dd>
                {p.priority_date} / {p.filing_date} / {p.publication_date}
              </dd>
              <dt>Displayed legal status · review required</dt>
              <dd>{p.displayed_legal_status || "Not extracted"}</dd>
              <dt>Experimental demonstration</dt>
              <dd>{p.demonstration_status}</dd>
            </dl>
            <details open>
              <summary>Patent claim text · source assertions</summary>
              {p.claims.map((claim: string, i: number) => (
                <p className="patent-claim" key={i}>
                  {claim}
                </p>
              ))}
            </details>
            <details>
              <summary>
                Backward citation identifiers ({p.references.length})
              </summary>
              <pre>{p.references.join("\n")}</pre>
            </details>
            <details>
              <summary>
                Linked patent records, citations and family leads (
                {p.linked_patents.length})
              </summary>
              {p.linked_patents.map((link: any, i: number) => (
                <div key={i} className="patent-link">
                  <strong>{link.identifier}</strong>
                  <small>{link.section_heading}</small>
                  <a
                    href={new URL(link.href, p.source_url).href}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open publisher record
                  </a>
                </div>
              ))}
            </details>
            <p className="muted">{p.source_warning}</p>
          </article>
        ) : (
          <p>
            Patent indexing runs automatically after isolated extraction.
            Originals queued before this parser upgrade need reprocessing.
          </p>
        )}
      </div>
    </div>
  );
}

export function PhotoWorkspace({ selectEvidence, notify }: any) {
  const [data, setData] = useState<any>({ leads: [], images: [] });
  const refresh = () =>
    api("/photo-corpus")
      .then(setData)
      .catch((e) => notify(e.message));
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="page-scroll collection-workspace">
      <div className="section-title">
        <h2>Public photograph collection & attribution</h2>
        <span className="status amber">IDENTITY REVIEW REQUIRED</span>
      </div>
      <div className="notice">{data.coverage}</div>
      <h3>Publisher-linked photograph leads</h3>
      {data.leads.length ? (
        data.leads.map((l: any) => (
          <article className="photo-lead" key={l.url}>
            <div>
              <strong>{l.data.parent_title}</strong>
              <p>{l.data.caption}</p>
              <small>
                {l.data.subject_status} · {l.url}
              </small>
            </div>
            <button
              className="button"
              onClick={() => selectEvidence(l.parent_evidence_id)}
            >
              Source page
            </button>
            <button
              className="button primary"
              onClick={async () => {
                try {
                  if (l.acquired) selectEvidence(l.acquired.id);
                  else {
                    await post("/photo-corpus/queue", {
                      parent_evidence_id: l.parent_evidence_id,
                      url: l.url,
                    });
                    notify("Original image acquisition queued");
                  }
                } catch (e: any) {
                  notify(e.message);
                }
              }}
            >
              {l.acquired ? "Inspect acquired original" : "Acquire image bytes"}
            </button>
          </article>
        ))
      ) : (
        <p>
          No publisher-linked subject leads have been extracted yet. Denied
          source pages remain failed acquisition records.
        </p>
      )}
      <h3>
        Preserved image library · subject photographs, contextual media and game
        artwork
      </h3>
      <div className="photo-grid">
        {data.images.map((e: any) => (
          <button key={e.id} onClick={() => selectEvidence(e.id)}>
            <img src={e.previewUrl} alt={e.title} />
            <strong>{e.title}</strong>
            <small>
              {e.id} · {e.status}
            </small>
            <span>
              {e.metadata.dimensions?.join(" × ")} · {bytes(e.size)}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { api, post } from "./api";
import { Search, Database, RefreshCw, FileText, Link2 } from "lucide-react";
import "./collection.css";

function citedFocus(text: string, query: string): string {
  // Select an actual phrase inside the returned passage for visible PDF block highlighting.
  const words = query.match(/[\p{L}\p{N}]+/gu) || [];
  const candidates: string[][] = [];
  for (let count = Math.min(4, words.length); count >= 1; count--)
    for (let start = 0; start + count <= words.length; start++)
      candidates.push(words.slice(start, start + count));
  candidates.sort((a, b) => b.join(" ").length - a.join(" ").length);
  for (const tokens of candidates) {
    if (tokens.join(" ").length < 7) continue;
    const found = text.match(
      new RegExp("\\b" + tokens.join("\\s+") + "\\b", "iu"),
    );
    if (found) return found[0];
  }
  return text.slice(0, 180);
}

export default function KnowledgeWorkspace({ selectEvidence, notify }: any) {
  const [status, setStatus] = useState<any>(null);
  const [query, setQuery] = useState("burn resistant nickel alloy inventors");
  const [mode, setMode] = useState("hybrid");
  const [result, setResult] = useState<any>(null);
  const [identifiers, setIdentifiers] = useState<any>(null);
  const [kind, setKind] = useState("PATENT");
  const [busy, setBusy] = useState(false);
  const refresh = () =>
    api("/knowledge/status")
      .then(setStatus)
      .catch((e) => notify(e.message));
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    setIdentifiers(null);
    api("/knowledge/identifiers?kind=" + kind)
      .then(setIdentifiers)
      .catch((e) => notify(e.message));
  }, [kind, status?.chunks]);
  async function search(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      setResult(await post("/knowledge/search", { query, mode, limit: 12 }));
    } catch (e: any) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page-scroll collection-workspace knowledge-workspace">
      <div className="section-title">
        <h2>
          <Search size={21} /> Evidence retrieval & cross-reference
        </h2>
        <span className="status blue">EXACT SOURCE CITATIONS</span>
      </div>
      <p>
        Search acquired originals by meaning and keywords. Every passage is
        checked against its preserved original and extracted text before
        display.
      </p>
      <div className="collection-metrics">
        <article>
          <Database />
          <h3>{status?.chunks ?? "…"}</h3>
          <p>Persistent cited passages</p>
        </article>
        <article>
          <FileText />
          <h3>
            {status?.documents?.find((d: any) => d.status === "COMPLETE")
              ?.count ?? 0}
          </h3>
          <p>Indexed original records</p>
        </article>
        <article>
          <Link2 />
          <h3>{status?.identifier_occurrences ?? "…"}</h3>
          <p>Literal identifier occurrences</p>
        </article>
        <article>
          <RefreshCw />
          <h3>{status?.running ? "INDEXING" : "WATCHING"}</h3>
          <p>New processed evidence checked every 60 seconds</p>
        </article>
      </div>
      <div className="collection-paths">
        <strong>
          Elasticsearch BM25 + Qdrant cosine search · local MiniLM · 384
          dimensions
        </strong>
        <p>
          {status?.error ||
            "Sources retain original hashes, derivative hashes, page numbers and character offsets. AI-written notes are excluded."}
        </p>
        <small>
          Last cycle: {status?.last_cycle || "Starting"}. Passage limit:{" "}
          {status?.max_chunks_per_document ?? 2000} per document; any truncation
          appears below.
        </small>
        <button
          className="button"
          onClick={() =>
            post("/knowledge/index", {})
              .then(() => {
                notify("Indexing cycle queued");
                refresh();
              })
              .catch((e) => notify(e.message))
          }
        >
          Check for new evidence
        </button>
      </div>
      <form onSubmit={search} className="knowledge-query">
        <input
          aria-label="Evidence research query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask about an alloy, publication or technical claim"
          minLength={2}
          maxLength={500}
          required
        />
        <select
          aria-label="Retrieval mode"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="hybrid">Hybrid · meaning + keywords</option>
          <option value="keyword">Keywords · BM25</option>
          <option value="semantic">Meaning · local vectors</option>
        </select>
        <button className="button primary" disabled={busy} type="submit">
          {busy ? "Verifying sources…" : "Search stored evidence"}
        </button>
      </form>
      {result && (
        <section aria-label="Cited search results">
          <h3>{result.results.length} verified passages</h3>
          <a
            className="button"
            href={"/api/knowledge/queries/" + result.id}
            target="_blank"
            rel="noreferrer"
          >
            Open reproducible query record · JSON
          </a>
          <p>{result.answer.assessment}</p>
          {result.results.map((hit: any) => (
            <article className="knowledge-hit" key={hit.id}>
              <div>
                <span className="status green">SOURCE HASH CHECKED</span>
                <span className="status blue">{hit.acquisition_status}</span>
              </div>
              <h3>{hit.title}</h3>
              <blockquote>{hit.text}</blockquote>
              <p>
                {hit.page ? `PDF page ${hit.page} · ` : "Text extract · "}
                characters {hit.start}–{hit.end} · {hit.evidence_id}
              </p>
              <small>{hit.source_url}</small>
              <code>SHA-256 {hit.original_sha256}</code>
              <button
                className="button"
                onClick={() =>
                  selectEvidence(
                    hit.evidence_id,
                    citedFocus(hit.text, result.query),
                  )
                }
              >
                Open original & cited passage
              </button>
            </article>
          ))}
          {!result.results.length && (
            <p>
              No verified passages matched. The index does not include missing
              originals or secondary notes.
            </p>
          )}
        </section>
      )}
      <section className="collection-paths">
        <h3>Cross-document identifier matches</h3>
        <p>
          Exact identifiers appearing in multiple acquired records. Citations,
          copies and shared names do not prove independent corroboration or
          account ownership.
        </p>
        <select
          aria-label="Identifier category"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          {["PATENT", "DOI", "PUBLIC_HANDLE", "ISO_DATE", "SHA256"].map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
        {identifiers?.results?.map((group: any) => (
          <details key={group.normalized}>
            <summary>
              {group.normalized} · {group.sources} records
            </summary>
            {group.occurrences.map((m: any, i: number) => (
              <button
                className="search-result"
                key={m.evidence_id + i}
                onClick={() => selectEvidence(m.evidence_id, m.value)}
              >
                <strong>{m.title}</strong>
                <p>{m.context}</p>
                <small>
                  Exact characters {m.start}–{m.end} · {m.evidence_id}
                </small>
              </button>
            ))}
          </details>
        ))}
        {identifiers && !identifiers.results.length && (
          <p>No cross-document matches currently indexed for this category.</p>
        )}
      </section>
      <details className="collection-paths">
        <summary>Index processing records and coverage</summary>
        {status?.recent_documents.map((d: any) => (
          <p key={d.evidence_id}>
            <strong>{d.evidence_id}</strong> · {d.status} ·{" "}
            {d.data.chunk_count ?? 0} passages{" "}
            {d.data.truncated ? "· PASSAGE LIMIT REACHED" : ""}{" "}
            {d.data.extraction_truncated ? "· SOURCE EXTRACTION TRUNCATED" : ""}{" "}
            {d.data.failure || ""}
          </p>
        ))}
      </details>
    </div>
  );
}

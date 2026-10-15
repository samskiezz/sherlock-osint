import React, { useEffect, useRef, useState } from "react";
import { api, post } from "./api";
import "./entities.css";

type Entity = {
  id: string;
  canonical_name?: string;
  kind?: string;
  aliases?: string[];
  mention_ids?: string[];
  mentions?: {
    id: string;
    surface: string;
    evidence_id: string;
    byte_offset: number;
    offset_space: string;
    valid_from: number;
    valid_to: number;
  }[];
};
type Lineage = {
  support: string[];
  why: string[][];
  minimal_witnesses: string[][];
  count: number | string;
  boolean: boolean;
  how: unknown;
  decisions: { a: string; b: string; score: number; decision: string }[];
};
type Source = { id: string; source_uuid: string; title: string };
export default function EntitiesWorkspace() {
  const [entities, setEntities] = useState<Entity[]>([]),
    [selected, setSelected] = useState<Entity | null>(null);
  const [lineage, setLineage] = useState<Lineage | null>(null),
    [neighbors, setNeighbors] = useState<Entity[]>([]);
  const [sources, setSources] = useState<Source[]>([]),
    [source, setSource] = useState("");
  const [query, setQuery] = useState(""),
    [next, setNext] = useState<string | null>(null);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [ready, setReady] = useState(false);
  const [retract, setRetract] = useState(false),
    [raw, setRaw] = useState("");
  const inspection = useRef(0);
  function clearInspection() {
    inspection.current += 1;
    setSelected(null);
    setLineage(null);
    setNeighbors([]);
  }
  async function load(after?: string) {
    const q = new URLSearchParams({ q: query, limit: "30" });
    if (after) q.set("after", after);
    const result = await api("/erps/entities?" + q);
    setEntities((old) =>
      after ? [...old, ...result.entities] : result.entities,
    );
    setNext(result.next);
  }
  async function inspect(id: string) {
    const request = ++inspection.current;
    setError("");
    setSelected(null);
    setLineage(null);
    setNeighbors([]);
    try {
      const detail = await api("/erps/entities/" + id);
      if (request !== inspection.current) return;
      setSelected(detail);
      const [history, graph] = await Promise.all([
        api("/erps/lineage/" + id),
        api("/erps/entities/" + id + "/neighbors?depth=1&limit=20"),
      ]);
      if (request !== inspection.current) return;
      setLineage(history);
      setNeighbors(graph.entities.filter((e: Entity) => e.id !== id));
    } catch (e) {
      if (request === inspection.current) setError(String(e));
    }
  }
  async function act(task: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    let active = true;
    Promise.all([api("/erps/health"), api("/erps/sources")])
      .then(([, s]) => {
        if (!active) return;
        setReady(true);
        setSources(s.sources);
        return load();
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, []);
  const label = (id: string) =>
    sources.find((s) => s.source_uuid === id)?.title || id;
  return (
    <section className="erps-workspace" aria-label="Entity resolution">
      <div className="erps-intro">
        <div>
          <p className="erps-eyebrow">ENTITY RESOLUTION & PROVENANCE</p>
          <h2>Follow the evidence behind each entity</h2>
          <p>
            Find linked mentions, inspect their supporting sources, and review
            uncertain associations.
          </p>
        </div>
        <span className={ready ? "erps-status ready" : "erps-status"}>
          {ready ? "Service connected" : "Service unavailable"}
        </span>
      </div>
      {error && (
        <div role="alert" className="erps-error">
          {error}
        </div>
      )}
      {notice && (
        <div role="status" className="erps-notice">
          {notice}
        </div>
      )}
      <form
        className="erps-toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          void act(() => load());
        }}
      >
        <input
          aria-label="Search entities"
          placeholder="Search canonical names…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button disabled={busy || !ready}>Search</button>
      </form>
      <div className="erps-columns">
        <aside className="erps-list">
          <h3>
            Entities <small>{entities.length} loaded</small>
          </h3>
          {!entities.length && (
            <p className="erps-muted">
              No entities found. Index a verified source below to extract
              mentions.
            </p>
          )}
          {entities.map((e) => (
            <button
              key={e.id}
              className={selected?.id === e.id ? "selected" : ""}
              onClick={() => void inspect(e.id)}
            >
              <strong>{e.canonical_name || "Restricted entity"}</strong>
              <span>
                {e.kind} · {e.mention_ids?.length ?? "—"} mentions
              </span>
            </button>
          ))}
          {next && (
            <button disabled={busy} onClick={() => void act(() => load(next))}>
              Load more
            </button>
          )}
        </aside>
        <article className="erps-detail">
          {!selected ? (
            <div className="erps-empty">
              <h3>Select an entity to inspect its lineage</h3>
              <p>
                Similarity scores guide resolution and are uncalibrated. Review
                associations are suggestions for an analyst.
              </p>
            </div>
          ) : (
            <>
              <p className="erps-eyebrow">{selected.kind}</p>
              <h2>{selected.canonical_name || selected.id}</h2>
              <code>{selected.id}</code>
              <h3>Aliases</h3>
              <div className="erps-tags">
                {selected.aliases?.map((a) => (
                  <span key={a}>{a}</span>
                ))}
              </div>
              <h3>Mentions</h3>
              {selected.mentions?.map((m) => (
                <div className="erps-mention" key={m.id}>
                  <strong>{m.surface}</strong>
                  <span>{label(m.evidence_id)}</span>
                  <small>
                    Byte {m.byte_offset} in{" "}
                    {m.offset_space === "ExtractedTextUtf8"
                      ? "extracted UTF-8 text"
                      : "source bytes"}
                  </small>
                  <small>
                    Valid interval [{m.valid_from}, {m.valid_to})
                  </small>
                </div>
              ))}
              {lineage && (
                <>
                  <h3>Supporting evidence</h3>
                  <p>
                    {lineage.support.length} sources · {lineage.count}{" "}
                    derivations ·{" "}
                    {lineage.boolean ? "Supported" : "Unsupported"}
                  </p>
                  <ul>
                    {lineage.support.map((s) => (
                      <li key={s}>{label(s)}</li>
                    ))}
                  </ul>
                  <h3>Witness sets</h3>
                  <p className="erps-muted">
                    Each row gives sources that together support one derivation
                    of membership. Separate rows are alternatives. These do not
                    prove that a merge decision is correct.
                  </p>
                  {lineage.why.map((w, i) => (
                    <div className="erps-witness" key={i}>
                      {w.length
                        ? w.map((s) => label(s)).join(" + ")
                        : "Source-independent derivation"}
                    </div>
                  ))}
                  <details>
                    <summary>Provenance polynomial</summary>
                    <pre>{JSON.stringify(lineage.how, null, 2)}</pre>
                  </details>
                  <h3>Scored candidate pairs</h3>
                  <p className="erps-muted">
                    Scores express similarity, rather than a probability of
                    identity.
                  </p>
                  {lineage.decisions.slice(0, 100).map((d, i) => (
                    <div className="erps-pair" key={i}>
                      <span>{d.decision}</span>
                      <strong>{d.score.toFixed(3)}</strong>
                      <small>
                        {d.a.slice(0, 8)} ↔ {d.b.slice(0, 8)}
                      </small>
                    </div>
                  ))}
                </>
              )}
              <h3>Nearby candidate entities</h3>
              {neighbors.length ? (
                neighbors.map((n) => (
                  <button
                    className="erps-neighbor"
                    key={n.id}
                    onClick={() => void inspect(n.id)}
                  >
                    {n.canonical_name} →
                  </button>
                ))
              ) : (
                <p className="erps-muted">No visible review associations.</p>
              )}
            </>
          )}
        </article>
      </div>
      <div className="erps-operations">
        <section>
          <h3>Index verified evidence</h3>
          <p>
            Extract email addresses, handles, DOIs, and possible person names
            from preserved text. Name extraction is a rule-based baseline.
          </p>
          <select
            aria-label="Evidence source"
            value={source}
            onChange={(e) => {
              setSource(e.target.value);
              setRetract(false);
            }}
          >
            <option value="">Choose a verified source</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </select>
          <button
            disabled={busy || !ready || !source}
            onClick={() =>
              void act(async () => {
                const r = await post("/erps/index", { evidence_id: source });
                if (r.status !== "complete")
                  throw new Error(r.error || "Ingestion queued for retry");
                await load();
                clearInspection();
                setNotice("Source indexed. Entity list refreshed.");
              })
            }
          >
            Index source
          </button>
          <button
            className="erps-subtle"
            disabled={busy || !source}
            onClick={() => setRetract(true)}
          >
            Retract source…
          </button>
          {retract && (
            <div className="erps-confirm">
              <p>
                Retract this source from ERPS and recompute the workspace
                partition. Original evidence stays in the vault. This source
                cannot be ingested again.
              </p>
              <button
                disabled={busy}
                onClick={() =>
                  void act(async () => {
                    const s = sources.find((s) => s.id === source)!;
                    const r = await post("/erps/deletion", {
                      source_var: s.source_uuid,
                    });
                    clearInspection();
                    setRetract(false);
                    await load();
                    setNotice(
                      `Retraction complete: ${r.affected_mentions} mentions affected.`,
                    );
                  })
                }
              >
                Confirm retraction
              </button>
              <button onClick={() => setRetract(false)}>Cancel</button>
            </div>
          )}
        </section>
        <details>
          <summary>Submit structured mentions</summary>
          <p>
            Paste a /resolve JSON request with UUID identifiers, mention kinds,
            byte offsets, and valid-time intervals.
          </p>
          <textarea
            aria-label="Structured mentions JSON"
            rows={9}
            placeholder={'{"mentions": [...], "constraints": []}'}
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
          />
          <button
            disabled={busy || !ready || !raw}
            onClick={() =>
              void act(async () => {
                const result = await api("/erps/resolve", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: raw,
                });
                await load();
                clearInspection();
                setNotice(
                  `Resolved ${result.entities.length} entities using ${result.scoring_engine}.`,
                );
              })
            }
          >
            Resolve mentions
          </button>
        </details>
      </div>
    </section>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
} from "@xyflow/react";
import { api, post } from "./api";
import {
  Plus,
  Search,
  GitBranch,
  MapPin,
  ShieldCheck,
  Clock3,
  X,
  Download,
  RotateCcw,
} from "lucide-react";
import "./workspaces.css";

type Props = {
  evidence: any[];
  selectEvidence: (id: string, quote?: string) => void;
  notify: (text: string) => void;
};
const colors: Record<string, string> = {
  DOCUMENTED: "#5baaff",
  CORROBORATED: "#61c39f",
  CONTRADICTED: "#f16b74",
  HYPOTHESIS: "#b99af3",
  UNVERIFIED: "#d8ab61",
  REJECTED: "#8a92a4",
};
const isoDate = (time: number, span: number) =>
  new Date(time)
    .toISOString()
    .slice(0, span < 86400000 ? 19 : span < 86400000 * 100 ? 10 : 7)
    .replace("T", " ");

export function TimelineWorkspace({ evidence, selectEvidence, notify }: Props) {
  const [events, setEvents] = useState<any[]>([]),
    [hidden, setHidden] = useState<string[]>([]),
    [range, setRange] = useState<[number, number] | null>(null),
    [active, setActive] = useState<any>(null),
    [form, setForm] = useState(false);
  const [draft, setDraft] = useState({
    title: "",
    start: "",
    end: "",
    date_type: "Publication",
    evidence_id: "",
    quote: "",
    layer: "Source chronology",
  });
  const container = useRef<HTMLDivElement>(null),
    drag = useRef<{ x: number; range: [number, number] } | null>(null);
  const load = () =>
    api("/chronology")
      .then(setEvents)
      .catch((e) => notify(e.message));
  useEffect(() => {
    load();
  }, []);
  const layers = [...new Set(events.map((e) => e.layer))];
  const shown = events.filter((e) => !hidden.includes(e.layer));
  const full: [number, number] = useMemo(() => {
    const times = events
      .flatMap((e) => [Date.parse(e.start), Date.parse(e.end)])
      .filter(Number.isFinite);
    const lo = Math.min(...times),
      hi = Math.max(...times);
    const margin = Math.max((hi - lo) * 0.08, 86400000);
    return times.length
      ? [lo - margin, hi + margin]
      : [Date.now() - 86400000, Date.now() + 86400000];
  }, [events]);
  const bounds = range || full,
    span = bounds[1] - bounds[0];
  const scale = (t: number) => 160 + ((t - bounds[0]) / span) * 1000;
  const zoom = (factor: number, center = (bounds[0] + bounds[1]) / 2) => {
    const ns = Math.min(86400000 * 365 * 2000, Math.max(1000, span * factor));
    const ratio = (center - bounds[0]) / span;
    setRange([center - ratio * ns, center + (1 - ratio) * ns]);
  };
  return (
    <div className="lab-page timeline-workspace">
      <div className="lab-heading">
        <div>
          <span className="eyebrow">TEMPORAL INTELLIGENCE</span>
          <h2>The evidence has a history.</h2>
          <p>
            Separate publication, archive capture and acquisition. Scroll to
            zoom; drag to travel through time.
          </p>
        </div>
        <button className="button" onClick={() => setForm(!form)}>
          <Plus size={15} /> Add sourced date
        </button>
      </div>
      <div className="lab-toolbar">
        <button className="button" onClick={() => zoom(0.5)}>
          Zoom in
        </button>
        <button className="button" onClick={() => zoom(2)}>
          Zoom out
        </button>
        <button className="button" onClick={() => setRange(null)}>
          <RotateCcw size={13} /> Fit history
        </button>
        <span className="eyebrow">
          {isoDate(bounds[0], span)} — {isoDate(bounds[1], span)} UTC
        </span>
      </div>
      <div className="layer-filters">
        {layers.map((layer) => (
          <label key={layer}>
            <input
              type="checkbox"
              checked={!hidden.includes(layer)}
              onChange={() =>
                setHidden(
                  hidden.includes(layer)
                    ? hidden.filter((x) => x !== layer)
                    : [...hidden, layer],
                )
              }
            />
            {layer}{" "}
            <small>{events.filter((e) => e.layer === layer).length}</small>
          </label>
        ))}
      </div>
      <div
        className="timeline-stage"
        ref={container}
        onWheel={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const ratio = Math.max(
            0,
            Math.min(1, (e.clientX - rect.left) / rect.width),
          );
          zoom(e.deltaY > 0 ? 1.25 : 0.8, bounds[0] + ratio * span);
        }}
        onPointerDown={(e) => {
          if ((e.target as Element).closest(".time-event")) return;
          drag.current = { x: e.clientX, range: bounds };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (!drag.current) return;
          const dx =
            ((e.clientX - drag.current.x) /
              (container.current?.clientWidth || 1000)) *
            (drag.current.range[1] - drag.current.range[0]);
          setRange([drag.current.range[0] - dx, drag.current.range[1] - dx]);
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
      >
        <svg
          viewBox={`0 0 1200 ${Math.max(250, layers.length * 145 + 70)}`}
          role="img"
          aria-label="Interactive source chronology"
        >
          <defs>
            <clipPath id="timeline-clip">
              <rect x="160" y="0" width="1020" height="2000" />
            </clipPath>
          </defs>
          {Array.from({ length: 7 }, (_, i) => {
            const t = bounds[0] + (span * i) / 6;
            return (
              <g key={i}>
                <line
                  x1={scale(t)}
                  x2={scale(t)}
                  y1="42"
                  y2="2000"
                  stroke="#263242"
                  strokeDasharray="3 7"
                />
                <text
                  x={scale(t)}
                  y="23"
                  fill="#95a4b9"
                  fontSize="11"
                  textAnchor="middle"
                >
                  {isoDate(t, span)}
                </text>
              </g>
            );
          })}
          {layers
            .filter((l) => !hidden.includes(l))
            .map((layer, i) => (
              <g key={layer}>
                <text x="16" y={92 + i * 145} fill="#c6d2df" fontSize="12">
                  {layer.slice(0, 20)}
                </text>
                <line
                  x1="160"
                  x2="1180"
                  y1={86 + i * 145}
                  y2={86 + i * 145}
                  stroke="#273440"
                />
              </g>
            ))}
          <g clipPath="url(#timeline-clip)">
            {shown.map((e) => {
              const row = layers
                .filter((l) => !hidden.includes(l))
                .indexOf(e.layer);
              const others = shown.filter((x) => x.layer === e.layer);
              const slot = others.indexOf(e) % 4;
              const y = 80 + row * 145 + slot * 27;
              const x = scale(Date.parse(e.start));
              const end = scale(Date.parse(e.end));
              return (
                <g
                  key={e.id}
                  className="time-event"
                  tabIndex={0}
                  role="button"
                  aria-label={e.title}
                  onClick={() => setActive(e)}
                  onKeyDown={(ev) => {
                    if (ev.key === "Enter") setActive(e);
                  }}
                >
                  <line
                    x1={x}
                    x2={Math.max(x + 1, end)}
                    y1={y}
                    y2={y}
                    stroke={e.date_type === "Retrieval" ? "#5baaff" : "#d8ab61"}
                    strokeWidth="8"
                  />
                  <circle
                    cx={x}
                    cy={y}
                    r="5"
                    fill={e.date_type === "Retrieval" ? "#5baaff" : "#d8ab61"}
                  />
                  <text
                    x={x + 10}
                    y={y + 4}
                    fontSize="11"
                    fill={active?.id === e.id ? "#fff" : "#b7c9d9"}
                  >
                    {e.title.slice(0, 43)}
                  </text>
                  <title>
                    {e.date_type}: {e.start}\n{e.title}
                  </title>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      {active && (
        <div className="temporal-detail">
          <div>
            <span className="eyebrow">
              {active.date_type.toUpperCase()} · {active.status}
            </span>
            <h3>{active.title}</h3>
            <p>
              {active.start} {active.end !== active.start && `— ${active.end}`}
            </p>
            <p>
              {active.interpretation ||
                "Retrieval records when this application acquired bytes; it cannot establish when the source was originally created."}
            </p>
            {active.citations.map((c: any) => (
              <blockquote key={c.id}>{c.quote}</blockquote>
            ))}
          </div>
          <button
            className="button"
            onClick={() =>
              selectEvidence(active.evidence_id, active.citations[0]?.quote)
            }
          >
            Inspect original →
          </button>
        </div>
      )}
      {form && (
        <form
          className="lab-form"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await post("/chronology", { ...draft, end: draft.end || null });
              setForm(false);
              load();
              notify("Sourced date saved; interpretation remains explicit");
            } catch (e: any) {
              notify(e.message);
            }
          }}
        >
          <h3>Add a source-linked date</h3>
          <label>
            Title
            <input
              required
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            />
          </label>
          <div className="form-grid">
            <label>
              Start / exact date
              <input
                required
                type="date"
                value={draft.start}
                onChange={(e) => setDraft({ ...draft, start: e.target.value })}
              />
            </label>
            <label>
              End of uncertainty interval
              <input
                type="date"
                value={draft.end}
                onChange={(e) => setDraft({ ...draft, end: e.target.value })}
              />
            </label>
            <label>
              Date meaning
              <select
                value={draft.date_type}
                onChange={(e) =>
                  setDraft({ ...draft, date_type: e.target.value })
                }
              >
                {[
                  "Creation",
                  "Publication",
                  "Archive capture",
                  "Modification",
                  "Repository commit",
                  "Catalogue indexing",
                  "Event",
                ].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </label>
            <label>
              Layer
              <input
                value={draft.layer}
                onChange={(e) => setDraft({ ...draft, layer: e.target.value })}
              />
            </label>
          </div>
          <SourceFields
            evidence={evidence}
            value={draft}
            onChange={(v) => setDraft({ ...draft, ...v })}
          />
          <button className="button primary">Save sourced date</button>
          <p className="muted">
            The source must contain the proposed year. Date meaning is your
            interpretation and remains visible.
          </p>
        </form>
      )}
      <div className="timeline-records">
        {shown.map((e) => (
          <button key={e.id} onClick={() => setActive(e)}>
            <span className="eyebrow">{e.date_type}</span>
            <strong>{e.title}</strong>
            <time>{e.start.slice(0, 10)}</time>
          </button>
        ))}
      </div>
    </div>
  );
}

export function SourceFields({
  evidence,
  value,
  onChange,
  required = true,
}: {
  evidence: any[];
  value: any;
  onChange: (value: any) => void;
  required?: boolean;
}) {
  const source = evidence.find((e) => e.id === value.evidence_id);
  return (
    <>
      <label>
        Acquired original
        <select
          required={required}
          value={value.evidence_id}
          onChange={(e) => onChange({ evidence_id: e.target.value, quote: "" })}
        >
          <option value="">Choose an acquired source</option>
          {evidence
            .filter((e) => e.fileUrl && e.text)
            .map((e) => (
              <option key={e.id} value={e.id}>
                {e.title}
              </option>
            ))}
        </select>
      </label>
      {source && (
        <details className="source-text">
          <summary>Read attested source text</summary>
          <pre>{source.text}</pre>
        </details>
      )}
      <label>
        Exact supporting passage
        <textarea
          required={required}
          rows={4}
          value={value.quote}
          onChange={(e) => onChange({ quote: e.target.value })}
          placeholder="Copy the original passage exactly; the backend independently checks the original and derivative hashes."
        />
      </label>
    </>
  );
}

function GraphInner({
  boardId,
  selectEvidence,
  notify,
  onRelationship,
}: {
  boardId: string;
  selectEvidence: (id: string) => void;
  notify: (s: string) => void;
  onRelationship: (edge: Edge) => void;
}) {
  const [graph, setGraph] = useState<any>(null),
    [documented, setDocumented] = useState(true),
    [source, setSource] = useState(""),
    [target, setTarget] = useState(""),
    [highlight, setHighlight] = useState<string[]>([]),
    [highlightEdges, setHighlightEdges] = useState<string[]>([]),
    [message, setMessage] = useState("");
  const load = () =>
    api(`/graph/${boardId}?documented_only=${documented}`)
      .then((g) => {
        setGraph(g);
        setHighlight([]);
        setHighlightEdges([]);
      })
      .catch((e) => notify(e.message));
  useEffect(() => {
    load();
  }, [boardId, documented]);
  const nodes: Node[] = useMemo(
    () =>
      graph?.nodes.map((n: any) => {
        const component = graph.components.findIndex((c: string[]) =>
          c.includes(n.id),
        );
        const group = graph.components[component];
        const i = group.indexOf(n.id);
        const angle = (2 * Math.PI * i) / Math.max(1, group.length);
        return {
          id: n.id,
          data: {
            label: (
              <div className="analysis-node">
                <span>{n.kind.toUpperCase()}</span>
                <strong>{n.title}</strong>
                <small>{n.status}</small>
              </div>
            ),
          },
          position: {
            x: (component % 3) * 600 + 220 + Math.cos(angle) * 180,
            y: Math.floor(component / 3) * 500 + 200 + Math.sin(angle) * 180,
          },
          style: {
            width: 190,
            background:
              highlight.length && !highlight.includes(n.id)
                ? "#111722"
                : "#1c2939",
            color: "#e4ecf3",
            border: `1px solid ${highlight.includes(n.id) ? "#71bcff" : "#44536b"}`,
            opacity: highlight.length && !highlight.includes(n.id) ? 0.35 : 1,
          },
        };
      }) || [],
    [graph, highlight],
  );
  const edges: Edge[] = useMemo(
    () =>
      graph?.edges.map((e: any) => ({
        ...e,
        label: `${e.label || e.data?.claim?.slice(0, 30)} · ${e.data?.state || "UNVERIFIED"}`,
        style: {
          stroke: colors[e.data?.state] || "#8894a6",
          strokeWidth: highlightEdges.includes(e.id) ? 4 : 1.5,
          strokeDasharray: e.citation_verified ? undefined : "5 5",
          opacity:
            highlightEdges.length && !highlightEdges.includes(e.id) ? 0.25 : 1,
        },
        labelStyle: { fill: "#c4d2df", fontSize: 10 },
        labelBgStyle: { fill: "#101822" },
        animated: highlightEdges.includes(e.id),
      })) || [],
    [graph, highlightEdges],
  );
  const query = async (path: boolean) => {
    try {
      const g = await api(
        `/graph/${boardId}?documented_only=${documented}&source=${encodeURIComponent(source)}${path ? `&target=${encodeURIComponent(target)}` : "&hops=2"}`,
      );
      setHighlight(path ? g.path : g.neighbourhood);
      setHighlightEdges(g.path_edges || []);
      setMessage(
        path
          ? g.path.length
            ? `${g.path.length - 1} relationship steps. A path is not proof of a wider allegation.`
            : "No path exists in the selected evidence layer."
          : "Two-hop neighbourhood highlighted.",
      );
    } catch (e: any) {
      notify(e.message);
    }
  };
  if (!graph)
    return <div className="lab-page">Loading source-linked graph…</div>;
  return (
    <div className="graph-workspace">
      <div className="lab-heading">
        <div>
          <span className="eyebrow">NETWORK INTELLIGENCE</span>
          <h2>Find a path. Inspect every step.</h2>
          <p>
            Explicit board relationships only. Dashed lines are leads; shared
            words never create an identity.
          </p>
        </div>
      </div>
      <div className="lab-toolbar">
        <label>
          <input
            type="checkbox"
            checked={documented}
            onChange={(e) => setDocumented(e.target.checked)}
          />{" "}
          Citation-verified relationships only
        </label>
        <a
          className="button"
          href={`/api/graph/${boardId}/export/graphml?documented_only=${documented}`}
        >
          <Download size={13} /> GraphML
        </a>
        <a
          className="button"
          href={`/api/graph/${boardId}/export/gexf?documented_only=${documented}`}
        >
          GEXF
        </a>
      </div>
      <div className="analysis-metrics">
        <div>
          <strong>{graph.nodes.length}</strong>
          <span>board entities</span>
        </div>
        <div>
          <strong>{graph.edges.length}</strong>
          <span>eligible relationships</span>
        </div>
        <div>
          <strong>{graph.components.length}</strong>
          <span>connected components</span>
        </div>
        <div>
          <strong>
            {graph.edges.filter((e: any) => !e.citation_verified).length}
          </strong>
          <span>unverified / disputed edges</span>
        </div>
      </div>
      <div className="lab-toolbar">
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">Starting entity</option>
          {graph.nodes.map((n: any) => (
            <option key={n.id} value={n.id}>
              {n.title}
            </option>
          ))}
        </select>
        <select value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="">Destination entity</option>
          {graph.nodes.map((n: any) => (
            <option key={n.id} value={n.id}>
              {n.title}
            </option>
          ))}
        </select>
        <button
          className="button"
          disabled={!source || !target}
          onClick={() => query(true)}
        >
          <GitBranch size={13} /> Shortest path
        </button>
        <button
          className="button"
          disabled={!source}
          onClick={() => query(false)}
        >
          2-hop network
        </button>
      </div>
      {message && <p className="analysis-message">{message}</p>}
      <div className="analysis-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          minZoom={0.1}
          maxZoom={2}
          onEdgeClick={(_, edge) => onRelationship(edge)}
          onNodeClick={(_, n) =>
            selectEvidence(
              graph.nodes.find((x: any) => x.id === n.id).evidence_id,
            )
          }
        >
          <Background color="#2e3e53" gap={24} />
          <Controls />
          <MiniMap nodeColor="#527596" maskColor="#090f19bb" />
        </ReactFlow>
      </div>
      <div className="degree-rank">
        <h3>Degree ranking</h3>
        {graph.nodes
          .slice()
          .sort((a: any, b: any) => graph.degree[b.id] - graph.degree[a.id])
          .slice(0, 10)
          .map((n: any) => (
            <button key={n.id} onClick={() => selectEvidence(n.evidence_id)}>
              <strong>{graph.degree[n.id]}</strong>
              {n.title}
              <small>explicit neighbours</small>
            </button>
          ))}
      </div>
    </div>
  );
}
export function GraphWorkspace(props: {
  boardId: string;
  selectEvidence: (id: string) => void;
  notify: (s: string) => void;
  onRelationship: (edge: Edge) => void;
}) {
  return (
    <ReactFlowProvider>
      <GraphInner {...props} />
    </ReactFlowProvider>
  );
}

export function ReviewWorkspace({
  boardId,
  evidence,
  selectEvidence,
  notify,
  onReviewed,
}: { boardId: string; onReviewed: () => void } & Props) {
  const [claims, setClaims] = useState<any[]>([]),
    [board, setBoard] = useState<any>(null),
    [form, setForm] = useState(false),
    [reason, setReason] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState({
    source: "",
    target: "",
    relationship: "References",
    claim: "",
    evidence_id: "",
    quote: "",
    contrary_id: "",
    contrary_quote: "",
  });
  const load = () =>
    Promise.all([api("/claims"), api(`/boards/${boardId}`)])
      .then(([c, b]) => {
        setClaims(c);
        setBoard(b);
      })
      .catch((e) => notify(e.message));
  useEffect(() => {
    load();
  }, [boardId]);
  const title = (id: string) =>
    evidence.find(
      (e) =>
        e.id === board?.nodes.find((n: any) => n.id === id)?.data.evidenceId,
    )?.title || id;
  const review = async (c: any, decision: string) => {
    try {
      await post(`/claims/${c.id}/review`, {
        decision,
        reason: reason[c.id] || "",
      });
      await load();
      onReviewed();
      notify("Review saved with source validation and audit history");
    } catch (e: any) {
      notify(e.message);
    }
  };
  return (
    <div className="lab-page">
      <div className="lab-heading">
        <div>
          <span className="eyebrow">EVIDENCE AUDITOR</span>
          <h2>Claims require a reason to exist.</h2>
          <p>
            Review support and contradiction together. Acceptance records a
            human judgment, not an automatic conclusion.
          </p>
        </div>
        <button className="button" onClick={() => setForm(!form)}>
          <Plus size={14} /> Propose relationship
        </button>
      </div>
      <div className="analysis-metrics">
        <div>
          <strong>
            {claims.filter((c) => c.status === "REVIEW REQUIRED").length}
          </strong>
          <span>awaiting review</span>
        </div>
        <div>
          <strong>
            {claims.filter((c) => c.status === "DOCUMENTED").length}
          </strong>
          <span>human accepted</span>
        </div>
        <div>
          <strong>
            {claims.filter((c) => c.status === "CONTRADICTED").length}
          </strong>
          <span>disputed</span>
        </div>
        <div>
          <strong>
            {claims.filter((c) => c.status === "REJECTED").length}
          </strong>
          <span>rejected</span>
        </div>
      </div>
      {form && board && (
        <form
          className="lab-form"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await post("/claims", {
                board_id: boardId,
                source: draft.source,
                target: draft.target,
                relationship: draft.relationship,
                claim: draft.claim,
                supporting: draft.evidence_id
                  ? [{ id: draft.evidence_id, quote: draft.quote }]
                  : [],
                contradicting: draft.contrary_id
                  ? [{ id: draft.contrary_id, quote: draft.contrary_quote }]
                  : [],
              });
              setForm(false);
              load();
              notify("Proposal queued for human review");
            } catch (e: any) {
              notify(e.message);
            }
          }}
        >
          <h3>Propose an explicit relationship</h3>
          <div className="form-grid">
            {["source", "target"].map((key) => (
              <label key={key}>
                {key === "source" ? "From" : "To"}
                <select
                  required
                  value={draft[key as "source" | "target"]}
                  onChange={(e) =>
                    setDraft({ ...draft, [key]: e.target.value })
                  }
                >
                  <option value="">Choose board entity</option>
                  {board.nodes.map((n: any) => (
                    <option key={n.id} value={n.id}>
                      {title(n.id)}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <label>
            Relationship label
            <input
              required
              value={draft.relationship}
              onChange={(e) =>
                setDraft({ ...draft, relationship: e.target.value })
              }
            />
          </label>
          <label>
            Exact claim
            <textarea
              required
              value={draft.claim}
              onChange={(e) => setDraft({ ...draft, claim: e.target.value })}
            />
          </label>
          <SourceFields
            evidence={evidence}
            value={draft}
            onChange={(v) => setDraft({ ...draft, ...v })}
          />
          <details>
            <summary>Add contradicting original evidence</summary>
            <SourceFields
              required={false}
              evidence={evidence}
              value={{
                evidence_id: draft.contrary_id,
                quote: draft.contrary_quote,
              }}
              onChange={(v) =>
                setDraft({
                  ...draft,
                  contrary_id: v.evidence_id ?? draft.contrary_id,
                  contrary_quote: v.quote ?? draft.contrary_quote,
                })
              }
            />
          </details>
          <button className="button primary">Submit for review</button>
        </form>
      )}
      {!claims.length && (
        <div className="lab-empty">
          <ShieldCheck size={36} />
          <h3>No relationship proposals yet</h3>
          <p>
            Create an explicit claim between two board entities and cite an
            acquired original. AI findings remain in Investigator until attached
            as hypotheses.
          </p>
        </div>
      )}
      {claims.map((c) => (
        <article className="review-card" key={c.id}>
          <div className="lab-toolbar">
            <span className="eyebrow">{c.id}</span>
            <span
              className={`status ${c.status === "DOCUMENTED" ? "blue" : c.status === "CONTRADICTED" ? "red" : "amber"}`}
            >
              {c.status}
            </span>
          </div>
          <h3>{c.data.claim}</h3>
          <p>
            {title(c.data.source)} → {c.data.relationship} →{" "}
            {title(c.data.target)}
          </p>
          {["supporting", "contradicting"].map((key) => (
            <div
              key={key}
              className={key === "contradicting" ? "contrary-citations" : ""}
            >
              <h4>{key.toUpperCase()} ORIGINALS</h4>
              {c.data[key].map((citation: any) => (
                <button
                  className="citation-card"
                  key={citation.id + citation.quote}
                  onClick={() => selectEvidence(citation.id, citation.quote)}
                >
                  <blockquote>{citation.quote}</blockquote>
                  <small>
                    {citation.id} · {citation.location} · inspect source →
                  </small>
                </button>
              ))}
              {!c.data[key].length && <p className="muted">None supplied</p>}
            </div>
          ))}
          {c.review && (
            <p className="review-decision">
              {c.review.decision}: {c.review.reason} · {c.review.time}
            </p>
          )}
          <label>
            Review reason
            <textarea
              rows={2}
              value={reason[c.id] || ""}
              onChange={(e) => setReason({ ...reason, [c.id]: e.target.value })}
              placeholder="Explain why the original supports, contradicts or fails to establish this claim."
            />
          </label>
          <div className="lab-toolbar">
            <button
              className="button primary"
              disabled={
                !c.data.supporting.length || !!c.data.contradicting.length
              }
              onClick={() => review(c, "ACCEPT")}
            >
              Accept as documented
            </button>
            <button
              className="button"
              disabled={!c.data.contradicting.length}
              onClick={() => review(c, "DISPUTE")}
            >
              Mark disputed
            </button>
            <button className="button" onClick={() => review(c, "REJECT")}>
              Reject claim
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

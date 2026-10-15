import { api, post } from "./api";
import Investigator from "./Investigator";
import CipherWorkbench from "./CipherWorkbench";
import {
  VaultWorkspace,
  PatentWorkspace,
  PhotoWorkspace,
} from "./CollectionWorkspaces";
import TradecraftWorkspace from "./TradecraftWorkspace";
import KnowledgeWorkspace from "./KnowledgeWorkspace";
import AutomationWorkspace from "./AutomationWorkspace";
import AutonomousWorkspace from "./AutonomousWorkspace";
import CaseOverview from "./CaseBreakdown";
import DossierVerification from "./DossierVerification";
import AutomaticWorkspace, { isAutomaticView } from "./AutomaticWorkspace";
import LicenceReview from "./LicenceReview";
import ResearchConsole from "./ResearchConsole";
import OnionResearch from "./OnionResearch";
import ArchiveWorkspace from "./ArchiveWorkspace";
import {
  TimelineWorkspace,
  GraphWorkspace,
  ReviewWorkspace,
} from "./Workspaces";
const MapWorkspace = React.lazy(() => import("./MapWorkspace"));
const PdfInspector = React.lazy(() => import("./PdfInspector"));
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createRoot } from "react-dom/client";
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  addEdge,
  MarkerType,
  ReactFlowProvider,
  useReactFlow,
  type Node,
  type Edge,
  type Connection,
} from "@xyflow/react";
import {
  Bot,
  ScanEye,
  Network,
  Files,
  Download,
  Clock3,
  FlaskConical,
  Activity,
  Search,
  Plus,
  ChevronRight,
  ChevronDown,
  PanelRightClose,
  PanelRightOpen,
  Maximize2,
  LayoutGrid,
  Sun,
  Moon,
  Check,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  User,
  Building2,
  Gamepad2,
  Lightbulb,
  StickyNote,
  GitBranch,
  ShieldCheck,
  Play,
  Pause,
  X,
  RotateCcw,
  Upload,
  ArrowUpRight,
  Command,
  Link2,
  MapPin,
  Settings,
  FolderOpen,
  Undo2,
  Redo2,
} from "lucide-react";

import "@fontsource-variable/dm-sans";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource-variable/caveat";
import "@xyflow/react/dist/style.css";
import "./style.css";
type Evidence = {
  id: string;
  title: string;
  kind: string;
  status: string;
  url: string;
  sha256: string | null;
  mime: string;
  size: number;
  created: string;
  text: string;
  fileUrl: string | null;
  previewUrl: string | null;
  metadata: Record<string, any>;
};
type Job = {
  id: string;
  objective: string;
  url: string;
  status: string;
  progress: number;
  error: string | null;
  evidence_id: string | null;
  result: string | null;
  attempts: number;
  created: string;
};
const iconFor = (kind: string) =>
  ({
    person: User,
    organisation: Building2,
    document: FileText,
    photograph: ImageIcon,
    "game asset": Gamepad2,
    patent: FileText,
    hypothesis: Lightbulb,
    note: StickyNote,
    "social post": Command,
    website: Files,
  })[kind] || Files;
const statusColor = (s: string) =>
  s.includes("VERIFIED")
    ? "green"
    : s === "ORIGINAL ACQUIRED"
      ? "blue"
      : s.includes("FAILED") || s === "CONTRADICTED"
        ? "red"
        : s === "HYPOTHESIS"
          ? "purple"
          : "amber";
function EvidenceCard({ data, selected }: any) {
  const e: Evidence | undefined = data.evidence;
  const Icon = iconFor(e?.kind || "document");
  if (!e) return <div className="evidence-card">Loading evidence…</div>;
  return (
    <div
      className={`evidence-card ${e.kind === "note" ? "note-card" : ""} ${selected ? "card-selected" : ""}`}
    >
      <Handle type="target" position={Position.Left} />
      <div className="card-type">
        <Icon size={12} />
        <span>{e.kind.toUpperCase()}</span>
        <span className="card-id">{e.id.slice(-6).toUpperCase()}</span>
      </div>
      {e.previewUrl ? (
        <div
          className={`card-media ${e.kind === "document" ? "paper-media" : ""}`}
        >
          <img src={e.previewUrl} alt={`Original preview: ${e.title}`} />
          <span className="media-chip">
            <ShieldCheck size={10} /> PRESERVED ORIGINAL
          </span>
        </div>
      ) : e.kind === "note" ? (
        <div className="handwriting">{e.text}</div>
      ) : e.fileUrl ? (
        <div className="source-text-preview">
          <span>
            {e.mime === "application/json"
              ? "PRESERVED SOURCE RECORD"
              : "EXTRACTED ORIGINAL CONTENT"}
          </span>
          <pre>
            {e.text.slice(0, 400) ||
              "Original bytes preserved; no text extracted."}
          </pre>
        </div>
      ) : (
        <div className={`text-media ${e.kind}`}>
          <Icon size={e.kind === "person" ? 46 : 36} />
          <span>
            {e.kind === "person"
              ? "Portrait not acquired"
              : e.kind === "organisation"
                ? "INSTITUTIONAL RECORD"
                : e.kind === "hypothesis"
                  ? "A QUESTION TO TEST"
                  : e.kind === "game asset"
                    ? "ORIGINAL BUILD NOT ACQUIRED"
                    : e.kind === "social post"
                      ? "ARCHIVE REQUIRED"
                      : e.kind === "patent"
                        ? "PRIMARY RECORD REQUIRED"
                        : "SECONDARY INVESTIGATIVE NOTE"}
          </span>
          {e.kind === "social post" && <code>1738018409441308955</code>}
        </div>
      )}
      {e.kind !== "note" && (
        <>
          <h3>{e.title}</h3>
          <p>
            {e.text.replace(/\n/g, " ").slice(0, 100)}
            {e.text.length > 100 ? "…" : ""}
          </p>
        </>
      )}
      <div className="card-footer">
        <span className={`status ${statusColor(e.status)}`}>
          <i />
          {e.status}
        </span>
        <ChevronRight size={13} />
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
const nodeTypes = { evidence: EvidenceCard };
const nav = [
  ["board", "Evidence board", Network],
  ["library", "Evidence library", Files],
  ["vault", "Growing database", Files],
  ["knowledge", "Evidence retrieval", Search],
  ["autonomous", "Investigation", Bot],
  ["lab", "Forensic analysis", FlaskConical],
  ["automation", "Automation control", Activity],
  ["patents", "Patent intelligence", FileText],
  ["photos", "Public photo corpus", ImageIcon],
  ["tradecraft", "Tradecraft & hypotheses", ShieldCheck],
  ["queue", "Acquisition queue", Download],
  ["watch", "Continuous watch", RotateCcw],
  ["research", "Sources", Search],
  ["onion", "Onion document browser", ShieldCheck],
  ["timeline", "Chronology", Clock3],
  ["archives", "Archive comparison", GitBranch],
  ["maps", "Geospatial intelligence", MapPin],
  ["review", "Claim review", ShieldCheck],
  ["cipher", "Cipher laboratory", FlaskConical],
  ["graph", "Graph intelligence", GitBranch],
  ["agents", "Investigator", ScanEye],
] as const;
function App() {
  const [evidence, setEvidence] = useState<Evidence[]>([]),
    [jobs, setJobs] = useState<Job[]>([]),
    [activity, setActivity] = useState<any[]>([]),
    [view, setView] = useState("board"),
    [selected, setSelected] = useState<string | null>(null),
    [edgeSelected, setEdgeSelected] = useState<Edge | null>(null),
    [theme, setTheme] = useState(localStorage.getItem("theme") || "dark"),
    [boards, setBoards] = useState<any[]>([]),
    [boardId, setBoardId] = useState("looking-glass"),
    [nodes, setNodes, onNodesChange] = useNodesState<Node>([]),
    [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all"),
    [searchResults, setSearchResults] = useState<any[] | null>(null),
    [drawer, setDrawer] = useState(false),
    [inspector, setInspector] = useState(false),
    [advanced, setAdvanced] = useState(false),
    [inspectorWidth, setInspectorWidth] = useState(
      Number(localStorage.getItem("inspectorWidth")) || 327,
    ),
    [toast, setToast] = useState(""),
    [modal, setModal] = useState(false),
    [saveState, setSaveState] = useState("Saved"),
    [linkDraft, setLinkDraft] = useState<Connection | null>(null),
    [inspectorTab, setInspectorTab] = useState("original"),
    [citationFocus, setCitationFocus] = useState(""),
    [loading, setLoading] = useState(true);
  const flow = useReactFlow();
  const loaded = useRef(false);
  const defaultSelection = useRef(false);
  const undo = useRef<any[]>([]),
    redo = useRef<any[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const saving = useRef(false);
  const notify = (s: string) => {
    setToast(s);
    setTimeout(() => setToast(""), 4500);
  };
  const refresh = useCallback(async () => {
    const brief =
      view === "board" || view === "autonomous" || isAutomaticView(view);
    let [e, j, a] = await Promise.all([
      api(
        brief
          ? view === "board"
            ? "/evidence?summary=true&cards=true"
            : "/evidence?summary=true"
          : "/evidence",
      ),
      api("/jobs"),
      drawer ? api("/activity") : Promise.resolve([]),
    ]);
    if (brief && inspector && selected) {
      const detail = await api("/evidence/" + selected);
      e = e.map((item: any) => (item.id === selected ? detail : item));
    }
    setEvidence(e);
    setJobs(j);
    setActivity(a);
  }, [view, inspector, selected, drawer]);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        await refresh();
      } catch (e: any) {
        if (active) notify(e.message);
      }
      if (active) timer = setTimeout(poll, 15000);
    }
    poll();
    api("/boards")
      .then(setBoards)
      .catch((e) => notify(e.message));
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [refresh]);
  useEffect(() => {
    loaded.current = false;
    setLoading(true);
    api("/boards/" + boardId)
      .then((b) => {
        setNodes(b.nodes);
        setEdges(b.edges);
        setLoading(false);
        setTimeout(() => {
          loaded.current = true;
          flow.fitView({ padding: 0.09 });
        }, 200);
      })
      .catch((e) => notify(e.message));
  }, [boardId]);
  useEffect(() => {
    if (!loaded.current) return;
    setSaveState("Saving…");
    const timer = setTimeout(async () => {
      try {
        saving.current = true;
        await api("/boards/" + boardId, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            nodes: nodes.map(({ data, ...n }) => ({
              ...n,
              data: { evidenceId: data.evidenceId },
            })),
            edges,
          }),
        });
        setSaveState("Saved");
      } catch (e: any) {
        setSaveState("Save failed");
        notify(e.message);
      } finally {
        saving.current = false;
      }
    }, 650);
    return () => clearTimeout(timer);
  }, [nodes, edges, boardId]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);
  const snapshot = () => {
    undo.current.push({
      nodes: structuredClone(nodes),
      edges: structuredClone(edges),
    });
    if (undo.current.length > 40) undo.current.shift();
    redo.current = [];
  };
  const travel = (back: boolean) => {
    const from = back ? undo : redo,
      to = back ? redo : undo;
    const state = from.current.pop();
    if (state) {
      to.current.push({ nodes, edges });
      setNodes(state.nodes);
      setEdges(state.edges);
    }
  };
  useEffect(() => {
    const f = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
      if (
        (e.ctrlKey || e.metaKey) &&
        e.key === "z" &&
        !(e.target instanceof HTMLInputElement) &&
        !(e.target instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        travel(!e.shiftKey);
      }
      if (e.key === "Escape") {
        setModal(false);
        setLinkDraft(null);
        setSearchResults(null);
      }
    };
    window.addEventListener("keydown", f);
    return () => window.removeEventListener("keydown", f);
  }, [nodes, edges]);
  useEffect(() => {
    if (!defaultSelection.current && evidence.length) {
      setSelected(
        evidence.find((e) => e.title.includes("team photograph"))?.id ||
          "NOTE-quantum",
      );
      defaultSelection.current = true;
    }
  }, [evidence]);
  const indexed = useMemo(
    () => Object.fromEntries(evidence.map((e) => [e.id, e])),
    [evidence],
  );
  const displayed = useMemo(
    () =>
      nodes.map((n) => ({
        ...n,
        hidden:
          filter === "originals"
            ? !indexed[String(n.data.evidenceId)]?.fileUrl
            : filter === "hypotheses"
              ? indexed[String(n.data.evidenceId)]?.status !== "HYPOTHESIS"
              : false,
        data: {
          ...n.data,
          evidenceId: n.data.evidenceId,
          evidence: indexed[String(n.data.evidenceId)],
        },
      })),
    [nodes, indexed, filter],
  );
  const coloredEdges = edges.map((e) => {
    const state = e.data?.state;
    const color =
      state === "DOCUMENTED"
        ? "#609fd0"
        : state === "CORROBORATED"
          ? "#61b897"
          : state === "CONTRADICTED"
            ? "#e27870"
            : state === "HYPOTHESIS"
              ? "#b293d6"
              : "#7c8290";
    return {
      ...e,
      label: e.label,
      style: {
        stroke: color,
        strokeWidth: 1.5,
        strokeDasharray: state === "UNVERIFIED" ? "5 5" : undefined,
      },
      labelStyle: {
        fill: color,
        fontSize: 10,
        fontFamily: "IBM Plex Mono, monospace",
      },
      labelBgStyle: {
        fill: theme === "cork" ? "#d4bf9e" : "#171d23",
        fillOpacity: 0.94,
      },
      labelBgPadding: [8, 5] as [number, number],
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 13, height: 13 },
    };
  });
  const acquired = evidence.filter((e) => e.fileUrl);
  const selectedEvidence = selected ? indexed[selected] : null;
  const selectEvidence = (id: string, quote = "") => {
    setCitationFocus(quote);
    setSelected(id);
    setEdgeSelected(null);
    setInspector(true);
    setInspectorTab("original");
  };
  const addToBoard = (id: string) => {
    snapshot();
    if (nodes.some((n) => n.data.evidenceId === id)) {
      notify("This evidence is already on the board");
      return;
    }
    const pos = flow.screenToFlowPosition({
      x: window.innerWidth * 0.5,
      y: window.innerHeight * 0.45,
    });
    setNodes((n) => [
      ...n,
      {
        id: "node-" + id,
        type: "evidence",
        position: pos,
        data: { evidenceId: id },
      },
    ]);
    setView("board");
    selectEvidence(id);
    notify("Evidence placed on board");
  };
  const autoLayout = async () => {
    snapshot();
    const { default: ELK } = await import("elkjs/lib/elk.bundled.js");
    const elk = new ELK();
    const g = await elk.layout({
      id: "root",
      layoutOptions: {
        "elk.algorithm": "layered",
        "elk.spacing.nodeNode": "100",
        "elk.layered.spacing.nodeNodeBetweenLayers": "170",
      },
      children: nodes.map((n) => ({ id: n.id, width: 270, height: 300 })),
      edges: edges.map((e) => ({
        id: e.id,
        sources: [e.source],
        targets: [e.target],
      })),
    });
    setNodes((n) =>
      n.map((x) => ({
        ...x,
        position: {
          x: g.children?.find((c) => c.id === x.id)?.x || 0,
          y: g.children?.find((c) => c.id === x.id)?.y || 0,
        },
      })),
    );
    setTimeout(() => flow.fitView({ padding: 0.15, duration: 500 }), 100);
  };
  const runSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) {
      setSearchResults(null);
      return;
    }
    try {
      setSearchResults(await api("/search?q=" + encodeURIComponent(query)));
    } catch (e: any) {
      notify(e.message);
    }
  };
  return (
    <div
      className={`app-shell ${view === "board" ? "board-with-breakdown" : ""} ${view === "autonomous" ? "investigation-home" : ""} ${["lab", "automation", "knowledge", "patents", "photos", "tradecraft", "research", "onion", "watch", "cipher", "archives", "agents"].includes(view) ? "automatic-tab" : ""}`}
    >
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <ScanEye size={25} />
          </div>
          <div>
            SHERLOCK<span>OSINT INTELLIGENCE SYSTEM</span>
          </div>
        </div>
        <div className="workspace-label">
          WORKSPACE <span>LOCAL</span>
        </div>
        <button
          className="case-box"
          onClick={() => {
            setBoardId("looking-glass");
            setView("board");
          }}
        >
          <div className="case-symbol">
            <FolderOpen size={18} />
          </div>
          <div>
            Project Looking Glass<small>CASE 001 · ACTIVE INVESTIGATION</small>
          </div>
          <ChevronDown size={14} />
        </button>
        <div className="nav-caption">INVESTIGATION</div>
        <nav>
          {nav
            .filter(([id]) =>
              [
                "autonomous",
                "board",
                "library",
                "research",
                "timeline",
              ].includes(id),
            )
            .sort(
              (a, b) =>
                Number(b[0] === "autonomous") - Number(a[0] === "autonomous"),
            )
            .map(([id, label, Icon]) => (
              <button
                key={id}
                className={view === id ? "active" : ""}
                onClick={() => {
                  setView(id);
                  setSearchResults(null);
                }}
              >
                <Icon size={17} />
                <span>{label}</span>
                {id === "library" ? (
                  <b>{evidence.length}</b>
                ) : id === "queue" ? (
                  <b>
                    {
                      jobs.filter(
                        (j) =>
                          ![
                            "COMPLETE",
                            "CANCELLED",
                            "ACQUISITION FAILED",
                            "PROCESSING FAILED",
                          ].includes(j.status),
                      ).length
                    }
                  </b>
                ) : id === "board" ? (
                  <span className="active-dot" />
                ) : null}
              </button>
            ))}
        </nav>
        <button
          className="advanced-nav-toggle"
          onClick={() => setAdvanced(!advanced)}
        >
          Advanced tools <ChevronDown size={13} />
        </button>
        {advanced && (
          <>
            <nav>
              {nav
                .filter(
                  ([id]) =>
                    ![
                      "autonomous",
                      "board",
                      "library",
                      "research",
                      "timeline",
                    ].includes(id),
                )
                .map(([id, label, Icon]) => (
                  <button
                    key={id}
                    className={view === id ? "active" : ""}
                    onClick={() => {
                      setView(id);
                      setSearchResults(null);
                    }}
                  >
                    <Icon size={17} />
                    <span>{label}</span>
                    {id === "library" ? (
                      <b>{evidence.length}</b>
                    ) : id === "queue" ? (
                      <b>
                        {
                          jobs.filter(
                            (j) =>
                              ![
                                "COMPLETE",
                                "CANCELLED",
                                "ACQUISITION FAILED",
                                "PROCESSING FAILED",
                              ].includes(j.status),
                          ).length
                        }
                      </b>
                    ) : id === "board" ? (
                      <span className="active-dot" />
                    ) : null}
                  </button>
                ))}
            </nav>
          </>
        )}
        <details className="advanced-board-list">
          <summary>Case boards</summary>
          <div className="nav-caption board-list-title">
            CASE BOARDS
            <button
              onClick={async () => {
                const name = prompt("Board name");
                if (name) {
                  const b = await post("/boards", { name });
                  setBoards([...boards, b]);
                  setBoardId(b.id);
                  setView("board");
                }
              }}
            >
              <Plus size={14} />
            </button>
          </div>
          <div className="board-list">
            {boards.map((b) => (
              <button
                key={b.id}
                className={boardId === b.id ? "current" : ""}
                onClick={() => {
                  setBoardId(b.id);
                  setView("board");
                }}
              >
                <span />{" "}
                {b.name === "PROJECT LOOKING GLASS"
                  ? "The big picture"
                  : b.name}
              </button>
            ))}
          </div>
        </details>
        <div className="sidebar-bottom">
          <div className="local-status">
            <i />
            Local evidence vault
            <small>
              {acquired.length} originals ·{" "}
              {(acquired.reduce((s, e) => s + e.size, 0) / 1024 / 1024).toFixed(
                1,
              )}{" "}
              MB preserved
            </small>
          </div>
          <button
            className="theme-toggle"
            onClick={() => setTheme(theme === "dark" ? "cork" : "dark")}
          >
            {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}{" "}
            {theme === "dark" ? "Classic corkboard" : "Forensic command centre"}
          </button>
          <div className="profile">
            <span>LG</span>
            <div>
              Local investigator<small>Evidence-first workspace</small>
            </div>
            <ShieldCheck size={16} />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Investigations <ChevronRight size={12} />
            <span>Project Looking Glass</span>
          </div>
          <form className="search-bar" onSubmit={runSearch}>
            <Search size={15} />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search evidence, entities, passages…"
            />
            <kbd>⌘ K</kbd>
          </form>
          <span className="connection">
            <i /> LOCAL SYSTEM
          </span>
          <a
            className="icon-button"
            title="Export case JSON"
            href="/api/export/json"
          >
            <Download size={17} />
          </a>
          <a
            className="button"
            href="/api/export/pdf"
            title="Download evidence audit report as PDF"
          >
            PDF
          </a>
          <a
            className="button"
            href="/api/export/docx"
            title="Download evidence audit report as DOCX"
          >
            DOCX
          </a>
          <button
            className="icon-button"
            title="Toggle inspector"
            onClick={() => setInspector(!inspector)}
          >
            <PanelRightOpen size={17} />
          </button>
        </header>
        <div className="workspace-header">
          <div>
            <div className="eyebrow">
              CASE 001 <span /> OPEN-SOURCE INTELLIGENCE
            </div>
            <h1>{nav.find((n) => n[0] === view)?.[1] || "Evidence board"}</h1>
            <p>
              {view === "board"
                ? "Every connection starts with evidence. Follow the thread."
                : view === "library"
                  ? "Preserved originals and clearly marked investigative notes."
                  : view === "queue"
                    ? "Discover → fetch → hash → preserve → extract → index."
                    : view === "cipher"
                      ? "Reproducible transformations. Controls before conclusions."
                      : view === "timeline"
                        ? "Keep creation, publication, capture and retrieval dates distinct."
                        : view === "watch"
                          ? "Always watching. Scheduled discovery with durable execution history."
                          : view === "agents"
                            ? "Query acquired evidence. Inspect every tool result."
                            : "Inspect the structure. Verify every relationship."}
            </p>
          </div>
          <div className="header-actions">
            <div className="save-indicator">
              <Check size={12} />
              {saveState}
            </div>
            <button className="button primary" onClick={() => setModal(true)}>
              <Plus size={15} /> Acquire evidence
            </button>
          </div>
        </div>
        <div className="stats-bar">
          <span>
            <i className="blue-dot" />
            <strong>{evidence.length}</strong> evidence items
          </span>
          <span>
            <Link2 size={13} />
            <strong>{edges.length}</strong> relationships
          </span>
          <span>
            <ShieldCheck size={13} />
            <strong>{acquired.length}</strong> originals preserved
          </span>
          <span>
            <Lightbulb size={13} />
            <strong>
              {evidence.filter((e) => e.status === "HYPOTHESIS").length}
            </strong>{" "}
            open hypotheses
          </span>
          <span className="stats-right">
            PROJECT LOOKING GLASS <span className="tiny-divider" /> LOCAL-FIRST
          </span>
        </div>
        <div className="workspace-body">
          <main className="content-area">
            <AutomaticWorkspace
              view={searchResults !== null ? "search" : view}
              selectEvidence={selectEvidence}
            >
              {searchResults !== null ? (
                <div className="page-scroll">
                  <div className="section-title">
                    <h2>
                      Search results{" "}
                      <small>{searchResults.length} matching records</small>
                    </h2>
                    <button
                      className="button"
                      onClick={() => setSearchResults(null)}
                    >
                      Return to workspace
                    </button>
                  </div>
                  {searchResults.map((h) => (
                    <button
                      className="search-result"
                      key={h.id}
                      onClick={() => selectEvidence(h.id)}
                    >
                      <span
                        className={`status ${statusColor(h.evidence.status)}`}
                      >
                        {h.evidence.status}
                      </span>
                      <h3>{h.evidence.title}</h3>
                      <p>{h.snippet.replace(/<\/?mark>/g, "")}</p>
                      <small>
                        {h.evidence.url || "Imported secondary note"}
                      </small>
                    </button>
                  ))}
                </div>
              ) : view === "board" ? (
                <div className="board-and-breakdown">
                  <div className="board-toolbar">
                    <div className="segmented">
                      {[
                        ["all", "All evidence"],
                        ["originals", "Originals"],
                        ["hypotheses", "Hypotheses"],
                      ].map(([id, label]) => (
                        <button
                          key={id}
                          className={filter === id ? "chosen" : ""}
                          onClick={() => setFilter(id)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <div className="toolbar-right">
                      <button
                        title="Undo (Ctrl/Cmd Z)"
                        onClick={() => travel(true)}
                      >
                        <Undo2 size={15} />
                      </button>
                      <button title="Redo" onClick={() => travel(false)}>
                        <Redo2 size={15} />
                      </button>
                      <span />
                      <button onClick={autoLayout}>
                        <LayoutGrid size={14} /> Auto layout
                      </button>
                      <button
                        title="Fit board"
                        onClick={() =>
                          flow.fitView({ padding: 0.12, duration: 400 })
                        }
                      >
                        <Maximize2 size={15} />
                      </button>
                      <button
                        title="Presentation mode"
                        onClick={() =>
                          document.fullscreenElement
                            ? document.exitFullscreen()
                            : document.documentElement.requestFullscreen()
                        }
                      >
                        <Play size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="canvas">
                    <ReactFlow
                      nodes={displayed}
                      edges={coloredEdges}
                      onNodesChange={onNodesChange}
                      onEdgesChange={onEdgesChange}
                      nodeTypes={nodeTypes}
                      onNodeDragStart={snapshot}
                      onConnect={(c) => setLinkDraft(c)}
                      onNodeClick={(_, n) =>
                        selectEvidence(String(n.data.evidenceId))
                      }
                      onEdgeClick={(_, e) => {
                        setEdgeSelected(e);
                        setSelected(null);
                        setInspector(true);
                      }}
                      fitView
                      minZoom={0.12}
                      maxZoom={2.5}
                      onlyRenderVisibleElements
                      selectionOnDrag
                      deleteKeyCode={["Backspace", "Delete"]}
                      onNodesDelete={snapshot}
                      onEdgesDelete={snapshot}
                    >
                      <Background
                        variant={BackgroundVariant.Dots}
                        gap={28}
                        size={1}
                        color={theme === "dark" ? "#39414a" : "#9a7952"}
                      />
                      <Controls showInteractive={false} />
                      <MiniMap
                        pannable
                        zoomable
                        nodeColor={(n) =>
                          indexed[String(n.data.evidenceId)]?.fileUrl
                            ? "#619fbb"
                            : "#665e74"
                        }
                        maskColor={theme === "dark" ? "#0e131a99" : "#c4a87866"}
                      />
                    </ReactFlow>
                    {loading && (
                      <div className="canvas-empty">
                        Loading preserved board…
                      </div>
                    )}
                    <div className="canvas-label">
                      <span />{" "}
                      {boardId === "looking-glass"
                        ? "THE BIG PICTURE"
                        : (
                            boards.find((b) => b.id === boardId)?.name ||
                            "EVIDENCE BOARD"
                          ).toUpperCase()}{" "}
                      <small>{nodes.length} cards · drag to investigate</small>
                    </div>
                    <div className="canvas-legend">
                      <span>
                        <i style={{ background: "#609fd0" }} />
                        Documented
                      </span>
                      <span>
                        <i style={{ background: "#61b897" }} />
                        Corroborated
                      </span>
                      <span>
                        <i style={{ background: "#b293d6" }} />
                        Hypothesis
                      </span>
                      <span>
                        <i style={{ background: "#7c8290" }} />
                        Unverified
                      </span>
                    </div>
                  </div>
                  <section
                    className="under-board"
                    aria-label="Case breakdown underneath bulletin board"
                  >
                    <DossierVerification selectEvidence={selectEvidence} />
                    <CaseOverview
                      selectEvidence={selectEvidence}
                      onBoard={(id: string) => {
                        setBoardId(id);
                        setView("board");
                        document
                          .querySelector(".board-and-breakdown")
                          ?.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                    />
                  </section>
                </div>
              ) : view === "library" ? (
                <div className="page-scroll">
                  <div className="section-title">
                    <h2>
                      Evidence vault{" "}
                      <small>{acquired.length} acquired originals</small>
                    </h2>
                    <label className="button">
                      <Upload size={14} /> Import file
                      <input
                        type="file"
                        hidden
                        onChange={async (e) => {
                          if (e.target.files?.[0]) {
                            const form = new FormData();
                            form.append("file", e.target.files[0]);
                            try {
                              const ev = await api("/upload", {
                                method: "POST",
                                body: form,
                              });
                              await refresh();
                              selectEvidence(ev.id);
                              notify("Original imported, hashed and extracted");
                            } catch (ex: any) {
                              notify(ex.message);
                            }
                          }
                        }}
                      />
                    </label>
                  </div>
                  <div className="library-grid">
                    {evidence.map((e) => (
                      <div className="library-card" key={e.id}>
                        <button onClick={() => selectEvidence(e.id)}>
                          {e.previewUrl ? (
                            <img src={e.previewUrl} alt={e.title} />
                          ) : (
                            <div className="library-placeholder">
                              {React.createElement(iconFor(e.kind), {
                                size: 32,
                              })}
                              <span>
                                {e.fileUrl
                                  ? "Original stored"
                                  : "No original acquired"}
                              </span>
                            </div>
                          )}
                          <span className={`status ${statusColor(e.status)}`}>
                            {e.status}
                          </span>
                          <h3>{e.title}</h3>
                          <p>
                            {e.id} ·{" "}
                            {e.fileUrl
                              ? (e.size / 1024).toFixed(1) + " KB"
                              : "Secondary note"}
                          </p>
                        </button>
                        <button
                          className="library-add"
                          onClick={() => addToBoard(e.id)}
                        >
                          <Plus size={12} /> Place on board
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              ) : view === "queue" ? (
                <div className="page-scroll">
                  <div className="section-title">
                    <h2>
                      Acquisition jobs <small>Persistent across restarts</small>
                    </h2>
                    <button className="button" onClick={() => setModal(true)}>
                      <Plus size={14} /> New acquisition
                    </button>
                  </div>
                  {jobs.length ? (
                    jobs.map((j) => (
                      <div className="job-card" key={j.id}>
                        <div className="job-icon">
                          <Download size={18} />
                        </div>
                        <div className="job-main">
                          <div className="job-heading">
                            <h3>{j.objective}</h3>
                            <span className={`status ${statusColor(j.status)}`}>
                              {j.status}
                            </span>
                          </div>
                          <p>
                            {j.url || "Local evidence audit"} · {j.id}
                          </p>
                          <div className="progress-track">
                            <div style={{ width: j.progress + "%" }} />
                          </div>
                          {j.error && (
                            <div className="error-text">
                              NOT ACQUIRED / processing incomplete: {j.error}
                            </div>
                          )}
                          <small>
                            {j.progress}% · {j.attempts} attempt(s) ·{" "}
                            {new Date(j.created).toLocaleString()}
                          </small>
                        </div>
                        <div className="job-controls">
                          {j.evidence_id && (
                            <button
                              className="button"
                              onClick={() => selectEvidence(j.evidence_id!)}
                            >
                              Inspect original
                            </button>
                          )}
                          {j.status !== "COMPLETE" && (
                            <>
                              {[
                                "PAUSED",
                                "ACQUISITION FAILED",
                                "PROCESSING FAILED",
                                "CANCELLED",
                              ].includes(j.status) ? (
                                <button
                                  title="Retry / resume"
                                  onClick={() =>
                                    post("/jobs/" + j.id + "/resume", {}).then(
                                      refresh,
                                    )
                                  }
                                >
                                  <Play size={15} />
                                </button>
                              ) : (
                                <button
                                  title="Pause at next checkpoint"
                                  onClick={() =>
                                    post("/jobs/" + j.id + "/pause", {}).then(
                                      refresh,
                                    )
                                  }
                                >
                                  <Pause size={15} />
                                </button>
                              )}
                              <button
                                title="Cancel"
                                onClick={() =>
                                  post("/jobs/" + j.id + "/cancel", {}).then(
                                    refresh,
                                  )
                                }
                              >
                                <X size={15} />
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <Empty
                      Icon={Download}
                      title="Start with an original source"
                      text="Queue a public PDF, image or webpage. Original bytes, hash and acquisition history will be preserved."
                    />
                  )}
                </div>
              ) : view === "autonomous" ? (
                <CaseOverview
                  notify={notify}
                  selectEvidence={selectEvidence}
                  onBoard={(id: string) => {
                    setBoardId(id);
                    setView("board");
                  }}
                />
              ) : view === "lab" ? (
                <AutonomousWorkspace
                  evidence={evidence}
                  notify={notify}
                  selectEvidence={selectEvidence}
                />
              ) : view === "automation" ? (
                <AutomationWorkspace
                  evidence={evidence}
                  selectEvidence={selectEvidence}
                  notify={notify}
                />
              ) : view === "knowledge" ? (
                <KnowledgeWorkspace
                  selectEvidence={selectEvidence}
                  notify={notify}
                />
              ) : view === "vault" ? (
                <VaultWorkspace
                  selectEvidence={selectEvidence}
                  notify={notify}
                />
              ) : view === "patents" ? (
                <PatentWorkspace
                  selectEvidence={selectEvidence}
                  notify={notify}
                />
              ) : view === "photos" ? (
                <PhotoWorkspace
                  selectEvidence={selectEvidence}
                  notify={notify}
                />
              ) : view === "tradecraft" ? (
                <TradecraftWorkspace
                  evidence={evidence}
                  selectEvidence={selectEvidence}
                  notify={notify}
                  boards={boards}
                  onPin={async (id: string) => {
                    loaded.current = false;
                    await refresh();
                    setBoardId(id);
                    const b = await api(`/boards/${id}`);
                    setNodes(b.nodes);
                    setEdges(b.edges);
                    setView("board");
                    setTimeout(() => {
                      loaded.current = true;
                      flow.fitView({ padding: 0.09 });
                    }, 200);
                  }}
                />
              ) : view === "research" ? (
                <ResearchConsole
                  notify={notify}
                  selectEvidence={selectEvidence}
                  onBoard={async (id) => {
                    setBoards(await api("/boards"));
                    setBoardId(id);
                    setView("board");
                  }}
                />
              ) : view === "onion" ? (
                <OnionResearch
                  evidence={evidence}
                  notify={notify}
                  selectEvidence={selectEvidence}
                />
              ) : view === "watch" ? (
                <ContinuousWatch notify={notify} />
              ) : view === "cipher" ? (
                <CipherWorkbench evidence={evidence} notify={notify} />
              ) : view === "timeline" ? (
                <TimelineWorkspace
                  evidence={evidence}
                  selectEvidence={selectEvidence}
                  notify={notify}
                />
              ) : view === "archives" ? (
                <ArchiveWorkspace
                  evidence={evidence}
                  selectEvidence={selectEvidence}
                  notify={notify}
                />
              ) : view === "maps" ? (
                <React.Suspense
                  fallback={
                    <div className="page-scroll">
                      Loading geospatial workspace…
                    </div>
                  }
                >
                  <MapWorkspace
                    evidence={evidence}
                    selectEvidence={selectEvidence}
                    notify={notify}
                  />
                </React.Suspense>
              ) : view === "review" ? (
                <ReviewWorkspace
                  boardId={boardId}
                  evidence={evidence}
                  selectEvidence={selectEvidence}
                  notify={notify}
                  onReviewed={async () => {
                    const b = await api(`/boards/${boardId}`);
                    setNodes(b.nodes);
                    setEdges(b.edges);
                    refresh();
                  }}
                />
              ) : view === "agents" ? (
                <Investigator
                  notify={notify}
                  onAttached={async () => {
                    const updated = await api("/boards/looking-glass");
                    await refresh();
                    setBoardId("looking-glass");
                    setNodes(updated.nodes);
                    setEdges(updated.edges);
                    setView("board");
                  }}
                />
              ) : (
                <GraphWorkspace
                  onRelationship={(edge) => {
                    setSelected(null);
                    setEdgeSelected(edge);
                    setInspector(true);
                  }}
                  boardId={boardId}
                  selectEvidence={selectEvidence}
                  notify={notify}
                />
              )}
            </AutomaticWorkspace>
          </main>
          {inspector && (
            <aside className="inspector" style={{ width: inspectorWidth }}>
              <div
                className="inspector-resize-handle"
                role="separator"
                aria-label="Resize evidence inspector"
                aria-orientation="vertical"
                tabIndex={0}
                onPointerDown={(e) =>
                  e.currentTarget.setPointerCapture(e.pointerId)
                }
                onPointerMove={(e) => {
                  if (e.currentTarget.hasPointerCapture(e.pointerId)) {
                    const w = Math.max(
                      300,
                      Math.min(
                        800,
                        window.innerWidth * 0.65,
                        window.innerWidth - e.clientX,
                      ),
                    );
                    setInspectorWidth(w);
                    localStorage.setItem("inspectorWidth", String(w));
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
                    e.preventDefault();
                    const w = Math.max(
                      300,
                      Math.min(
                        800,
                        inspectorWidth + (e.key === "ArrowLeft" ? 30 : -30),
                      ),
                    );
                    setInspectorWidth(w);
                    localStorage.setItem("inspectorWidth", String(w));
                  }
                }}
              />

              <div className="inspector-heading">
                <span>
                  <ScanEye size={15} /> EVIDENCE INSPECTOR
                </span>
                <button
                  onClick={() => setInspector(false)}
                  title="Close inspector"
                >
                  <PanelRightClose size={17} />
                </button>
              </div>
              {edgeSelected ? (
                <div className="inspector-scroll">
                  <span className="eyebrow">RELATIONSHIP RECORD</span>
                  <h2>
                    {String(edgeSelected.data?.claim || edgeSelected.label)}
                  </h2>
                  <span className="status amber">
                    {String(edgeSelected.data?.state)}
                  </span>
                  <div className="notice">
                    {String(
                      edgeSelected.data?.reason ||
                        "Manually proposed relationship",
                    )}
                  </div>
                  <dl>
                    <dt>Confidence</dt>
                    <dd>
                      {String(edgeSelected.data?.confidence || "Unassessed")}
                    </dd>
                    <dt>Proposed by</dt>
                    <dd>
                      {String(
                        edgeSelected.data?.method || "Human investigator",
                      )}
                    </dd>
                    <dt>Supporting originals</dt>
                    <dd>
                      {(edgeSelected.data?.evidence as any[])?.length || 0}
                    </dd>
                  </dl>
                  {((edgeSelected.data?.evidence as any[]) || []).map((c) => (
                    <button
                      className="citation"
                      key={c.id}
                      onClick={() => selectEvidence(c.id, c.quote)}
                    >
                      <FileText size={15} />
                      <strong>{indexed[c.id]?.title}</strong>
                      <p>“{c.quote}”</p>
                      <small>{c.location || "Extracted document text"}</small>
                    </button>
                  ))}
                  <h4>Contradicting evidence</h4>
                  <p className="muted">
                    {(edgeSelected.data?.contradictions as any[])?.length
                      ? JSON.stringify(edgeSelected.data?.contradictions)
                      : "None recorded. This does not establish the claim."}
                  </p>
                </div>
              ) : selectedEvidence ? (
                <>
                  <div className="inspector-title">
                    <div className="inspector-kind">
                      {React.createElement(iconFor(selectedEvidence.kind), {
                        size: 16,
                      })}
                      {selectedEvidence.kind.toUpperCase()}
                    </div>
                    <h2>{selectedEvidence.title}</h2>
                    <span
                      className={`status ${statusColor(selectedEvidence.status)}`}
                    >
                      <i />
                      {selectedEvidence.status}
                    </span>
                  </div>
                  <div className="inspector-tabs">
                    {["original", "provenance", "extraction"].map((t) => (
                      <button
                        key={t}
                        className={inspectorTab === t ? "active" : ""}
                        onClick={() => setInspectorTab(t)}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                  <div className="inspector-scroll">
                    {inspectorTab === "original" ? (
                      <>
                        {selectedEvidence.fileUrl ? (
                          selectedEvidence.mime === "application/pdf" ? (
                            <React.Suspense
                              fallback={
                                <div className="notice">
                                  Loading preserved PDF…
                                </div>
                              }
                            >
                              <PdfInspector
                                evidence={selectedEvidence}
                                focus={citationFocus}
                              />
                            </React.Suspense>
                          ) : selectedEvidence.mime.startsWith("video/") ? (
                            <video
                              className="inspector-video"
                              controls
                              src={selectedEvidence.fileUrl}
                            />
                          ) : selectedEvidence.mime.startsWith("audio/") ? (
                            <audio controls src={selectedEvidence.fileUrl} />
                          ) : selectedEvidence.mime.startsWith("image/") ? (
                            <a
                              href={selectedEvidence.fileUrl}
                              target="_blank"
                              rel="noreferrer"
                            >
                              <img
                                className="inspector-image"
                                src={selectedEvidence.fileUrl}
                                alt={selectedEvidence.title}
                              />
                            </a>
                          ) : (
                            <div className="original-text">
                              {selectedEvidence.text.slice(0, 4000)}
                            </div>
                          )
                        ) : (
                          <div className="not-acquired">
                            <ShieldCheck size={28} />
                            <strong>No original acquired</strong>
                            <p>
                              This is a secondary note or model proposal. It
                              cannot authenticate the underlying claim.
                            </p>
                          </div>
                        )}
                        {selectedEvidence.fileUrl && (
                          <div className="inspector-action-row">
                            <a
                              className="button"
                              href={selectedEvidence.fileUrl}
                              target="_blank"
                              rel="noreferrer"
                            >
                              <ExternalLink size={12} /> Open original
                            </a>
                            <button
                              className="button"
                              onClick={() => addToBoard(selectedEvidence.id)}
                            >
                              <Plus size={12} /> Board
                            </button>
                          </div>
                        )}
                        {(selectedEvidence.metadata.citations || []).map(
                          (c: any) => (
                            <button
                              className="citation"
                              key={c.id}
                              onClick={() => selectEvidence(c.id, c.quote)}
                            >
                              <FileText size={14} />
                              <strong>Inspect supporting original</strong>
                              <p>“{c.quote}”</p>
                              <small>{c.location}</small>
                            </button>
                          ),
                        )}
                        <h4>
                          {selectedEvidence.fileUrl
                            ? "Source record"
                            : "Investigative note"}
                        </h4>
                        <p className="body-text">
                          {selectedEvidence.fileUrl
                            ? selectedEvidence.text.slice(0, 700) ||
                              "No textual content extracted. See original media."
                            : selectedEvidence.text}
                        </p>
                        {selectedEvidence.url && (
                          <a
                            className="source-link"
                            href={selectedEvidence.url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <ExternalLink size={12} />
                            {selectedEvidence.metadata.source_publisher ||
                              "Original source"}
                            <ArrowUpRight size={13} />
                          </a>
                        )}
                        <div className="review-note">
                          <ShieldCheck size={16} />
                          <div>
                            <strong>Evidence discipline</strong>
                            <p>
                              {selectedEvidence.fileUrl
                                ? "Byte integrity verified. This does not independently verify every statement in the source."
                                : "No inference, identity or relationship is verified by this note."}
                            </p>
                          </div>
                        </div>
                      </>
                    ) : inspectorTab === "provenance" ? (
                      <>
                        {selectedEvidence.fileUrl && (
                          <LicenceReview
                            key={selectedEvidence.id}
                            evidence={selectedEvidence}
                            notify={notify}
                            refresh={refresh}
                          />
                        )}
                        <h4>Chain of custody</h4>
                        <dl>
                          {[
                            ["Evidence ID", selectedEvidence.id],
                            ["Acquisition status", selectedEvidence.status],
                            [
                              "Source",
                              selectedEvidence.metadata.original_url ||
                                selectedEvidence.metadata.source,
                            ],
                            [
                              "Retrieved (UTC)",
                              selectedEvidence.metadata.retrieved_utc ||
                                selectedEvidence.created,
                            ],
                            [
                              "Publication date",
                              selectedEvidence.metadata.publication_date ||
                                "Not independently known",
                            ],
                            [
                              "Final URL",
                              selectedEvidence.metadata.final_url ||
                                "Not acquired",
                            ],
                            ["MIME type", selectedEvidence.mime],
                            [
                              "Byte size",
                              selectedEvidence.size.toLocaleString(),
                            ],
                            [
                              "Retrieval method",
                              selectedEvidence.metadata.retrieval_method ||
                                "Imported secondary note",
                            ],
                            [
                              "Licence",
                              selectedEvidence.metadata.licence || "Unknown",
                            ],
                          ].map(([k, v]) => (
                            <React.Fragment key={k}>
                              <dt>{k}</dt>
                              <dd>{v}</dd>
                            </React.Fragment>
                          ))}
                        </dl>
                        <h4>SHA-256</h4>
                        <code className="hash">
                          {selectedEvidence.sha256 ||
                            "No original file to hash"}
                        </code>
                        <h4>Transformations</h4>
                        <pre>
                          {JSON.stringify(
                            selectedEvidence.metadata.transformations || [],
                            null,
                            2,
                          )}
                        </pre>
                        <h4>HTTP & original metadata</h4>
                        <pre>
                          {JSON.stringify(selectedEvidence.metadata, null, 2)}
                        </pre>
                      </>
                    ) : (
                      <>
                        <h4>Isolated processing</h4>
                        <span
                          className={
                            "status " +
                            (selectedEvidence.metadata.sandbox
                              ? "green"
                              : "amber")
                          }
                        >
                          {selectedEvidence.metadata.sandbox
                            ? "NETWORK DISABLED · READ-ONLY ORIGINAL"
                            : "NOT YET SANDBOX PROCESSED"}
                        </span>
                        {selectedEvidence.metadata.processing_failure && (
                          <p className="error-text">
                            {selectedEvidence.metadata.processing_failure}
                          </p>
                        )}
                        <button
                          className="button process-button"
                          disabled={!selectedEvidence.fileUrl}
                          onClick={async () => {
                            notify("Processing in a disposable container…");
                            try {
                              await post(
                                "/evidence/" + selectedEvidence.id + "/process",
                                {},
                              );
                              await refresh();
                              notify(
                                "Isolated processing complete; original hash reverified",
                              );
                            } catch (e: any) {
                              notify(e.message);
                            }
                          }}
                        >
                          <ShieldCheck size={13} />
                          Process safely
                        </button>
                        <h4>Search extracted text</h4>
                        <input
                          className="field"
                          placeholder="Find passage…"
                          onChange={(e) => {
                            const text =
                              document.getElementById("extracted-text");
                            if (text) {
                              const pos = selectedEvidence.text
                                .toLowerCase()
                                .indexOf(e.target.value.toLowerCase());
                              text.scrollTop = Math.max(0, (pos / 80) * 18);
                            }
                          }}
                        />
                        <pre id="extracted-text" className="extracted-text">
                          {selectedEvidence.text ||
                            "No extracted text available"}
                        </pre>
                        {selectedEvidence.metadata.dimensions && (
                          <>
                            <h4>Image analysis</h4>
                            <dl>
                              <dt>Dimensions</dt>
                              <dd>
                                {selectedEvidence.metadata.dimensions.join(
                                  " × ",
                                )}
                              </dd>
                              <dt>Average hash</dt>
                              <dd>{selectedEvidence.metadata.average_hash}</dd>
                              <dt>EXIF</dt>
                              <dd>
                                {JSON.stringify(selectedEvidence.metadata.exif)}
                              </dd>
                            </dl>
                          </>
                        )}
                        <p className="muted">
                          Extraction is a derivative; the original file remains
                          unchanged.
                        </p>
                      </>
                    )}
                  </div>
                  <div className="inspector-bottom">
                    <span className="eyebrow">{selectedEvidence.id}</span>
                    <span>
                      {selectedEvidence.fileUrl
                        ? "LOCAL ORIGINAL"
                        : "SECONDARY NOTE"}
                    </span>
                  </div>
                </>
              ) : (
                <Empty
                  Icon={ScanEye}
                  title="Inspect the evidence"
                  text="Select a card or relationship to view its source and provenance."
                />
              )}
            </aside>
          )}
        </div>
        {(advanced || drawer) && (
          <div className={`execution-drawer ${drawer ? "expanded" : ""}`}>
            <button
              className="drawer-heading"
              onClick={() => setDrawer(!drawer)}
            >
              <Activity size={14} />
              <strong>Execution log</strong>
              <span className="live-dot" />
              <span>LIVE</span>
              <small>
                {jobs.filter((j) => j.status === "COMPLETE").length} completed ·{" "}
                {jobs.filter((j) => j.status === "ACQUISITION FAILED").length}{" "}
                failed
              </small>
              <ChevronDown
                size={15}
                style={{ transform: drawer ? "none" : "rotate(180deg)" }}
              />
            </button>
            {drawer && (
              <div className="log-lines">
                {activity.slice(0, 3).map((a) => (
                  <div key={a.id}>
                    <time>{a.time.slice(11, 19)}</time>
                    <span
                      className={
                        a.action.includes("failed") ? "red" : "log-tag"
                      }
                    >
                      {a.action.replace(/_/g, " ").toUpperCase()}
                    </span>
                    <p>
                      {JSON.parse(a.detail).id ||
                        JSON.parse(a.detail).url ||
                        "Case state updated"}{" "}
                      {JSON.parse(a.detail).error || ""}
                    </p>
                    <Check size={12} />
                  </div>
                ))}
                {!activity.length && (
                  <div>
                    <time>—</time>
                    <span className="log-tag">VAULT READY</span>
                    <p>Waiting for an original evidence acquisition.</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        <footer className="app-footer">
          <span>
            <ShieldCheck size={11} /> Original files are immutable. Inferences
            are reviewable.
          </span>
          <span>
            SHERLOCK OSINT v0.13 <span> · </span> PROJECT LOOKING GLASS
          </span>
        </footer>
      </div>
      {toast && (
        <div className="toast">
          <ShieldCheck size={16} />
          {toast}
        </div>
      )}
      {modal && (
        <AcquireModal
          close={() => setModal(false)}
          notify={notify}
          refresh={refresh}
        />
      )}{" "}
      {linkDraft && (
        <RelationshipModal
          connection={linkDraft}
          evidence={evidence}
          close={() => setLinkDraft(null)}
          save={(data: any) => {
            snapshot();
            setEdges((e) =>
              addEdge(
                {
                  ...linkDraft,
                  id: "rel-" + Date.now(),
                  label: data.claim + " · " + data.state.toLowerCase(),
                  type: "smoothstep",
                  data,
                },
                e,
              ),
            );
            setLinkDraft(null);
            notify("Relationship recorded with provenance");
          }}
        />
      )}
    </div>
  );
}
function Empty({ Icon, title, text }: any) {
  return (
    <div className="empty-state">
      <Icon size={34} />
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
function AcquireModal({ close, notify, refresh }: any) {
  const [url, setUrl] = useState(""),
    [title, setTitle] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="modal-overlay">
      <form
        className="modal"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await post("/jobs", { url, title });
            await refresh();
            notify("Acquisition queued. Inspect progress in the queue.");
            close();
          } catch (e: any) {
            notify(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="modal-heading">
          <Download size={22} />
          <button type="button" onClick={close}>
            <X size={19} />
          </button>
        </div>
        <span className="eyebrow">ORIGINAL-SOURCE ACQUISITION</span>
        <h2>Bring evidence into the vault.</h2>
        <p>
          Public HTTP(S) only. Site access policies are checked. Files up to 25
          MB are preserved read-only and hashed.
        </p>
        <label>
          Evidence title
          <input
            className="field"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="A descriptive source title"
          />
        </label>
        <label>
          Original source URL
          <input
            className="field"
            type="url"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://institution.edu/original.pdf"
          />
        </label>
        <div className="notice">
          <ShieldCheck size={17} />A failed download stays visible. An AI
          summary will never replace an unavailable original.
        </div>
        <button className="button primary" disabled={busy}>
          {busy ? "Queuing…" : "Queue acquisition"}
          <ArrowUpRight size={15} />
        </button>
      </form>
    </div>
  );
}
function RelationshipModal({ connection, evidence, close, save }: any) {
  const [claim, setClaim] = useState(""),
    [state, setState] = useState("UNVERIFIED"),
    [source, setSource] = useState(""),
    [quote, setQuote] = useState(""),
    [location, setLocation] = useState("");
  const ev = evidence.find((e: Evidence) => e.id === source);
  return (
    <div className="modal-overlay">
      <form
        className="modal"
        onSubmit={(e) => {
          e.preventDefault();
          if (
            state === "DOCUMENTED" &&
            (!ev || !quote || !ev.text.includes(quote))
          )
            return;
          save({
            claim,
            state,
            confidence:
              state === "DOCUMENTED"
                ? "Source-supported, pending independent review"
                : "Unassessed",
            method: "Human investigator",
            reason: "Manually linked on evidence board",
            evidence: source && quote ? [{ id: source, quote, location }] : [],
            contradictions: [],
          });
        }}
      >
        <div className="modal-heading">
          <Link2 size={22} />
          <button type="button" onClick={close}>
            <X size={19} />
          </button>
        </div>
        <h2>Make the connection inspectable.</h2>
        <p>
          {connection.source} → {connection.target}
        </p>
        <label>
          Exact relationship claim
          <input
            className="field"
            required
            value={claim}
            onChange={(e) => setClaim(e.target.value)}
          />
        </label>
        <label>
          Evidence state
          <select
            className="field"
            value={state}
            onChange={(e) => setState(e.target.value)}
          >
            <option>UNVERIFIED</option>
            <option>HYPOTHESIS</option>
            <option>DOCUMENTED</option>
            <option>CONTRADICTED</option>
          </select>
        </label>
        <label>
          Supporting acquired original
          <select
            className="field"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            <option value="">No acquired citation</option>
            {evidence
              .filter((e: Evidence) => e.fileUrl)
              .map((e: Evidence) => (
                <option key={e.id} value={e.id}>
                  {e.title}
                </option>
              ))}
          </select>
        </label>
        <label>
          Exact supporting passage
          <textarea
            className="field"
            value={quote}
            onChange={(e) => setQuote(e.target.value)}
          />
        </label>
        <label>
          Page / paragraph / location
          <input
            className="field"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
        </label>
        {state === "DOCUMENTED" && (!quote || !ev?.text.includes(quote)) && (
          <p className="error-text">
            Documented edges require a passage matching an acquired original.
          </p>
        )}
        <button className="button primary">Save relationship</button>
      </form>
    </div>
  );
}
function ContinuousWatch({ notify }: any) {
  const [data, setData] = useState<any>({
      watches: [],
      runs: [],
      discovery: [],
    }),
    [name, setName] = useState(""),
    [target, setTarget] = useState(""),
    [mode, setMode] = useState("crossref"),
    [interval, setIntervalMinutes] = useState(60),
    [cron, setCron] = useState("");
  const refresh = () => api("/watches").then(setData);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="page-scroll">
      <div className="section-title">
        <h2>
          Continuous discovery{" "}
          <small>
            Built-in cron-style scheduler · persisted in the case database
          </small>
        </h2>
        <span className="status green">BACKGROUND WORKER</span>
      </div>
      <div className="notice">
        <RotateCcw size={18} />
        Watches run while the backend service is running. Missed intervals
        resume once after restart. Crossref searches discover recent
        publications; RSS feeds discover new source links; URL watches preserve
        changed versions. No login or model credential required.
      </div>
      <form
        className="cipher-form"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await post("/watches", {
              name,
              mode,
              target,
              interval_minutes: interval,
              cron_expression: cron,
            });
            setName("");
            setTarget("");
            await refresh();
            notify("Continuous watch enabled; first run is due now");
          } catch (e: any) {
            notify(e.message);
          }
        }}
      >
        <div className="two-col">
          <label>
            Watch name
            <input
              className="field"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Advanced propulsion literature"
            />
          </label>
          <label>
            Discovery source
            <select
              className="field"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
            >
              <option value="crossref">Crossref · publication search</option>
              <option value="rss">RSS / Atom · new records</option>
              <option value="nasa">NASA NTRS · public report originals</option>
              <option value="archive">
                Internet Archive · historical captures
              </option>
              <option value="url">Public URL · version monitoring</option>
            </select>
          </label>
        </div>
        <div className="two-col">
          <label>
            {["crossref", "nasa"].includes(mode)
              ? "Search terms"
              : "Public source / feed URL"}
            <input
              className="field"
              required
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder={
                ["crossref", "nasa"].includes(mode)
                  ? "superalloy"
                  : "https://institution.edu/feed.xml"
              }
            />
          </label>
          <label>
            Repeat every (minutes, minimum 5)
            <input
              className="field"
              type="number"
              min={5}
              max={525600}
              value={interval}
              onChange={(e) => setIntervalMinutes(Number(e.target.value))}
            />
          </label>
        </div>
        <label>
          Optional cron expression · UTC (overrides interval)
          <input
            className="field code-input"
            value={cron}
            onChange={(e) => setCron(e.target.value)}
            placeholder="0 */6 * * *"
          />
          <small>
            Five fields: minute hour day month weekday. Leave empty to use the
            interval.
          </small>
        </label>
        <button className="button primary">
          <Plus size={14} /> Enable continuous watch
        </button>
      </form>
      <h3 className="history-title">
        Active watches{" "}
        <small>
          {data.watches.filter((w: any) => w.enabled).length} enabled
        </small>
      </h3>
      {data.watches.map((w: any) => (
        <div className="job-card" key={w.id}>
          <div className="job-icon">
            <RotateCcw size={17} />
          </div>
          <div className="job-main">
            <div className="job-heading">
              <h3>{w.name}</h3>
              <span className={"status " + (w.enabled ? "green" : "amber")}>
                {w.enabled ? "WATCHING" : "PAUSED"}
              </span>
            </div>
            <p>
              {w.mode.toUpperCase()} · {w.target}
            </p>
            <small>
              {w.cron_expression
                ? `Cron ${w.cron_expression} UTC`
                : `Every ${w.interval_minutes} min`}{" "}
              · {w.runs} runs · Next:{" "}
              {w.enabled
                ? new Date(w.next_run * 1000).toLocaleString()
                : "paused"}
            </small>
            {w.last_error && <p className="error-text">{w.last_error}</p>}
          </div>
          <div className="job-controls">
            <button
              title={w.enabled ? "Pause watch" : "Resume watch"}
              onClick={() =>
                post(
                  "/watches/" + w.id + "/" + (w.enabled ? "pause" : "resume"),
                  {},
                ).then(refresh)
              }
            >
              {w.enabled ? <Pause size={15} /> : <Play size={15} />}
            </button>
            <button
              className="button"
              onClick={() =>
                post("/watches/" + w.id + "/run", {}).then(refresh)
              }
            >
              Run now
            </button>
            <button
              title="Remove watch"
              onClick={() =>
                post("/watches/" + w.id + "/delete", {}).then(refresh)
              }
            >
              <X size={14} />
            </button>
          </div>
        </div>
      ))}
      <h3 className="history-title">Automatic evidence audits</h3>
      {(data.analyses || []).map((a: any) => (
        <div className="experiment-history" key={a.job_id}>
          <ShieldCheck size={15} />
          <span>
            {a.job_id}
            <small>{a.run_id || a.error || "Preparing audit"}</small>
          </span>
          <span className="status blue">{a.status}</span>
        </div>
      ))}
      <h3 className="history-title">Discovery runs</h3>
      {data.runs.map((r: any) => (
        <div key={r.id} className="experiment-history">
          <Clock3 size={15} />
          <span>
            {new Date(r.started).toLocaleString()}
            <small>{r.watch_id}</small>
          </span>
          <code>
            {r.discovered} found · {r.queued} queued
            {r.error ? " · " + r.error : ""}
          </code>
          <span
            className={"status " + (r.status === "FAILED" ? "red" : "green")}
          >
            {r.status}
          </span>
        </div>
      ))}
      {!data.watches.length && (
        <Empty
          Icon={RotateCcw}
          title="Keep the investigation moving"
          text="Create a watch above. Every discovery run and acquisition failure stays inspectable."
        />
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <ReactFlowProvider>
    <App />
  </ReactFlowProvider>,
);

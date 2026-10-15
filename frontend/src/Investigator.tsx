import { useEffect, useState } from "react";
import {
  ScanEye,
  Play,
  Pause,
  X,
  Check,
  ChevronDown,
  ExternalLink,
} from "lucide-react";
import { api, post } from "./api";
export default function Investigator({
  notify,
  onAttached,
}: {
  notify: (message: string) => void;
  onAttached: () => Promise<void>;
}) {
  const [question, setQuestion] = useState(
    "What do the acquired patent records say about inventors Monica Jacinto and Dallis Hardwick?",
  );
  const [runs, setRuns] = useState<any[]>([]),
    [selectedId, setSelectedId] = useState(""),
    [busy, setBusy] = useState(false),
    [models, setModels] = useState<any>(null),
    [provider, setProvider] = useState("deterministic"),
    [model, setModel] = useState("");
  const refresh = () => api("/investigations").then(setRuns);
  useEffect(() => {
    refresh().catch((e) => notify(e.message));
    api("/models")
      .then(setModels)
      .catch((e) => notify(e.message));
    const timer = setInterval(() => refresh().catch(() => {}), 2000);
    return () => clearInterval(timer);
  }, []);
  const run = runs.find((r) => r.id === selectedId) || runs[0],
    result = run?.result;
  const control = async (action: string) => {
    try {
      await post("/investigations/" + run.id + "/" + action, {});
      await refresh();
    } catch (e: any) {
      notify(e.message);
    }
  };
  return (
    <div className="page-scroll">
      <div className="section-title">
        <h2>
          Investigation control
          <small>
            Persistent tasks · exact source passages · independent provenance
            checks
          </small>
        </h2>
        <span className="status blue">CHECKPOINTED WORKFLOW</span>
      </div>
      <div className="notice">
        <ScanEye size={18} />
        Seven named stages operate on acquired originals with attested text.
        Deterministic tasks verify provenance and locate passages. Model
        proposals require a configured provider and human review; agents cannot
        execute host commands or create factual edges.
      </div>
      <form
        className="investigator-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const created = await post("/investigations", {
              question,
              provider,
              model,
            });
            setSelectedId(created.id);
            await refresh();
            notify("Investigation queued; checkpoints persist across restarts");
          } catch (e: any) {
            notify(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Investigative objective
          <textarea
            className="field"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            required
          />
        </label>
        <div className="two-col model-controls">
          <label>
            Analyst mode
            <select
              className="field"
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value);
                setModel(
                  e.target.value === "ollama"
                    ? models?.ollama.models[0] || ""
                    : models?.anthropic.model || "",
                );
              }}
            >
              <option value="deterministic">
                Deterministic retrieval & audit
              </option>
              <option value="ollama" disabled={!models?.ollama.ready}>
                Local Ollama {models?.ollama.ready ? "" : "· not running"}
              </option>
              <option value="anthropic" disabled={!models?.anthropic.ready}>
                Claude API{" "}
                {models?.anthropic.ready ? "" : "· credentials absent"}
              </option>
            </select>
          </label>
          <label>
            Model
            {provider === "ollama" ? (
              <select
                className="field"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              >
                {models?.ollama.models.map((m: string) => (
                  <option key={m}>{m}</option>
                ))}
              </select>
            ) : (
              <input
                className="field"
                value={model}
                disabled={provider === "deterministic"}
                onChange={(e) => setModel(e.target.value)}
                placeholder={
                  provider === "deterministic"
                    ? "No model used"
                    : "Configured model name"
                }
              />
            )}
          </label>
        </div>
        <button className="button primary" disabled={busy}>
          <Play size={14} />
          {busy ? "Queuing…" : "Start investigation"}
        </button>
      </form>
      {runs.length > 0 && (
        <div className="run-selector">
          <label>
            Saved investigations
            <select
              className="field"
              value={run?.id || ""}
              onChange={(e) => setSelectedId(e.target.value)}
            >
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.status} · {r.question.slice(0, 100)}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      {run && (
        <>
          <div className="section-title investigation-heading">
            <h3>
              {run.id}
              <small> · {run.provider}</small>
            </h3>
            <div className="run-actions">
              <span
                className={
                  "status " +
                  (run.status === "FAILED"
                    ? "red"
                    : run.status === "COMPLETE"
                      ? "green"
                      : "blue")
                }
              >
                {run.status}
              </span>
              {!["COMPLETE", "CANCELLED"].includes(run.status) && (
                <>
                  {run.status === "PAUSED" || run.status === "FAILED" ? (
                    <button
                      className="button"
                      onClick={() => control("resume")}
                    >
                      <Play size={12} />
                      Resume
                    </button>
                  ) : (
                    <button className="button" onClick={() => control("pause")}>
                      <Pause size={12} />
                      Pause
                    </button>
                  )}
                  <button className="button" onClick={() => control("cancel")}>
                    <X size={12} />
                    Cancel
                  </button>
                </>
              )}
            </div>
          </div>
          <div className="progress-track">
            <div
              style={{ width: (run.cursor / run.tasks.length) * 100 + "%" }}
            />
          </div>
          {run.error && <p className="error-text">{run.error}</p>}
          <div className="agent-tasks">
            {run.tasks.map((t: any) => (
              <details className="agent-task" key={t.id}>
                <summary>
                  <span
                    className={
                      "task-indicator " +
                      (t.status === "COMPLETE"
                        ? "done"
                        : t.status === "RUNNING"
                          ? "running"
                          : "")
                    }
                  >
                    {t.status === "COMPLETE" ? (
                      <Check size={13} />
                    ) : (
                      t.sequence + 1
                    )}
                  </span>
                  <span>
                    <strong>{t.agent}</strong>
                    <small>{t.objective}</small>
                  </span>
                  <span
                    className={
                      "status " +
                      (t.status === "FAILED"
                        ? "red"
                        : t.status === "COMPLETE"
                          ? "green"
                          : "blue")
                    }
                  >
                    {t.status}
                  </span>
                  <ChevronDown size={13} />
                </summary>
                <div className="agent-task-detail">
                  <dl>
                    <dt>Task ID</dt>
                    <dd>{t.id}</dd>
                    <dt>Tool execution</dt>
                    <dd>
                      {t.tool} · {t.attempts} attempt(s)
                    </dd>
                    <dt>Dependency</dt>
                    <dd>{t.dependency || "Entry task"}</dd>
                    <dt>Input originals</dt>
                    <dd>
                      {t.input_evidence.join(", ") || "No original selected"}
                    </dd>
                    <dt>Validation / output</dt>
                    <dd>
                      {t.output ? "Persisted tool result" : "Pending execution"}
                    </dd>
                  </dl>
                  {t.error && <p className="error-text">{t.error}</p>}
                  {t.output && <pre>{JSON.stringify(t.output, null, 2)}</pre>}
                </div>
              </details>
            ))}
          </div>
        </>
      )}
      {result && (
        <div className="audit-results">
          <span className="eyebrow">PERSISTED INVESTIGATION RESULT</span>
          <h3>{result.question}</h3>
          <span className="status amber">{result.review_state}</span>
          <p className="audit-summary">{result.summary}</p>
          {result.sources.map((source: any) => (
            <div className="citation" key={source.id}>
              <span className="status green">BYTE & TEXT HASHES VERIFIED</span>
              <h4>{source.title}</h4>
              <blockquote>{source.quote}</blockquote>
              <small>
                {source.location} · {source.id}
              </small>
              <a
                href={"/api/evidence/" + source.id + "/file"}
                target="_blank"
                rel="noreferrer"
              >
                Open stored original <ExternalLink size={12} />
              </a>
            </div>
          ))}
          {!result.sources.length && (
            <p className="error-text">
              No matching attested source passages. Secondary notes and
              unprocessed originals cannot substantiate an answer.
            </p>
          )}
          {result.findings.length > 0 && (
            <>
              <h4 className="history-title">
                Model proposals · human review required
              </h4>
              {result.findings.map((f: any, i: number) => (
                <div className="citation" key={i}>
                  <span className="status amber">{f.review_state}</span>
                  <h4>{f.claim}</h4>
                  <blockquote>{f.quote}</blockquote>
                  <small>
                    {f.evidence_id} · {f.citation_status}
                  </small>
                  <button
                    className="button attach-proposal"
                    onClick={async () => {
                      try {
                        await post(
                          "/investigation-findings/" +
                            run.id +
                            "/" +
                            i +
                            "/attach",
                          { board_id: "looking-glass" },
                        );
                        await onAttached();
                        notify(
                          "Proposal attached as a hypothesis; human review remains required",
                        );
                      } catch (e: any) {
                        notify(e.message);
                      }
                    }}
                  >
                    Attach proposal to board
                  </button>
                </div>
              ))}
            </>
          )}
          <h4 className="history-title">Red-team limitations</h4>
          {result.limitations.map((l: string, i: number) => (
            <p className="muted" key={i}>
              {l}
            </p>
          ))}
          {result.excluded_sources.length > 0 && (
            <details className="excluded-sources">
              <summary>
                {result.excluded_sources.length} sources excluded by the auditor
              </summary>
              <pre>{JSON.stringify(result.excluded_sources, null, 2)}</pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

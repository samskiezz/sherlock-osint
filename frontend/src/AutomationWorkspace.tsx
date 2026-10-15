import { useEffect, useMemo, useState } from "react";
import { api, post } from "./api";
import {
  Bot,
  Play,
  Pause,
  Square,
  RefreshCw,
  ShieldCheck,
  Workflow,
  Search,
  Clock3,
  FileCheck2,
} from "lucide-react";
import "./automation.css";

export default function AutomationWorkspace({
  evidence,
  notify,
  selectEvidence,
}: any) {
  const [catalogue, setCatalogue] = useState<any>(null);
  const [state, setState] = useState<any>(null);
  const [filter, setFilter] = useState("");
  const [family, setFamily] = useState("");
  const [selected, setSelected] = useState<any>(null);
  const [inputs, setInputs] = useState("{}");
  const [run, setRun] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState("");
  const [mission, setMission] = useState(
    "Identify the technical claims in this original and the evidence still needed to verify them.",
  );
  const [cron, setCron] = useState("17 */6 * * *");
  const [plan, setPlan] = useState("");
  const [workflowId, setWorkflowId] = useState("");
  const [binding, setBinding] = useState(false);
  const originals = evidence.filter((e: any) => e.fileUrl && e.text);
  async function refresh() {
    const value = await api("/automation");
    setState(value);
    if (run?.id) {
      const id = run.id;
      const value = await api("/automation/runs/" + id);
      setRun((current: any) => (current?.id === id ? value : current));
    }
  }
  useEffect(() => {
    api("/automation/catalogue")
      .then((v) => {
        setCatalogue(v);
        choose(
          v.tools.find((t: any) => t.id === "text.identifiers") || v.tools[0],
        );
      })
      .catch((e) => notify(e.message));
    refresh().catch((e) => notify(e.message));
  }, []);
  useEffect(() => {
    const timer = setInterval(() => refresh().catch(() => {}), 3500);
    return () => clearInterval(timer);
  }, [run?.id]);
  const tools = useMemo(
    () =>
      (catalogue?.tools || []).filter(
        (t: any) =>
          (!family || t.family === family) &&
          (t.title + " " + t.id + " " + t.procedure)
            .toLowerCase()
            .includes(filter.toLowerCase()),
      ),
    [catalogue, family, filter],
  );
  function choose(t: any) {
    setSelected(t);
    setInputs(JSON.stringify(t.example, null, 2));
    setBinding(false);
  }
  async function act(fn: () => Promise<any>) {
    setBusy(true);
    try {
      await fn();
      await refresh();
    } catch (e: any) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  }
  const seedPlan = () =>
    setPlan(
      JSON.stringify(
        {
          name: "Source verification and text triage",
          objective:
            "Verify a stored original, extract literal identifiers and produce reproducible lexical triage.",
          authorisation: "Investigator-selected public source analysis",
          max_seconds: 300,
          steps: [
            {
              id: "integrity",
              tool: "evidence.verify",
              inputs: { evidence_id: { $binding: "evidence_id" } },
            },
            {
              id: "identifiers",
              tool: "text.identifiers",
              depends_on: ["integrity"],
              inputs: { evidence_id: { $binding: "evidence_id" } },
            },
            {
              id: "terms",
              tool: "text.word_frequency",
              depends_on: ["integrity"],
              inputs: { evidence_id: { $binding: "evidence_id" } },
            },
            {
              id: "controls",
              tool: "text.unicode_controls",
              depends_on: ["integrity"],
              inputs: { evidence_id: { $binding: "evidence_id" } },
            },
          ],
        },
        null,
        2,
      ),
    );
  return (
    <div className="page-scroll automation-workspace">
      <div className="section-title">
        <h2>
          <Workflow size={23} /> Automation control
        </h2>
        <span className="status blue">PERSISTENT EXECUTION</span>
      </div>
      <p className="automation-intro">
        Run source-bound tools, build repeatable workflows and monitor newly
        acquired evidence. Every action leaves an execution receipt. Model
        proposals stay provisional.
      </p>
      <div className="automation-metrics">
        <div>
          <strong>{catalogue?.count ?? "—"}</strong>
          <span>Callable tools</span>
        </div>
        <div>
          <strong>
            {(catalogue?.by_kind?.MACHINE_LEARNING || 0) +
              (catalogue?.by_kind?.MODEL_INFERENCE || 0)}
          </strong>
          <span>ML / model adapters</span>
        </div>
        <div>
          <strong>
            {state?.runs?.filter((r: any) => r.status === "COMPLETE").length ??
              "—"}
          </strong>
          <span>Completed runs · latest 100</span>
        </div>
        <div>
          <strong>
            {state?.schedules?.filter((s: any) => s.enabled).length ?? "—"}
          </strong>
          <span>Active schedules</span>
        </div>
      </div>
      <div className="automation-policy">
        <ShieldCheck size={18} />
        <span>{state?.policy || "Loading execution policy…"}</span>
      </div>
      <div className="automation-grid">
        <section className="automation-panel tool-picker">
          <h3>
            <Search size={17} /> Executable tool library
          </h3>
          <input
            aria-label="Search automation tools"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search tools or procedures"
          />
          <select
            aria-label="Tool family"
            value={family}
            onChange={(e) => setFamily(e.target.value)}
          >
            <option value="">All families</option>
            {Object.keys(catalogue?.by_family || {}).map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
          <small>
            {tools.length} matching tools. Classical transforms and
            deterministic statistics are labelled separately from AI.
          </small>
          <div className="automation-tool-list">
            {tools.map((t: any) => (
              <button
                key={t.id}
                className={selected?.id === t.id ? "selected" : ""}
                onClick={() => choose(t)}
              >
                <strong>{t.title}</strong>
                <span>
                  {t.id} · {t.kind.replaceAll("_", " ")}
                </span>
              </button>
            ))}
          </div>
        </section>
        <section className="automation-panel">
          <h3>
            <FileCheck2 size={17} /> {selected?.title || "Select a tool"}
          </h3>
          <p>{selected?.procedure}</p>
          {selected && (
            <a href={selected.reference} target="_blank" rel="noreferrer">
              Technical reference ↗
            </a>
          )}
          <label>
            Source for evidence-bound actions
            <select
              aria-label="Automation source"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              <option value="">Select an acquired original</option>
              {originals.map((e: any) => (
                <option value={e.id} key={e.id}>
                  {e.title}
                </option>
              ))}
            </select>
          </label>
          <label className="automation-checkbox">
            <input
              type="checkbox"
              checked={binding}
              onChange={(e) => setBinding(e.target.checked)}
            />{" "}
            Bind analytical text to the first 12,000 verified characters; model
            tools select cited passages
          </label>
          <label>
            JSON parameters · supplied examples are synthetic
            <textarea
              aria-label="Automation tool parameters"
              value={inputs}
              onChange={(e) => setInputs(e.target.value)}
              spellCheck={false}
            />
          </label>
          <button
            className="primary"
            disabled={busy || !selected}
            onClick={() =>
              act(async () => {
                const value = JSON.parse(inputs);
                if (
                  binding ||
                  selected.id.startsWith("evidence.") ||
                  selected.id.startsWith("model.")
                ) {
                  if (!source) throw new Error("Select an acquired original");
                  delete value.text;
                  value.evidence_id = source;
                }
                setRun(
                  await post("/automation/run", {
                    tool: selected.id,
                    inputs: value,
                    authorisation:
                      "Investigator selected a bounded registered operation",
                  }),
                );
              })
            }
          >
            <Play size={15} /> Queue tool execution
          </button>
          <p className="automation-note">{selected?.limitations}</p>
        </section>
      </div>
      <section className="automation-panel mission-panel">
        <h3>
          <Bot size={18} /> Bounded autonomous source mission
        </h3>
        <p>
          A local model selects up to six allowed text tools. The controller
          verifies the source first, executes the validated plan, and checks
          model quotations. It cannot request arbitrary tools, code or commands.
        </p>
        <input
          aria-label="Autonomous mission objective"
          value={mission}
          onChange={(e) => setMission(e.target.value)}
        />
        <button
          disabled={busy || !source}
          onClick={() =>
            act(async () => {
              const value = await post("/automation/mission", {
                evidence_id: source,
                question: mission,
              });
              setWorkflowId(value.workflow_id);
              setRun(value.run);
            })
          }
        >
          <Bot size={16} /> Plan and run with local AI
        </button>
      </section>
      <div className="automation-grid">
        <section className="automation-panel">
          <h3>
            <Workflow size={18} /> Workflow builder
          </h3>
          <p>
            Explicit dependencies, data references, retry limits and failure
            policy. All steps use the registered allowlist.
          </p>
          <button onClick={seedPlan}>Load source-triage workflow</button>
          <textarea
            aria-label="Workflow JSON"
            className="workflow-editor"
            value={plan}
            onChange={(e) => setPlan(e.target.value)}
            placeholder="Load the working template or paste a workflow definition"
            spellCheck={false}
          />
          <div className="automation-actions">
            <button
              disabled={busy || !plan}
              onClick={() =>
                act(async () => {
                  const value = await post(
                    "/automation/workflows",
                    JSON.parse(plan),
                  );
                  setWorkflowId(value.id);
                  notify("Workflow saved");
                })
              }
            >
              Save workflow
            </button>
            <button
              disabled={busy || !workflowId}
              onClick={() =>
                act(async () =>
                  setRun(
                    await post(`/automation/workflows/${workflowId}/run`, {
                      evidence_id: source,
                    }),
                  ),
                )
              }
            >
              <Play size={14} /> Run saved workflow
            </button>
          </div>
          <select
            aria-label="Saved automation workflow"
            value={workflowId}
            onChange={(e) => {
              setWorkflowId(e.target.value);
              const w = state?.workflows.find(
                (w: any) => w.id === e.target.value,
              );
              if (w) setPlan(JSON.stringify(w.data, null, 2));
            }}
          >
            <option value="">Choose a saved workflow</option>
            {state?.workflows?.map((w: any) => (
              <option key={w.id} value={w.id}>
                {w.data.name}
              </option>
            ))}
          </select>
          <div className="automation-scheduler">
            <h4>
              <Clock3 size={15} /> Recurring automation
            </h4>
            <input
              aria-label="UTC cron expression"
              value={cron}
              onChange={(e) => setCron(e.target.value)}
            />
            <div className="automation-actions">
              <button
                disabled={busy || !workflowId}
                onClick={() =>
                  act(async () => {
                    await post("/automation/schedules", {
                      workflow_id: workflowId,
                      cron,
                      interval_minutes: 60,
                      trigger: "interval",
                      evidence_id: source,
                    });
                    notify(
                      "UTC schedule saved with the selected source binding.",
                    );
                  })
                }
              >
                Schedule UTC cron
              </button>
              <button
                disabled={busy || !workflowId}
                onClick={() =>
                  act(async () => {
                    await post("/automation/schedules", {
                      workflow_id: workflowId,
                      interval_minutes: 5,
                      trigger: "new_evidence",
                    });
                    notify(
                      "New originals will be processed every five minutes",
                    );
                  })
                }
              >
                Process new evidence
              </button>
            </div>
            <small>
              New-evidence schedules bind each original’s ID. Existing evidence
              is excluded by default. Scheduled failures remain visible.
            </small>
          </div>
          {state?.schedules?.map((s: any) => (
            <div className="automation-schedule" key={s.id}>
              <span>
                {s.data.schedule.trigger} ·{" "}
                {s.data.schedule.cron ||
                  `${s.data.schedule.interval_minutes} min`}{" "}
                · {s.enabled ? "ACTIVE" : "PAUSED"}
                {s.data.error && <em>{s.data.error}</em>}
              </span>
              <button
                onClick={() =>
                  act(() =>
                    post(
                      `/automation/schedules/${s.id}/${s.enabled ? "pause" : "resume"}`,
                      {},
                    ),
                  )
                }
              >
                {s.enabled ? "Pause" : "Resume"}
              </button>
            </div>
          ))}
        </section>
        <section className="automation-panel">
          <h3>
            <RefreshCw size={18} /> Execution receipts
          </h3>
          <select
            aria-label="Automation run history"
            value={run?.id || ""}
            onChange={(e) =>
              act(async () =>
                setRun(await api("/automation/runs/" + e.target.value)),
              )
            }
          >
            <option value="">Select a run</option>
            {state?.runs?.map((r: any) => (
              <option key={r.id} value={r.id}>
                {r.status} · {r.data.plan.name} · {r.id}
              </option>
            ))}
          </select>
          {run && (
            <>
              <div className="automation-run-status">
                <span
                  className={
                    "status " +
                    (run.status === "COMPLETE"
                      ? "green"
                      : run.status === "FAILED"
                        ? "red"
                        : "amber")
                  }
                >
                  {run.status}
                </span>
                <span>
                  {run.data.remaining_steps} steps remaining ·{" "}
                  {Number(run.data.active_seconds).toFixed(1)} active seconds
                </span>
              </div>
              <div className="automation-actions">
                {["QUEUED", "RUNNING", "PAUSED"].includes(run.status) && (
                  <>
                    <button
                      onClick={() =>
                        act(async () =>
                          setRun(
                            await post(
                              `/automation/runs/${run.id}/${run.status === "PAUSED" ? "resume" : "pause"}`,
                              {},
                            ),
                          ),
                        )
                      }
                    >
                      <Pause size={13} />{" "}
                      {run.status === "PAUSED" ? "Resume" : "Pause"}
                    </button>
                    <button
                      onClick={() =>
                        act(async () =>
                          setRun(
                            await post(`/automation/runs/${run.id}/cancel`, {}),
                          ),
                        )
                      }
                    >
                      <Square size={13} /> Cancel
                    </button>
                  </>
                )}
                <button
                  onClick={() => {
                    const b = new Blob([JSON.stringify(run, null, 2)], {
                      type: "application/json",
                    });
                    const url = URL.createObjectURL(b);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = run.id + ".json";
                    a.click();
                    setTimeout(() => URL.revokeObjectURL(url), 500);
                  }}
                >
                  Export receipt
                </button>
              </div>
              {run.data.error && (
                <p className="automation-error">{run.data.error}</p>
              )}
              {run.receipts.map((r: any) => (
                <details key={r.id} open={run.receipts.length === 1}>
                  <summary>
                    <b>{r.step_id}</b> · {r.status} · {r.data.tool}
                  </summary>
                  {r.data.result?.sources?.map(
                    (s: any) =>
                      s.evidence_id && (
                        <button
                          key={s.evidence_id}
                          onClick={() => selectEvidence(s.evidence_id)}
                        >
                          Open {s.evidence_id}
                        </button>
                      ),
                  )}
                  <pre>{JSON.stringify(r.data, null, 2)}</pre>
                </details>
              ))}
            </>
          )}
        </section>
      </div>
      <p className="automation-note">
        The catalogue counts callable computational tools, including distinct
        statistical tests and classical transformations. It does not claim 200
        independent AI agents or flawless investigation.{" "}
        <a href="/api/automation/references" target="_blank" rel="noreferrer">
          Read the documentation acquisition record ↗
        </a>
      </p>
    </div>
  );
}

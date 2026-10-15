import { useEffect, useState } from "react";
import { api, post } from "./api";
import {
  Bot,
  Play,
  Pause,
  Radio,
  ScanEye,
  Hash,
  Search,
  Workflow,
} from "lucide-react";
import "./automation.css";

export default function AutonomousWorkspace({
  evidence,
  notify,
  selectEvidence,
}: any) {
  const [status, setStatus] = useState<any>(null),
    [social, setSocial] = useState<any>(null),
    [current, setCurrent] = useState<any>(null);
  const [text, setText] = useState("436f6c6520416c6c656e"),
    [gemText, setGemText] = useState("Cole Allen"),
    [busy, setBusy] = useState(false);
  const [query, setQuery] = useState(
      "from:CForce3000 OR from:Bohrdom1 OR from:HenryMa79561893",
    ),
    [mode, setMode] = useState("recent");
  const [image, setImage] = useState(""),
    [audit, setAudit] = useState<any>(null);
  const [auditInput, setAuditInput] = useState(
    JSON.stringify(
      {
        artefact_id: "",
        artefact_quote: "",
        claimed_publication_utc: "2023-12-22T00:00:00Z",
        event_utc: "2026-04-25T00:00:00Z",
        specific_outcome:
          "Specify the actual outcome allegedly predicted, including its action, place and time.",
        specificity_terms: ["attack", "2026"],
        timestamp_source_id: "",
        timestamp_quote: "",
        counterevidence_ids: [],
      },
      null,
      2,
    ),
  );
  const images = evidence.filter(
    (e: any) => e.fileUrl && e.mime?.startsWith("image/"),
  );
  async function refresh() {
    const [a, s] = await Promise.all([api("/autopilot"), api("/social")]);
    setStatus(a);
    setSocial(s);
    if (current?.id) {
      const id = current.id;
      const value = await api("/automation/runs/" + id);
      setCurrent((old: any) => (old?.id === id ? value : old));
    }
  }
  useEffect(() => {
    refresh().catch((e) => notify(e.message));
    const timer = setInterval(() => refresh().catch(() => {}), 4000);
    return () => clearInterval(timer);
  }, [current?.id]);
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
  async function queue(tool: string, inputs: any) {
    setCurrent(
      await post("/automation/run", {
        tool,
        inputs,
        authorisation:
          "User requested automatic evidence analysis with preserved results",
      }),
    );
  }
  const gem = current?.receipts?.find(
    (r: any) => r.data.tool === "gematria.all",
  )?.data.result?.output;
  const decoded = current?.receipts?.find(
    (r: any) => r.data.tool === "decoder.auto",
  )?.data.result?.output;
  const visual = current?.receipts?.find(
    (r: any) => r.data.tool === "visual.search",
  )?.data.result?.output;
  return (
    <div className="page-scroll automation-workspace">
      <div className="section-title">
        <h2>
          <Bot /> Autonomous investigation
        </h2>
        <span className="status blue">TYPE-AWARE PARALLEL ANALYSIS</span>
      </div>
      <p className="automation-intro">
        One case-wide service selects compatible functions, infers decoding
        recipes and processes new originals. You do not need to select a cipher
        for each item. Missing keys, labels, source permissions and valid
        baselines remain visible.
      </p>
      <div className="automation-metrics">
        <div>
          <strong>
            {status?.parallelism?.global_analytical_actions ?? "—"}
          </strong>
          <span>Parallel analytical actions</span>
        </div>
        <div>
          <strong>{status?.parallelism?.ready_steps_per_run ?? "—"}</strong>
          <span>Independent branches per run</span>
        </div>
        <div>
          <strong>{status?.dispatches?.length ?? "—"}</strong>
          <span>Source profiles · latest 100</span>
        </div>
        <div>
          <strong>{social?.posts?.length ?? 0}</strong>
          <span>Stored X posts · shown latest 200</span>
        </div>
      </div>
      <section className="automation-panel">
        <h3>
          <Workflow size={18} /> Automatic case processing
        </h3>
        <p>{status?.policy}</p>
        <div className="automation-actions">
          <button
            disabled={busy}
            onClick={() =>
              act(async () => {
                await api("/autopilot/settings", {
                  method: "PUT",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    ...status.settings,
                    enabled: !status.settings.enabled,
                  }),
                });
              })
            }
          >
            {status?.settings?.enabled ? (
              <Pause size={15} />
            ) : (
              <Play size={15} />
            )}{" "}
            {status?.settings?.enabled
              ? "Pause automatic analysis"
              : "Start automatic analysis"}
          </button>
          <button
            disabled={busy}
            onClick={() =>
              act(async () => {
                const r = await post("/autopilot/scan", { limit: 5 });
                notify(
                  r.dispatches.length + " compatible source profiles queued",
                );
                if (r.dispatches[0])
                  setCurrent(
                    await api("/automation/runs/" + r.dispatches[0].run_id),
                  );
              })
            }
          >
            Analyse acquired originals now
          </button>
        </div>
        <small>
          Four actions across independent workflows; generation calls and
          isolated media parsers have separate resource limits. Source hashes
          and dependencies are checked before work starts.
        </small>
        <div className="automation-tool-list" style={{ height: 180 }}>
          {status?.dispatches?.map((d: any) => (
            <button
              key={d.run_id}
              onClick={() =>
                act(async () =>
                  setCurrent(await api("/automation/runs/" + d.run_id)),
                )
              }
            >
              <strong>
                {d.evidence_id} · {d.data.steps} automatic steps
              </strong>
              <span>
                {d.data.compatible_tools}/{d.data.catalogue_tools} tools
                applicable · exact candidate spans and skip reasons saved
              </span>
            </button>
          ))}
        </div>
      </section>
      <div className="automation-grid" style={{ marginTop: 20 }}>
        <section className="automation-panel">
          <h3>
            <Search size={18} /> Automatic multi-layer decoder
          </h3>
          <p>
            Established engine: GCHQ CyberChef Magic. It infers and tests recipe
            chains; no method selection. Execution stays in a read-only,
            network-disabled container.
          </p>
          <textarea
            aria-label="Automatic decoder input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            spellCheck={false}
          />
          <button
            disabled={busy}
            onClick={() => act(() => queue("decoder.auto", { text, depth: 3 }))}
          >
            Automatically identify and decode
          </button>
          {decoded && (
            <>
              <p>
                {decoded.returned_candidates} returned candidates ·{" "}
                {decoded.version} · {decoded.sandbox?.network} network
              </p>
              {decoded.candidates?.slice(0, 8).map((c: any, i: number) => (
                <details key={i} open={i === 0}>
                  <summary>
                    {c.recipe?.map((o: any) => o.op).join(" → ") ||
                      "Untransformed input"}
                  </summary>
                  <pre>
                    {typeof c.data === "string"
                      ? c.data
                      : JSON.stringify(c.data, null, 2)}
                  </pre>
                </details>
              ))}
            </>
          )}
        </section>
        <section className="automation-panel">
          <h3>
            <Hash size={18} /> Gematria / isopsephy
          </h3>
          <p>
            All eight explicit English, Hebrew and Greek mappings run together.
            Every original letter, normalisation and numerical contribution is
            retained.
          </p>
          <input
            aria-label="Gematria text"
            value={gemText}
            onChange={(e) => setGemText(e.target.value)}
          />
          <button
            disabled={busy}
            onClick={() =>
              act(() =>
                queue("gematria.all", { text: gemText, targets: [], seed: 42 }),
              )
            }
          >
            Run all gematria mappings
          </button>
          {gem && (
            <>
              <div
                className="automation-metrics"
                style={{ gridTemplateColumns: "1fr 1fr" }}
              >
                {gem.results.map((r: any) => (
                  <div key={r.table}>
                    <strong>{r.matched_letters ? r.sum : "—"}</strong>
                    <span>{r.table.replaceAll("_", " ")}</span>
                  </div>
                ))}
              </div>
              <p>{gem.limitations}</p>
              <small>
                {gem.tables_attempted} tables · {gem.control_strings_attempted}{" "}
                toy controls · shuffling letters cannot validate an additive
                sum.
              </small>
            </>
          )}
        </section>
      </div>
      <div className="automation-grid">
        <section className="automation-panel">
          <h3>
            <Radio size={18} /> X / Twitter collection
          </h3>
          <span
            className={"status " + (social?.configured ? "green" : "amber")}
          >
            {social?.configured ? "CREDENTIAL CONFIGURED" : "NOT CONFIGURED"}
          </span>
          <p>{social?.coverage}</p>
          <p>{social?.setup}</p>
          <input
            aria-label="X public search query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <select
            aria-label="X collection mode"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="recent">Recent public search</option>
            <option value="full_archive">
              Full archive · entitlement required
            </option>
            <option value="filtered_stream">
              Filtered live stream · entitlement required
            </option>
          </select>
          <button
            disabled={busy}
            onClick={() =>
              act(async () => {
                const f = await post("/social/feeds", {
                  name: "Looking Glass public query",
                  query,
                  mode,
                  interval_seconds: 120,
                  acquire_media: true,
                });
                const r = await post("/social/feeds/" + f.id + "/poll", {});
                notify(r.status);
              })
            }
          >
            Create and check feed
          </button>
          {social?.feeds?.map((f: any) => (
            <div className="automation-schedule" key={f.id}>
              <span>
                {f.data.query}
                <em>
                  {f.data.last_status || "WAITING"} · {f.data.mode}
                </em>
              </span>
              <button
                onClick={() =>
                  act(() =>
                    post(
                      `/social/feeds/${f.id}/${f.enabled ? "pause" : "resume"}`,
                      {},
                    ),
                  )
                }
              >
                {f.enabled ? "Pause" : "Resume"}
              </button>
            </div>
          ))}
          {social?.polls?.slice(0, 3).map((p: any) => (
            <p key={p.id}>
              {p.status}:{" "}
              {p.data.reason ||
                `${p.data.posts_received} actual post records preserved`}
            </p>
          ))}
        </section>
        <section className="automation-panel">
          <h3>
            <ScanEye size={18} /> Image artefact comparison
          </h3>
          <p>
            Compare actual source pixels at several blur scales, then inspect
            ImageHash signatures and OpenCV ORB/RANSAC matches. Similarity is a
            lead; the method does not determine identity or foreknowledge.
          </p>
          <select
            aria-label="Visual reference original"
            value={image}
            onChange={(e) => setImage(e.target.value)}
          >
            <option value="">Select an acquired image</option>
            {images.map((e: any) => (
              <option key={e.id} value={e.id}>
                {e.title}
              </option>
            ))}
          </select>
          <button
            disabled={busy || !image}
            onClick={() =>
              act(async () => {
                const w = await post("/automation/workflows", {
                  name: "Automatic image preparation and retrieval",
                  objective:
                    "Verify the actual image, extract sandboxed visual signatures and compare source-linked originals.",
                  authorisation:
                    "User requested digital image and artefact examination",
                  parallelism: 3,
                  steps: [
                    {
                      id: "prepare",
                      tool: "visual.prepare",
                      inputs: { evidence_id: image },
                    },
                    {
                      id: "compare",
                      tool: "visual.search",
                      depends_on: ["prepare"],
                      inputs: { evidence_id: image, limit: 12 },
                    },
                  ],
                });
                setCurrent(await post(`/automation/workflows/${w.id}/run`, {}));
              })
            }
          >
            Prepare and compare image
          </button>
          {image && (
            <div style={{ display: "flex", gap: 10, marginTop: 15 }}>
              <img
                alt="Preserved original preview"
                src={`/api/evidence/${image}/preview`}
                style={{ width: "48%", objectFit: "contain" }}
              />
              <img
                alt="Hash-verified low-frequency diagnostic"
                src={`/api/evidence/${image}/diagnostic/visual-blur-8`}
                style={{ width: "48%", objectFit: "contain" }}
                onError={(e) => {
                  e.currentTarget.style.display = "none";
                }}
              />
            </div>
          )}
          {visual && (
            <>
              <p>
                {visual.compared} acquired images compared;{" "}
                {visual.unavailable.length} need signatures. {visual.scope}
              </p>
              {visual.results.slice(0, 6).map((r: any) => (
                <div className="automation-schedule" key={r.evidence_id}>
                  <span>
                    {r.title}
                    <em>
                      pHash distance {r.hash_distances.phash}/64 ·{" "}
                      {r.ransac_inliers} geometric inliers · REVIEW REQUIRED
                    </em>
                  </span>
                  <button onClick={() => selectEvidence(r.evidence_id)}>
                    Inspect
                  </button>
                </div>
              ))}
            </>
          )}
        </section>
      </div>
      <section className="automation-panel">
        <h3>
          <Workflow size={18} /> Execution progress and source receipts
        </h3>
        {current ? (
          <>
            <div className="automation-run-status">
              <span
                className={
                  "status " +
                  (current.status === "COMPLETE" ? "green" : "amber")
                }
              >
                {current.status}
              </span>
              <span>
                {current.data.remaining_steps} steps remaining ·{" "}
                {current.data.plan.parallelism || 3} ready branches
              </span>
            </div>
            {["QUEUED", "RUNNING", "PAUSED"].includes(current.status) && (
              <div className="automation-actions">
                <button
                  onClick={() =>
                    act(async () =>
                      setCurrent(
                        await post(
                          `/automation/runs/${current.id}/${current.status === "PAUSED" ? "resume" : "pause"}`,
                          {},
                        ),
                      ),
                    )
                  }
                >
                  {current.status === "PAUSED" ? "Resume" : "Pause"}
                </button>
                <button
                  onClick={() =>
                    act(async () =>
                      setCurrent(
                        await post(`/automation/runs/${current.id}/cancel`, {}),
                      ),
                    )
                  }
                >
                  Cancel
                </button>
              </div>
            )}
            {current.receipts.map((r: any) => (
              <details key={r.id}>
                <summary>
                  {r.step_id} · {r.status} ·{" "}
                  {r.data.elapsed_seconds?.toFixed(2)} seconds
                </summary>
                <pre>{JSON.stringify(r.data, null, 2)}</pre>
              </details>
            ))}
          </>
        ) : (
          <p>
            Select a source profile or start an automatic experiment. No
            successful result is shown before its receipt exists.
          </p>
        )}
      </section>
      <section className="automation-panel" style={{ marginTop: 20 }}>
        <h3>Alleged prediction audit</h3>
        <p>
          Test the exact original quotation, the claimed date, a distinct
          timestamp-supporting source and an explicit outcome. A name, visual
          resemblance or numerical match alone cannot pass a specific prediction
          test. Counterevidence remains attached.
        </p>
        <textarea
          aria-label="Prediction audit parameters"
          value={auditInput}
          onChange={(e) => setAuditInput(e.target.value)}
          style={{ height: 220 }}
          spellCheck={false}
        />
        <button
          disabled={busy}
          onClick={() =>
            act(async () =>
              setAudit(
                await post("/prediction-audits", JSON.parse(auditInput)),
              ),
            )
          }
        >
          Audit source and chronology
        </button>
        {audit && <pre>{JSON.stringify(audit, null, 2)}</pre>}
      </section>
    </div>
  );
}

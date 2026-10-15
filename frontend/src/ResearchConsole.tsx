import { useEffect, useState } from "react";
import {
  Search,
  Plus,
  Play,
  Pause,
  X,
  ExternalLink,
  Radio,
  FileText,
  ChevronDown,
} from "lucide-react";
import { api, post } from "./api";

const stageNames = [
  "Discover sources",
  "Acquire originals",
  "Follow documents",
  "Audit evidence",
  "Publish to board",
];
export default function ResearchConsole({
  notify,
  onBoard,
  selectEvidence,
}: {
  notify: (s: string) => void;
  onBoard: (id: string) => void;
  selectEvidence: (id: string) => void;
}) {
  const [data, setData] = useState<any>({
      campaigns: [],
      runs: [],
      discovery: [],
    }),
    [providers, setProviders] = useState<any[]>([]),
    [models, setModels] = useState<any>(null),
    [open, setOpen] = useState(false),
    [selected, setSelected] = useState("");
  const [draft, setDraft] = useState({
    name: "Looking Glass · recurring public-source research",
    question:
      "Find new public documents relevant to Bohrdom and Mondaloy. Report exact source passages, distinguish reporting from original technical records, and preserve attribution uncertainty.",
    queries: "Bohrdom\nMondaloy",
    providers: ["internet_archive", "nasa", "gdelt"],
    seeds: "",
    domains: "",
    cron_expression: "0 */6 * * *",
    interval_minutes: 360,
    max_downloads: 6,
    provider: "deterministic",
    model: "",
    collect_images: false,
    collect_all_seed_images: false,
    follow_patents: false,
  });
  const refresh = () =>
    api("/research")
      .then(setData)
      .catch((e) => notify(e.message));
  useEffect(() => {
    refresh();
    Promise.all([api("/research/providers"), api("/models")])
      .then(([p, m]) => {
        setProviders(p);
        setModels(m);
      })
      .catch((e) => notify(e.message));
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);
  const split = (s: string) =>
    s
      .split("\n")
      .map((x) => x.trim())
      .filter(Boolean);
  const run = data.runs.find((r: any) => r.id === selected) || data.runs[0];
  const act = async (id: string, action: string) => {
    try {
      await post(`/research/${id}/${action}`, {});
      await refresh();
      notify(`Research ${action} saved`);
    } catch (e: any) {
      notify(e.message);
    }
  };
  return (
    <div className="lab-page research-console">
      <div className="lab-heading">
        <div>
          <span className="eyebrow">AUTONOMOUS ONLINE RESEARCH</span>
          <h2>Search. Acquire. Follow the evidence.</h2>
          <p>
            Recurring case questions across public indexes, disclosure feeds and
            onion sources. Each search and tool result survives a restart.
          </p>
        </div>
        <button className="button primary" onClick={() => setOpen(!open)}>
          <Plus size={14} /> New research campaign
        </button>
      </div>
      <div className="analysis-metrics">
        <div>
          <strong>{data.campaigns.filter((c: any) => c.enabled).length}</strong>
          <span>active cron campaigns</span>
        </div>
        <div>
          <strong>{data.discovery.length}</strong>
          <span>discovered source URLs</span>
        </div>
        <div>
          <strong>
            {data.runs.reduce(
              (n: number, r: any) => n + (r.data.result?.acquired?.length || 0),
              0,
            )}
          </strong>
          <span>verified acquisition records across runs</span>
        </div>
        <div>
          <strong>
            {
              data.runs.filter((r: any) =>
                ["QUEUED", "RUNNING", "WAITING"].includes(r.status),
              ).length
            }
          </strong>
          <span>active research runs</span>
        </div>
      </div>
      {open && (
        <form
          className="lab-form research-form"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              const result = await post("/research", {
                name: draft.name,
                question: draft.question,
                queries: split(draft.queries),
                providers: draft.providers,
                seeds: split(draft.seeds),
                allowed_domains: split(draft.domains),
                cron_expression: draft.cron_expression,
                interval_minutes: draft.interval_minutes,
                max_downloads: draft.max_downloads,
                provider: draft.provider,
                model: draft.model,
                collect_images: draft.collect_images,
                collect_all_seed_images: draft.collect_all_seed_images,
                follow_patents: draft.follow_patents,
              });
              setOpen(false);
              await refresh();
              notify("Recurring researcher enabled; initial run is due now");
            } catch (e: any) {
              notify(e.message);
            }
          }}
        >
          <h3>Define a bounded research job</h3>
          <label>
            Campaign name
            <input
              required
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </label>
          <label>
            Investigative question
            <textarea
              required
              rows={3}
              value={draft.question}
              onChange={(e) => setDraft({ ...draft, question: e.target.value })}
            />
          </label>
          <div className="form-grid">
            <label>
              Search queries · one per line, maximum four
              <textarea
                required
                rows={4}
                value={draft.queries}
                onChange={(e) =>
                  setDraft({ ...draft, queries: e.target.value })
                }
              />
            </label>
            <label>
              Public feed / disclosure-page / onion seed URLs · one per line
              <textarea
                rows={4}
                value={draft.seeds}
                onChange={(e) => setDraft({ ...draft, seeds: e.target.value })}
                placeholder="Public sources only; onion addresses use Tor exclusively."
              />
            </label>
          </div>
          <div className="provider-grid">
            {providers.map((p) => (
              <label
                key={p.id}
                className={draft.providers.includes(p.id) ? "chosen" : ""}
              >
                <input
                  type="checkbox"
                  checked={draft.providers.includes(p.id)}
                  onChange={() =>
                    setDraft({
                      ...draft,
                      providers: draft.providers.includes(p.id)
                        ? draft.providers.filter((x) => x !== p.id)
                        : [...draft.providers, p.id],
                    })
                  }
                />
                <div>
                  <strong>{p.name}</strong>
                  <small>{p.state}</small>
                </div>
              </label>
            ))}
          </div>
          <div className="form-grid">
            <label>
              UTC cron expression
              <input
                value={draft.cron_expression}
                onChange={(e) =>
                  setDraft({ ...draft, cron_expression: e.target.value })
                }
                placeholder="0 */6 * * *"
              />
              <small>Leave empty to use the interval.</small>
            </label>
            <label>
              Interval minutes
              <input
                type="number"
                min="15"
                value={draft.interval_minutes}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    interval_minutes: Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Maximum source downloads per run
              <input
                type="number"
                min="1"
                max="20"
                value={draft.max_downloads}
                onChange={(e) =>
                  setDraft({ ...draft, max_downloads: Number(e.target.value) })
                }
              />
            </label>
            <label>
              Optional allowed domains · one per line
              <textarea
                rows={2}
                value={draft.domains}
                onChange={(e) =>
                  setDraft({ ...draft, domains: e.target.value })
                }
                placeholder="ntrs.nasa.gov"
              />
            </label>
          </div>
          <div className="form-grid">
            <label>
              Evidence analysis
              <select
                value={draft.provider}
                onChange={(e) =>
                  setDraft({ ...draft, provider: e.target.value, model: "" })
                }
              >
                <option value="deterministic">
                  Source retrieval and independent integrity audit
                </option>
                <option value="ollama" disabled={!models?.ollama?.ready}>
                  Local Ollama · citation-checked proposals
                </option>
                <option value="anthropic" disabled={!models?.anthropic?.ready}>
                  Claude · configured API only
                </option>
              </select>
            </label>
            {draft.provider === "ollama" ? (
              <label>
                Installed local model
                <select
                  required
                  value={draft.model}
                  onChange={(e) =>
                    setDraft({ ...draft, model: e.target.value })
                  }
                >
                  <option value="">Choose model</option>
                  {models?.ollama?.models.map((m: string) => (
                    <option key={m}>{m}</option>
                  ))}
                </select>
              </label>
            ) : draft.provider === "anthropic" ? (
              <label>
                Configured Claude model
                <input
                  required
                  value={draft.model}
                  onChange={(e) =>
                    setDraft({ ...draft, model: e.target.value })
                  }
                />
              </label>
            ) : (
              <p className="muted">
                Documents are preserved, parsed, audited and attached
                automatically. Model-generated claims remain hypotheses.
              </p>
            )}
          </div>
          <label>
            <input
              type="checkbox"
              checked={draft.collect_images}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  collect_images: e.target.checked,
                  collect_all_seed_images:
                    e.target.checked && draft.collect_all_seed_images,
                })
              }
            />{" "}
            Acquire publisher-linked images · subject attribution remains
            unverified
          </label>
          <label>
            <input
              type="checkbox"
              checked={draft.collect_all_seed_images}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  collect_all_seed_images: e.target.checked,
                  collect_images: e.target.checked || draft.collect_images,
                })
              }
            />{" "}
            Include uncaptioned images from explicit seed pages within the
            download budget
          </label>
          <label>
            <input
              type="checkbox"
              checked={draft.follow_patents}
              onChange={(e) =>
                setDraft({ ...draft, follow_patents: e.target.checked })
              }
            />{" "}
            Follow patent PDF and citation/family leads within the download
            budget
          </label>
          <button className="button primary">
            <Radio size={14} /> Start recurring researcher
          </button>
          <p className="muted">
            Search responses are catalogues, not paper acquisitions. Public
            disclosure labels do not authenticate a “leak.” No login, CAPTCHA
            bypass or downloaded code execution is performed.
          </p>
        </form>
      )}
      {!data.campaigns.length && !open && (
        <div className="lab-empty">
          <Search size={40} />
          <h3>Give the researcher a case question</h3>
          <p>
            It will search public sources on its own schedule, recover available
            originals, follow document links, audit citations and update a case
            board.
          </p>
        </div>
      )}
      {data.campaigns.map((c: any) => (
        <article className="campaign-card" key={c.id}>
          <div className="lab-toolbar">
            <span className={`status ${c.enabled ? "green" : "amber"}`}>
              {c.enabled ? "RECURRING RESEARCH ENABLED" : "PAUSED"}
            </span>
            <span className="eyebrow">
              {c.settings.cron_expression
                ? `${c.settings.cron_expression} UTC`
                : `Every ${c.settings.interval_minutes} minutes`}
            </span>
          </div>
          <h3>{c.name}</h3>
          <p>{c.settings.question}</p>
          <div className="research-query-tags">
            {c.settings.queries.map((q: string) => (
              <span key={q}>{q}</span>
            ))}
          </div>
          <small>
            {c.settings.providers.join(" · ")} · {c.settings.max_downloads}{" "}
            source-download budget · Next{" "}
            {new Date(c.next_run * 1000).toISOString()}
          </small>
          <div className="lab-toolbar">
            <button className="button" onClick={() => act(c.id, "run")}>
              <Play size={13} /> Run now
            </button>
            <button
              className="button"
              onClick={() => act(c.id, c.enabled ? "pause" : "resume")}
            >
              {c.enabled ? <Pause size={13} /> : <Play size={13} />}{" "}
              {c.enabled ? "Pause campaign" : "Resume campaign"}
            </button>
            <button className="button" onClick={() => act(c.id, "cancel")}>
              <X size={13} /> Cancel active run
            </button>
            <button className="button" onClick={() => onBoard(c.board_id)}>
              <ExternalLink size={13} /> Open research board
            </button>
          </div>
        </article>
      ))}
      {run && (
        <section className="research-run">
          <div className="lab-toolbar">
            <h3>Durable execution history</h3>
            <select
              aria-label="Research run history"
              value={run.id}
              onChange={(e) => setSelected(e.target.value)}
            >
              {data.runs.map((r: any) => (
                <option key={r.id} value={r.id}>
                  {r.created.slice(0, 19)} · {r.status} · {r.id}
                </option>
              ))}
            </select>
            <span
              className={`status ${run.status === "COMPLETE" ? "green" : run.status === "FAILED" ? "red" : "amber"}`}
            >
              {run.status}
            </span>
          </div>
          <div className="research-stages">
            {stageNames.map((name, i) => (
              <div
                key={name}
                className={
                  run.cursor > i ? "done" : run.cursor === i ? "current" : ""
                }
              >
                <span>{i + 1}</span>
                <strong>{name}</strong>
                <small>
                  {run.cursor > i
                    ? "Checkpoint saved"
                    : run.cursor === i
                      ? "Current dependency"
                      : "Pending"}
                </small>
              </div>
            ))}
          </div>
          {run.error && <p className="notice">{run.error}</p>}
          {run.data.result && (
            <div className="research-outcome">
              <span className="eyebrow">{run.data.result.outcome}</span>
              <h3>
                {run.data.result.acquired?.length || 0} verified original
                records · {run.data.result.new_originals || 0} new vault files
              </h3>
              <p>
                {run.data.result.hypothesis_proposals?.length || 0}{" "}
                citation-checked hypothesis proposals · analysis:{" "}
                {run.data.result.analysis_state}
              </p>
              {run.data.result.acquired?.map((e: any) => (
                <button key={e.id} onClick={() => selectEvidence(e.id)}>
                  <FileText size={14} />
                  <div>
                    <strong>{e.title}</strong>
                    <small>
                      {e.id} · SHA-256 {e.sha256.slice(0, 16)}…
                    </small>
                  </div>
                  <span>Inspect →</span>
                </button>
              ))}
              {run.data.result.failures?.map((f: any) => (
                <p className="research-error" key={f.id}>
                  {f.status} · {f.error}
                </p>
              ))}
            </div>
          )}
          {run.tasks.map((t: any) => (
            <details className="research-task" key={t.id}>
              <summary>
                <span
                  className={`status ${t.status === "COMPLETE" ? "blue" : t.status === "FAILED" ? "red" : "amber"}`}
                >
                  {t.status}
                </span>
                <strong>{t.objective}</strong>
                <small>{t.attempts} attempt(s)</small>
                <ChevronDown size={13} />
              </summary>
              <div>
                <span className="eyebrow">
                  {t.id} · {t.task_key}
                </span>
                {t.error && <p className="research-error">{t.error}</p>}
                <pre>{JSON.stringify(t.output, null, 2)}</pre>
              </div>
            </details>
          ))}
        </section>
      )}
    </div>
  );
}

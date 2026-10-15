import { useEffect, useState } from "react";
import {
  ShieldCheck,
  Search,
  FileText,
  ExternalLink,
  Download,
} from "lucide-react";
import { api, post } from "./api";

export default function OnionResearch({
  evidence,
  notify,
  selectEvidence,
}: {
  evidence: any[];
  notify: (s: string) => void;
  selectEvidence: (id: string) => void;
}) {
  const [status, setStatus] = useState<any>(null),
    [proxy, setProxy] = useState("socks5h://127.0.0.1:9050"),
    [url, setUrl] = useState(""),
    [jobs, setJobs] = useState<any[]>([]),
    [selected, setSelected] = useState("");
  const refresh = async () => {
    try {
      const [s, j] = await Promise.all([api("/onion/status"), api("/jobs")]);
      setStatus(s);
      setJobs(j.filter((j: any) => j.transport === "tor"));
    } catch (e: any) {
      notify(e.message);
    }
  };
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, []);
  const originals = evidence.filter(
    (e) => e.metadata.network_transport === "tor",
  );
  const active = originals.find((e) => e.id === selected) || originals[0];
  return (
    <div className="lab-page onion-workspace">
      <div className="lab-heading">
        <div>
          <span className="eyebrow">PUBLIC ONION DOCUMENT RESEARCH</span>
          <h2>A separate route. The same evidence standard.</h2>
          <p>
            Acquire public v3 onion pages and documents through Tor, preserve
            the originals and follow their source links.
          </p>
        </div>
        <ShieldCheck size={30} />
      </div>
      <div className="tor-status">
        <span className={`status ${status?.ready ? "green" : "amber"}`}>
          {status?.state || "CHECKING TOR ROUTE"}
        </span>
        <h3>{status?.reason}</h3>
        <div>
          <span>DNS: resolved through SOCKS5h</span>
          <span>Clearnet fallback: never</span>
          <span>Originals: read-only SHA-256 vault</span>
        </div>
      </div>
      <form
        className="lab-form"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            const s = await post("/onion/config", { enabled: true, proxy });
            setStatus(s);
            notify(
              s.ready
                ? "Local SOCKS handshake succeeded"
                : "Configuration saved; connection blocker remains visible",
            );
          } catch (e: any) {
            notify(e.message);
          }
        }}
      >
        <h3>Local Tor connection</h3>
        <label>
          Loopback SOCKS5h endpoint
          <input
            required
            value={proxy}
            onChange={(e) => setProxy(e.target.value)}
          />
        </label>
        <div className="lab-toolbar">
          <button
            type="button"
            className="button"
            onClick={() => setProxy("socks5h://127.0.0.1:9150")}
          >
            Tor Browser · port 9150
          </button>
          <button
            type="button"
            className="button"
            onClick={() => setProxy("socks5h://127.0.0.1:9050")}
          >
            Native Tor · port 9050
          </button>
          <button className="button primary">Save & check Tor route</button>
        </div>
        <p className="muted">
          Start native Tor or Tor Browser on the same computer. This reader
          fetches documents through Tor; it does not claim Tor Browser’s
          complete fingerprinting protections.
        </p>
      </form>
      <form
        className="onion-address-bar"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await post("/jobs", {
              url,
              title: "Public onion document · " + new URL(url).hostname,
              transport: "tor",
            });
            await refresh();
            notify("Tor-only acquisition queued; failures will remain visible");
          } catch (e: any) {
            notify(e.message);
          }
        }}
      >
        <Search size={16} />
        <input
          aria-label="Public onion document URL"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="http://[verified 56-character v3 address].onion/document.pdf"
        />
        <button className="button primary">
          <Download size={14} /> Acquire through Tor
        </button>
      </form>
      <p className="muted">
        For scheduled discovery, create an Online researcher campaign with
        Ahmia’s public index or explicit public onion seed URLs. Onion
        acquisition remains blocked when the runtime cannot support Tor. No
        normal DNS request or public HTTP fallback is made.
      </p>
      {jobs.map((j) => (
        <div className="tor-job" key={j.id}>
          <div>
            <strong>{j.objective}</strong>
            <small>{j.url}</small>
            {j.error && <p className="research-error">{j.error}</p>}
          </div>
          <span
            className={`status ${j.status === "COMPLETE" ? "green" : j.status.includes("FAILED") ? "red" : "amber"}`}
          >
            {j.status}
          </span>
        </div>
      ))}
      <div className="onion-reader-layout">
        <aside>
          <h3>Preserved onion originals</h3>
          {originals.map((e) => (
            <button key={e.id} onClick={() => setSelected(e.id)}>
              <FileText size={14} />
              {e.title}
            </button>
          ))}
          {!originals.length && (
            <p>
              No onion original has been acquired. A configured proxy, URL or
              failed job does not count as evidence.
            </p>
          )}
        </aside>
        <section>
          {active ? (
            <>
              <div className="archive-source">
                <span className="eyebrow">{active.status} · TOR SOCKS5h</span>
                <h3>{active.title}</h3>
                <code>SHA-256 {active.sha256}</code>
                <button
                  className="button"
                  onClick={() => selectEvidence(active.id)}
                >
                  <ExternalLink size={13} /> Open evidence inspector
                </button>
              </div>
              <pre>
                {active.text ||
                  "No text extracted. Inspect the preserved original file."}
              </pre>
              <h4>Source document links</h4>
              {(active.metadata.links || [])
                .filter((l: any) => /\.pdf(?:$|[?#])/i.test(l.href))
                .slice(0, 20)
                .map((l: any, i: number) => (
                  <button
                    className="button"
                    key={i}
                    onClick={() => setUrl(new URL(l.href, active.url).href)}
                  >
                    {l.label || l.href} →
                  </button>
                ))}
            </>
          ) : (
            <div className="lab-empty">
              <ShieldCheck size={38} />
              <h3>Inspect originals, not a description of them</h3>
              <p>
                The reader displays text extracted from stored pages. Downloaded
                scripts are not executed.
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

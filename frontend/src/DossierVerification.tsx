import { useEffect, useState } from "react";
import { ExternalLink, ChevronDown } from "lucide-react";
import { api } from "./api";
import ScopeAudit from "./ScopeAudit";
export default function DossierVerification({ selectEvidence }: any) {
  const [state, setState] = useState<any>(null),
    [error, setError] = useState(""),
    [expanded, setExpanded] = useState(false),
    [filter, setFilter] = useState("Dossier’s verified list"),
    [page, setPage] = useState(0),
    [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    let alive = true,
      timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const d = await api("/dossiers/verification");
        if (alive) {
          setState(d);
          setError("");
        }
      } catch (e: any) {
        if (alive) setError(e.message);
      }
      if (alive) timer = setTimeout(refresh, 30000);
    }
    refresh();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);
  if (!state?.dossiers?.length)
    return error ? (
      <p className="briefing-error">
        Dossier verification could not load: {error}
      </p>
    ) : null;
  const dossier = state.dossiers[0];
  const claims = dossier.claims.filter((c: any) =>
    filter === "All claims"
      ? true
      : filter === "Dossier’s verified list"
        ? c.subsection.startsWith("10.1")
        : filter === "Has supporting passages"
          ? c.proof.length > 0
          : c.status === "NOT VERIFIED",
  );
  return (
    <section
      className="dossier-verification"
      aria-label="Expanded dossier verification"
    >
      <header>
        <div>
          <span className="case-kicker">YOUR PASTED DOSSIER</span>
          <h2>Which claims have actually been checked?</h2>
          <p>
            {dossier.claim_units} original paragraphs / bullets ·{" "}
            {dossier.counts.SUPPORTED || 0} supported ·{" "}
            {dossier.counts["PARTIALLY SUPPORTED"] || 0} partly supported ·{" "}
            {dossier.counts["NOT VERIFIED"] || 0} not verified
          </p>
        </div>
        <button onClick={() => setExpanded(!expanded)}>
          {expanded ? "Hide claim list" : "Read claim-by-claim verification"}
          <ChevronDown size={15} />
        </button>
      </header>
      <p className="dossier-standard">
        The dossier’s “Verified Facts” label is preserved as its author’s
        assertion. The statuses below reflect source checks in this case.
      </p>
      {dossier.acquisitions?.length > 0 && (
        <details className="dossier-source-status">
          <summary>
            Source acquisition:{" "}
            {
              dossier.acquisitions.filter((j: any) => j.status === "COMPLETE")
                .length
            }{" "}
            acquired ·{" "}
            {
              dossier.acquisitions.filter(
                (j: any) => j.status === "ACQUISITION FAILED",
              ).length
            }{" "}
            failed · {dossier.acquisitions.length} tracked jobs
          </summary>
          {dossier.acquisitions.map((j: any) => (
            <div key={j.id}>
              <p>
                {j.url} · {j.status}
              </p>
              {j.error && <p>{j.error}</p>}
              {j.evidence_id && (
                <button onClick={() => selectEvidence(j.evidence_id)}>
                  Open acquired source <ExternalLink size={12} />
                </button>
              )}
            </div>
          ))}
        </details>
      )}
      <ScopeAudit />
      {expanded && (
        <>
          <div className="dossier-filters">
            {[
              "Dossier’s verified list",
              "Has supporting passages",
              "Not verified",
              "All claims",
            ].map((f) => (
              <button
                key={f}
                className={filter === f ? "selected" : ""}
                onClick={() => {
                  setFilter(f);
                  setPage(0);
                }}
              >
                {f}
              </button>
            ))}
          </div>
          {claims.slice(page * 12, page * 12 + 12).map((c: any) => (
            <article className="dossier-claim" key={c.id}>
              <div>
                <small>
                  {c.subsection || c.section} · source line {c.line}
                </small>
                <span
                  className={
                    c.status === "SUPPORTED" ? "supported" : "unresolved"
                  }
                >
                  {c.status}
                </span>
              </div>
              <h3>{c.text}</h3>
              <p>{c.analysis}</p>
              <button onClick={() => setOpen(open === c.id ? null : c.id)}>
                {c.proof.length
                  ? `Read ${c.proof.length} supporting passage(s) and analysis`
                  : `Show source search leads (${c.candidates.length})`}
                <ChevronDown size={13} />
              </button>
              {open === c.id && (
                <div className="dossier-proof">
                  {c.proof.map((p: any, i: number) => (
                    <blockquote key={i}>
                      <p>{p.quote}</p>
                      <button
                        onClick={() => selectEvidence(p.evidence_id, p.quote)}
                      >
                        {p.title} · {p.location || "Exact source passage"}
                        <ExternalLink size={13} />
                      </button>
                    </blockquote>
                  ))}
                  {!c.proof.length && (
                    <p>
                      No acquired passage currently verifies this complete
                      claim. Search leads below are not proof.
                    </p>
                  )}
                  {c.candidates.map((p: any, i: number) => (
                    <div key={i}>
                      <small>SEARCH LEAD · UNVERIFIED</small>
                      <p>{p.excerpt}</p>
                      <button onClick={() => selectEvidence(p.evidence_id)}>
                        {p.title}
                        <ExternalLink size={13} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </article>
          ))}
          <div className="dossier-pagination">
            <button disabled={!page} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <span>
              {claims.length} claim units · page {page + 1}
            </span>
            <button
              disabled={(page + 1) * 12 >= claims.length}
              onClick={() => setPage(page + 1)}
            >
              Next
            </button>
          </div>
          <button onClick={() => selectEvidence(dossier.evidence_id)}>
            Open the preserved uploaded dossier
            <ExternalLink size={13} />
          </button>
          <p className="dossier-standard">{state.standard}</p>
        </>
      )}
    </section>
  );
}

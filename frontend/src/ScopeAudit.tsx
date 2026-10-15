import { useState } from "react";
import { api } from "./api";
export default function ScopeAudit() {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState("");
  return (
    <details
      className="scope-audit"
      onToggle={async (e) => {
        if (e.currentTarget.open && !data) {
          try {
            setData(await api("/delivery/gaps"));
          } catch (e: any) {
            setError(e.message);
          }
        }
      }}
    >
      <summary>Full thread audit and remaining implementation work</summary>
      {error && <p role="alert">{error}</p>}
      {data ? (
        <>
          <p>
            {data.items.length} requirement groups ·{" "}
            {data.third_party_integrations.length} integrations awaiting
            verification
          </p>
          <p>{data.scope}</p>
          <div className="scope-gap-list">
            {data.items.map((item: any) => (
              <article key={item.id}>
                <div>
                  <strong>
                    {item.id} · {item.requirement}
                  </strong>
                  <span
                    className={
                      item.status === "VERIFIED" ? "supported" : "unresolved"
                    }
                  >
                    {item.status}
                  </span>
                </div>
                <p>{item.remaining}</p>
                <small>Recorded evidence: {item.evidence}</small>
              </article>
            ))}
          </div>
          <h3>Requested integrations still awaiting acceptance</h3>
          <p>
            {data.third_party_integrations.map((t: any) => t.name).join(" · ")}
          </p>
          <p>
            Each needs an authenticity/licence check and a working adapter
            acceptance test.
          </p>
          <p>{data.execution}</p>
          <p>GitHub: {data.github_push}</p>
          <a href="/api/delivery/gaps" target="_blank" rel="noreferrer">
            Open the machine-readable audit
          </a>
        </>
      ) : (
        !error && <p>Reading the saved request audit…</p>
      )}
    </details>
  );
}

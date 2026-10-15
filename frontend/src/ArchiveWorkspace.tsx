import { useEffect, useState } from "react";
import { GitBranch, FileText } from "lucide-react";
import { api, post } from "./api";

export default function ArchiveWorkspace({
  evidence,
  selectEvidence,
  notify,
}: {
  evidence: any[];
  selectEvidence: (id: string) => void;
  notify: (s: string) => void;
}) {
  const archives = evidence
    .filter((e) => e.metadata.source_class === "HISTORICAL ARCHIVE")
    .sort((a, b) =>
      a.metadata.archive_capture_date.localeCompare(
        b.metadata.archive_capture_date,
      ),
    );
  const [leftId, setLeft] = useState(archives[0]?.id || ""),
    [rightId, setRight] = useState(archives.at(-1)?.id || ""),
    [result, setResult] = useState<any>(null),
    [history, setHistory] = useState<any[]>([]),
    [busy, setBusy] = useState(false);
  const left = evidence.find((e) => e.id === leftId),
    right = evidence.find((e) => e.id === rightId);
  const load = () =>
    api("/comparisons")
      .then(setHistory)
      .catch((e) => notify(e.message));
  useEffect(() => {
    load();
  }, []);
  const compare = async () => {
    setBusy(true);
    try {
      setResult(
        await post("/comparisons", { left_id: leftId, right_id: rightId }),
      );
      load();
    } catch (e: any) {
      notify(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="lab-page">
      <div className="lab-heading">
        <div>
          <span className="eyebrow">HISTORICAL ARCHIVE LABORATORY</span>
          <h2>What changed between the captures?</h2>
          <p>
            Compare the text extracted from preserved original responses. A
            changed webpage is a specific observation, not proof that an old
            executable changed.
          </p>
        </div>
      </div>
      <div className="lab-toolbar">
        <select
          aria-label="Earlier preserved version"
          value={leftId}
          onChange={(e) => setLeft(e.target.value)}
        >
          <option value="">Earlier source</option>
          {evidence
            .filter((e) => e.fileUrl && e.text)
            .map((e) => (
              <option key={e.id} value={e.id}>
                {e.metadata.archive_capture_date?.slice(0, 10) ||
                  "Current record"}{" "}
                · {e.title}
              </option>
            ))}
        </select>
        <select
          aria-label="Later preserved version"
          value={rightId}
          onChange={(e) => setRight(e.target.value)}
        >
          <option value="">Later source</option>
          {evidence
            .filter((e) => e.fileUrl && e.text)
            .map((e) => (
              <option key={e.id} value={e.id}>
                {e.metadata.archive_capture_date?.slice(0, 10) ||
                  "Current record"}{" "}
                · {e.title}
              </option>
            ))}
        </select>
        <button
          className="button primary"
          disabled={!leftId || !rightId || leftId === rightId || busy}
          onClick={compare}
        >
          <GitBranch size={14} />
          {busy ? "Verifying originals…" : "Compare & preserve"}
        </button>
      </div>
      <div className="archive-columns">
        {[left, right].map((e, i) => (
          <section key={i}>
            <div className="archive-source">
              <span className="eyebrow">
                {i === 0 ? "EARLIER / LEFT" : "LATER / RIGHT"} SOURCE
              </span>
              <h3>{e?.title || "Select a source"}</h3>
              {e && (
                <>
                  <p>
                    Capture:{" "}
                    {e.metadata.archive_capture_date ||
                      "Not independently known"}
                    <br />
                    Retrieval: {e.metadata.retrieved_utc}
                  </p>
                  <code>SHA-256 {e.sha256}</code>
                  <button
                    className="button"
                    onClick={() => selectEvidence(e.id)}
                  >
                    <FileText size={13} /> Inspect preserved original
                  </button>
                </>
              )}
            </div>
            <pre>{e?.text || "No source selected"}</pre>
          </section>
        ))}
      </div>
      {result && (
        <div className="comparison-result">
          <div className="lab-toolbar">
            <span className="status blue">REPRODUCIBLE TEXT COMPARISON</span>
            <span className="eyebrow">{result.id}</span>
          </div>
          <p className="muted">{result.method}</p>
          <p className="notice">{result.interpretation}</p>
          {result.truncated && (
            <p className="status amber">
              Result truncated; inspect full original records before drawing
              conclusions.
            </p>
          )}
          <pre>
            {result.diff.length
              ? result.diff.map((line: string, i: number) => (
                  <div
                    key={i}
                    className={
                      line.startsWith("+")
                        ? "diff-added"
                        : line.startsWith("-")
                          ? "diff-removed"
                          : ""
                    }
                  >
                    {line || " "}
                  </div>
                ))
              : "No differences in extracted text."}
          </pre>
        </div>
      )}
      <h3 className="history-title">Preserved comparison experiments</h3>
      {history.map((h) => (
        <button
          className="archive-history"
          key={h.id}
          onClick={() => {
            setLeft(h.left_id);
            setRight(h.right_id);
            setResult(h);
          }}
        >
          <GitBranch size={14} />
          <strong>
            {h.capture_dates
              .map((d: string | null) => d?.slice(0, 10) || "Unknown date")
              .join(" → ")}
          </strong>
          <span>{h.created.slice(0, 19).replace("T", " ")} UTC</span>
          <small>
            {h.changed ? "Extracted text differs" : "Same extracted text"}
          </small>
        </button>
      ))}
    </div>
  );
}

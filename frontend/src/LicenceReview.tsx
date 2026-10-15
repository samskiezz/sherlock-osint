import { useState } from "react";
import { post } from "./api";

export default function LicenceReview({ evidence, notify, refresh }: any) {
  const previous = evidence.metadata.licence_review;
  const [permitted, setPermitted] = useState(!!previous?.redistributable);
  const [licence, setLicence] = useState(previous?.licence || "");
  const [basis, setBasis] = useState(previous?.basis || "");
  const [busy, setBusy] = useState(false);
  return (
    <details className="licence-review">
      <summary>
        Archive redistribution review ·{" "}
        {previous?.redistributable
          ? "permitted by recorded review"
          : "original omitted until reviewed"}
      </summary>
      <p>
        Record the source licence or your authority to redistribute this file.
        This assessment controls case ZIP inclusion and leaves the preserved
        original unchanged.
      </p>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          try {
            await post(`/evidence/${evidence.id}/licence-review`, {
              redistributable: permitted,
              licence,
              basis,
            });
            await refresh();
            notify("Licence review saved; original file unchanged");
          } catch (e: any) {
            notify(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Licence or rights status
          <input
            aria-label="Original licence or rights status"
            value={licence}
            onChange={(e) => setLicence(e.target.value)}
            minLength={2}
            maxLength={200}
            required
          />
        </label>
        <label>
          Source and basis for this decision
          <textarea
            aria-label="Redistribution review basis"
            value={basis}
            onChange={(e) => setBasis(e.target.value)}
            minLength={20}
            maxLength={2000}
            required
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={permitted}
            onChange={(e) => setPermitted(e.target.checked)}
          />{" "}
          Redistribution permitted under the recorded basis
        </label>
        <button className="button" disabled={busy} type="submit">
          Save rights assessment
        </button>
      </form>
    </details>
  );
}

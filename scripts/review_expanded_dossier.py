"""Apply explicit, passage-bound reviews to the supplied dossier; leave unsupported claims open."""

import json
import sqlite3
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=60, trust_env=False)
conn = sqlite3.connect(ROOT / "data/case.db")
conn.row_factory = sqlite3.Row
imported = json.loads((ROOT / "artifacts/expanded-dossier-import.json").read_text())
did = imported["dossier"]["id"]
job_ids = [j["id"] for j in imported["source_jobs"]] + json.loads(
    (ROOT / "artifacts/expanded-dossier-official-pdf-jobs.json").read_text()
)
r = client.post("/api/dossiers/" + did + "/sources", json={"job_ids": job_ids})
r.raise_for_status()


def evidence(eid):
    """Read an existing preserved original and its attested text from the case database."""
    return dict(conn.execute("SELECT * FROM evidence WHERE id=?", (eid,)).fetchone())


def passage(eid, start, finish=None, length=500):
    """Select literal source characters; never generate a quotation."""
    e = evidence(eid)
    a = e["text"].index(start)
    b = (
        e["text"].index(finish, a) + len(finish)
        if finish
        else min(len(e["text"]), a + length)
    )
    q = e["text"][a:b]
    return {
        "evidence_id": eid,
        "quote": q,
        "sha256": e["sha256"],
        "location": f"Indexed characters {a}–{b}",
    }


def default_reason(unit):
    """Describe the actual source-coverage limit without claiming an exhaustive external search."""
    section = unit["section"]
    if section.startswith("2."):
        return "Source-coverage review: the acquired Caltech records name Cole Allen, but the complete biographical, degree, identity and employment assertions here are not independently established by that caption. No original degree/resume/employer record is attached to this whole paragraph."
    if section.startswith("4."):
        return "Source-coverage review: the official DOJ announcement, complaint and affidavit are preserved; they record allegations rather than a finding of guilt. The supplied CourtListener transcript pages returned HTTP 403. This full claim is not verified by a court transcript, original court audio or examined incident video in this vault."
    if section.startswith("5."):
        return "Source-coverage review: no original X post, independently dated pre-event capture or account-ownership history has been acquired. Preserved news accounts and decoding an identifier format cannot authenticate the historical text, ownership or alleged prediction."
    if section.startswith("6."):
        return "Source-coverage review: official CORDIS grant 820323 and the project website are preserved. This complete paragraph still requires a specific review of its dates, leadership, stakeholders or asserted absence of connections; the project name alone establishes no physical time-travel capability."
    if section.startswith("7."):
        return "Source-coverage review: case-specific original police, autopsy, missing-person and scientific collaboration records are not attached to this whole claim. A shared institution, surname or reported date does not establish a common team or cause."
    if section.startswith("8.") or unit["subsection"].startswith("3.5"):
        return "Source-coverage review: original alloy patents are preserved, but a complete claim about performance, inventor identity, family history or rocket deployment requires exact supporting passages. Patent disclosure is distinct from an independent replication or commercial demonstration."
    if section.startswith("9."):
        return "Source-coverage review: the AFP fact-check is preserved. It does not independently verify every named image or celebrity association in this paragraph; this system has not run a SynthID test on an acquired original Guthrie image."
    return "Source-coverage review: the entire supplied paragraph/bullet is not established by an attached original-source review. Its original wording and source line are retained. Candidate search matches are research leads, not verification."


assessments = []
for row in conn.execute(
    "SELECT id,data FROM dossier_claims WHERE dossier_id=? ORDER BY sequence", (did,)
):
    unit = json.loads(row["data"])
    text = unit["text"]
    status = "NOT VERIFIED"
    proof = []
    analysis = default_reason(unit)
    if "71.5 percent nickel" in text:
        status = "PARTIALLY SUPPORTED"
        proof = [
            passage(
                "EV-2bc448c8a80b",
                "An alloy having the weight percent composition of 71.5",
                "results of the test of Example 1 are plotted in FIG. 1 at data point Ex. 1.",
            )
        ]
        analysis = "The original patent gives this composition as Example 1 and reports tensile-strength/burn-resistance testing. The added claim that it survives “10 times the heat” is not substantiated by this passage. No independent temperature-performance test or defined heat comparison is supplied. This compound paragraph is only partly supported."
    elif "Monica Jacinto and Dallis Hardwick co-invented Mondaloy" in text:
        status = "PARTIALLY SUPPORTED"
        proof = [
            passage(
                "EV-1c1c3aa4469a",
                "Inventor\nMonica A. Jacinto\nDallis Ann Hardwick",
                "Current Assignee",
            )
        ]
        analysis = "The preserved patent lists Monica A. Jacinto and Dallis Ann Hardwick as inventors. This verifies the printed inventor attribution; it does not by itself authenticate the broader Mondaloy development story, the Reza/Jacinto identity merge, disappearance claims or a common research team."
    elif text.startswith("Allen developed and released the game Bohrdom"):
        status = "PARTIALLY SUPPORTED"
        proof = [
            passage("EV-18a41312505e", '"developers": [', '"package_groups"'),
            passage("EV-18a41312505e", '"release_date": {', '"support_info"'),
        ]
        analysis = "The actual Steam API response lists developer/publisher “Cole Allen” and release date Dec 20, 2018. This confirms those platform fields. It does not independently resolve the developer name to the individual accused in the criminal case."
    elif text.startswith(
        "Cole Tomas Allen, 31, of Torrance, California, is the suspect"
    ):
        status = "SUPPORTED"
        proof = [
            passage(
                "EV-b9bbec3555f4",
                "Cole\u00a0Tomas\u00a0Allen",
                "announced the Department of Justice.",
            )
        ]
        analysis = "The original DOJ release identifies the named 31-year-old Torrance defendant and the April 25, 2026 dinner shooting. This supports the suspect/charge identification, not guilt or the unrelated scientific hypotheses."
    elif text.startswith("According to court documents, Allen made a reservation"):
        status = "SUPPORTED"
        proof = [
            passage(
                "EV-b9bbec3555f4",
                "According to court documents, on April 6, 2026",
                "checked into the Washington Hilton later that day.",
            )
        ]
        analysis = "The preserved DOJ account explicitly attributes the reservation, train itinerary and arrival details to court documents. This verifies the dossier’s attribution to the court account, not an independent adjudication of those allegations."
    elif text.startswith(
        "According to the Justice Department press release, Allen was charged by complaint"
    ):
        status = "SUPPORTED"
        proof = [
            passage(
                "EV-b9bbec3555f4",
                "Allen\u00a0is charged\u00a0by",
                "The attempted assassination",
            )
            if "The attempted assassination" in evidence("EV-b9bbec3555f4")["text"]
            else passage(
                "EV-b9bbec3555f4", "Allen\u00a0is charged\u00a0by", length=1000
            ),
            passage(
                "EV-515b67cc6c69",
                "18 U.S.C. § 1751(c)",
                "See attached Statement of Facts.",
            ),
        ]
        analysis = "The actual DOJ-hosted complaint lists the three cited offenses, and the preserved press release reports the charge and possible life sentence. These are charges, not convictions."
    elif text.startswith("Allen purchased a Maverick 12-gauge shotgun"):
        status = "PARTIALLY SUPPORTED"
        proof = [
            passage(
                "EV-c6d4cfb2872e",
                "database records showed that on",
                "a different city in California.",
            )
        ]
        analysis = "The original affidavit reports a 12-gauge pump-action shotgun purchase on August 17, 2025. This passage does not name Maverick. The brand-specific bullet is therefore only partly supported, and the source is an investigative affidavit."
    elif (
        text.startswith(
            "The EU Time Machine project is a historical digitisation initiative"
        )
        or unit["subsection"].startswith("6.1")
        and "replicate the VTM" in text
    ):
        status = "PARTIALLY SUPPORTED"
        proof = [
            passage(
                "EV-fe5e7358c427",
                "Coordinated by\nECOLE POLYTECHNIQUE FEDERALE DE LAUSANNE",
                length=100,
            ),
            passage(
                "EV-fe5e7358c427",
                "Technology brings history to life",
                "creating new jobs.",
            ),
        ]
        analysis = "The European Commission’s own CORDIS record identifies EPFL as coordinator and describes digitising historical/geographical/museum/library archives. It supports a historical-data project, not physical time travel. The complete surrounding wording about flagship status, quantum programmes or absence of every case connection is not independently established by these passages."
    elif unit["subsection"].startswith("6.1") and "€1 million" in text:
        status = "PARTIALLY SUPPORTED"
        proof = [
            passage("EV-fe5e7358c427", "€ 997 930,00", length=60),
            passage(
                "EV-fe5e7358c427",
                "EC signature date",
                "EXCELLENT SCIENCE - Future and Emerging Technologies (FET)",
            ),
        ]
        analysis = "CORDIS gives an EU contribution of €997,930 and dates in 2019–2020, supporting “about €1 million”. It does not by itself substantiate the complete claim about six shortlisted candidates, sixteen applications or the December 2018 selection announcement."
    elif text.startswith("An AFP investigation found that more than 50 public figures"):
        status = "PARTIALLY SUPPORTED"
        proof = [
            passage(
                "EV-4c21397188dc",
                "In addition to Guthrie, an AFP investigation",
                "Chris Brown\n.",
            )
        ]
        analysis = "The preserved AFP article reports more than 50 false associations and names Hanks, Sweeney and Brown. The paragraph’s additional quoted description of Facebook is not verified by this passage; this is a source report, not this system independently testing every image."
    elif text.startswith("Google's SynthID detection tool identified"):
        status = "PARTIALLY SUPPORTED"
        proof = [
            passage(
                "EV-4c21397188dc",
                "Google's SynthID detection tool identified",
                "here\n).",
            )
        ]
        analysis = "AFP reports that Google’s tool identified a SynthID watermark. The article is preserved, but this system has not acquired the original image and independently reproduced the watermark test. The result remains source-attributed."
    value = {
        "status": status,
        "analysis": analysis,
        "proof": proof,
        "origin": "AI-assisted source review"
        if proof
        else "AI-assisted source-coverage assessment",
    }
    response = client.post("/api/dossiers/claims/" + row["id"] + "/review", json=value)
    if response.status_code != 200:
        raise RuntimeError((row["id"], response.status_code, response.text[:300]))
    assessments.append(
        {
            "claim_id": row["id"],
            "status": status,
            "proof_ids": [p["evidence_id"] for p in proof],
        }
    )
report = client.get("/api/dossiers/verification").json()
(ROOT / "artifacts/expanded-dossier-verification.json").write_text(
    json.dumps(report, indent=2)
)
print(
    "Reviewed source coverage for",
    len(assessments),
    "claim units:",
    report["dossiers"][0]["counts"],
)

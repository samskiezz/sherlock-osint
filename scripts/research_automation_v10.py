"""Collect primary public technical documentation; preserve HTTP outcomes and hashes."""

import concurrent.futures
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "scipy-stats": "https://docs.scipy.org/doc/scipy/reference/stats.html",
    "scipy-distance": "https://docs.scipy.org/doc/scipy/reference/spatial.distance.html",
    "scipy-signal": "https://docs.scipy.org/doc/scipy/reference/signal.html",
    "networkx": "https://networkx.org/documentation/stable/reference/algorithms/index.html",
    "sklearn-clustering": "https://scikit-learn.org/stable/modules/clustering.html",
    "sklearn-classification": "https://scikit-learn.org/stable/supervised_learning.html",
    "sklearn-text": "https://scikit-learn.org/stable/modules/feature_extraction.html#text-feature-extraction",
    "sklearn-evaluation": "https://scikit-learn.org/stable/modules/model_evaluation.html",
    "sklearn-pitfalls": "https://scikit-learn.org/stable/common_pitfalls.html",
    "ollama-structured": "https://docs.ollama.com/capabilities/structured-outputs",
    "ollama-embeddings": "https://docs.ollama.com/capabilities/embeddings",
    "nist-hashes": "https://csrc.nist.gov/pubs/fips/180-4/upd1/final",
    "python-text": "https://docs.python.org/3/library/text.html",
    "python-difflib": "https://docs.python.org/3/library/difflib.html",
    "python-unicode": "https://docs.python.org/3/library/unicodedata.html",
    "croniter": "https://github.com/pallets-eco/croniter",
    "pydantic": "https://docs.pydantic.dev/latest/concepts/models/",
    "sqlite-transactions": "https://www.sqlite.org/lang_transaction.html",
    "berkeley-protocol": "https://www.ohchr.org/sites/default/files/2022-04/OHCHR_BerkeleyProtocol.pdf",
    "nist-forensics": "https://nvlpubs.nist.gov/nistpubs/legacy/sp/nistspecialpublication800-86.pdf",
}


def fetch(item):
    """Fetch a fixed public primary reference, never execute its contents."""
    key, url = item
    stamp = datetime.now(timezone.utc).isoformat()
    record = {
        "id": key,
        "url": url,
        "retrieved_utc": stamp,
        "purpose": "Engineering reference; not case evidence or proof of effectiveness",
    }
    try:
        with httpx.Client(timeout=35, follow_redirects=True) as client:
            r = client.get(
                url, headers={"User-Agent": "SHERLOCK-OSINT/0.10 documentation review"}
            )
        record.update(
            status=r.status_code,
            final_url=str(r.url),
            mime=r.headers.get("content-type"),
            bytes=len(r.content),
        )
        if r.status_code == 200 and len(r.content) <= 16_000_000:
            file = (
                ROOT
                / "artifacts/automation-research-v10"
                / (key + (".pdf" if r.content.startswith(b"%PDF") else ".html"))
            )
            file.write_bytes(r.content)
            record.update(
                sha256=hashlib.sha256(r.content).hexdigest(),
                file=str(file.relative_to(ROOT)),
                acquisition="ACQUIRED",
            )
            if file.suffix == ".html":
                soup = BeautifulSoup(r.content, "html.parser")
                record["title"] = (
                    soup.title.get_text(" ", strip=True) if soup.title else key
                )
                record["headings"] = [
                    x.get_text(" ", strip=True) for x in soup.select("h1,h2,h3")
                ][:100]
        else:
            record["acquisition"] = "NOT ACQUIRED"
    except Exception as ex:
        record.update(acquisition="ACQUISITION FAILED", error=type(ex).__name__)
    return record


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        data = list(pool.map(fetch, SOURCES.items()))
    (ROOT / "artifacts/automation-research-v10.json").write_text(
        json.dumps(data, indent=2)
    )
    print(
        json.dumps(
            {
                "references": len(data),
                "acquired": sum(r.get("acquisition") == "ACQUIRED" for r in data),
                "failed": [r["id"] for r in data if r.get("acquisition") != "ACQUIRED"],
            }
        )
    )

"""Durable Celery collector using a bounded, reviewed Sherlock adapter."""

import csv
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.robotparser import RobotFileParser
from typing import Any
import httpx
from celery import Celery
from sqlalchemy import select
from . import config
from .models import Session, CollectionJob, Evidence, utcnow
from .audit import record

celery = Celery(
    "sherlock-foundation", broker=config.BROKER, backend=config.RESULT_BACKEND
)
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=110,
    task_time_limit=120,
    broker_transport_options={"visibility_timeout": 300},
    result_expires=86400,
)


def collect_public_username(username: str) -> dict[str, Any]:
    """Run Sherlock on one explicit public site after robots checks; preserve the real response."""
    url = "https://github.com/" + username
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        robots = client.get("https://github.com/robots.txt")
        if robots.status_code not in (200, 404):
            raise ValueError(f"Robots unavailable: HTTP {robots.status_code}")
        parser = RobotFileParser()
        parser.parse(robots.text.splitlines() if robots.status_code == 200 else [])
        if robots.status_code == 200 and not parser.can_fetch("SherlockOSINT", url):
            raise ValueError("Robots disallows this public profile")
        response = client.get(url)
        if response.status_code in (401, 403, 429):
            raise ValueError(
                f"Public profile access restricted: HTTP {response.status_code}"
            )
        if response.status_code not in (200, 404):
            raise ValueError(
                f"Unexpected profile response: HTTP {response.status_code}"
            )
        captured = response.content
        if len(captured) > 2 * 1024 * 1024:
            raise ValueError("Public profile exceeds 2 MiB adapter budget")
    with tempfile.TemporaryDirectory(prefix="sherlock-username-") as folder:
        folder = Path(folder)
        sites = folder / "sites.json"
        sites.write_text(
            json.dumps(
                {
                    "GitHub": {
                        "urlMain": "https://github.com/",
                        "url": "https://github.com/{}",
                        "errorType": "status_code",
                        "errorMsg": "404",
                        "username_claimed": "sherlock-project",
                        "username_unclaimed": "a-very-unlikely-unclaimed-name-593017",
                    }
                }
            )
        )
        env = os.environ.copy()
        for key in config.KEYS:
            env.pop(key, None)
        env.pop("SHERLOCK_FOUNDATION_ENV", None)
        env["PYTHONUNBUFFERED"] = "1"
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "sherlock_project",
                username,
                "--json",
                str(sites),
                "--site",
                "GitHub",
                "--timeout",
                "15",
                "--no-color",
                "--csv",
                "--output",
                str(folder / "result.txt"),
            ],
            cwd=folder,
            env=env,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if process.returncode:
            raise ValueError(
                "Sherlock execution failed; no positive profile assertion made"
            )
        csv_files = list(folder.glob("*.csv"))
        if not csv_files:
            raise ValueError("Sherlock did not create its expected CSV artefact")
        table = csv_files[0].read_text()[:100000]
    # Upload original bytes through the existing isolated acquisition/processing boundary.
    with httpx.Client(
        base_url=config.CORE_URL,
        headers=config.CORE_HEADERS,
        trust_env=False,
        timeout=100,
    ) as client:
        queued = client.post(
            "/api/jobs",
            json={"url": url, "title": "Public profile response · " + username},
        )
        queued.raise_for_status()
        acquisition = queued.json()
        import time

        for _ in range(70):
            jobs = client.get("/api/jobs").json()
            state = next(j for j in jobs if j["id"] == acquisition["id"])
            if state["status"] == "COMPLETE":
                original_response = client.get("/api/evidence/" + state["evidence_id"])
                original_response.raise_for_status()
                original = original_response.json()
                break
            if state["status"] in ("FAILED", "ACQUISITION FAILED"):
                raise ValueError(
                    "Original acquisition failed: " + str(state.get("error", ""))[:200]
                )
            time.sleep(1)
        else:
            raise ValueError(
                "Original acquisition did not finish inside the worker budget"
            )
        receipt = {
            "source_url": url,
            "http_status": response.status_code,
            "sherlock_version": "0.16.2",
            "csv": table,
            "attribution": "UNVERIFIED ATTRIBUTION; username availability does not establish account ownership",
            "original_evidence_id": original["id"],
            "sha256": original["sha256"],
            "byte_size": original["size"],
            "acquisition_status": original["status"],
            "original_provenance": {
                k: original["metadata"].get(k)
                for k in (
                    "original_url",
                    "final_url",
                    "retrieved_utc",
                    "retrieval_method",
                    "licence",
                    "response_status",
                    "network_transport",
                )
            },
            "observation_saved_utc": utcnow().isoformat(),
            "site_budget": 1,
        }
        note = client.post(
            "/api/annotations",
            json={
                "title": f"Public username observation · {username}",
                "text": json.dumps(receipt, indent=2),
                "citations": [],
            },
        )
        note.raise_for_status()
    return receipt


@celery.task(name="sherlock.collect_username", bind=True)
def collect_username(self: Any, job_id: str) -> dict[str, Any]:
    """Claim a persistent job once and save actual artefacts or an explicit failure."""
    with Session.begin() as s:
        job = s.execute(
            select(CollectionJob).where(CollectionJob.id == job_id).with_for_update()
        ).scalar_one()
        if job.status in ("COMPLETE", "FAILED"):
            return {"id": job_id, "status": job.status, "deduplicated": True}
        from datetime import timezone

        updated = (
            job.updated.replace(tzinfo=timezone.utc)
            if job.updated.tzinfo is None
            else job.updated
        )
        if job.status == "RUNNING" and (utcnow() - updated).total_seconds() < 300:
            return {"id": job_id, "status": "RUNNING", "deduplicated": True}
        job.status = "RUNNING"
        job.updated = utcnow()
        username = job.username
        case_id = job.case_id
        record(s, None, "collection_started", {"job_id": job_id, "site_budget": 1})
    try:
        result = collect_public_username(username)
        with Session.begin() as s:
            job = s.get(CollectionJob, job_id)
            job.status = "COMPLETE"
            job.result = result
            job.updated = utcnow()
            eid = result["original_evidence_id"]
            from sqlalchemy.dialects.postgresql import insert

            s.execute(
                insert(Evidence)
                .values(
                    id=eid,
                    case_id=case_id,
                    title="Public GitHub profile response · " + username,
                    status=result["acquisition_status"],
                    byte_size=result["byte_size"],
                    sha256=result["sha256"],
                    source_url=result["source_url"],
                    provenance=result,
                )
                .on_conflict_do_nothing(index_elements=[Evidence.id])
            )
            record(
                s,
                None,
                "collection_completed",
                {"job_id": job_id, "evidence_id": eid, "sha256": result["sha256"]},
            )
        return {"id": job_id, "status": "COMPLETE", "evidence_id": eid}
    except Exception as ex:
        # Error text is bounded and avoids URLs containing configured credentials.
        reason = (
            str(ex)[:500]
            if isinstance(ex, ValueError)
            else f"HTTP {ex.response.status_code} at internal {ex.request.url.path}"
            if isinstance(ex, httpx.HTTPStatusError)
            else type(ex).__name__
        )
        with Session.begin() as s:
            job = s.get(CollectionJob, job_id)
            job.status = "FAILED"
            job.error = reason
            job.updated = utcnow()
            record(s, None, "collection_failed", {"job_id": job_id, "reason": reason})
        return {"id": job_id, "status": "FAILED", "reason": reason}


def dispatch() -> int:
    """Publish the PostgreSQL outbox after commit; row locks prevent duplicate dispatchers."""
    count = 0
    with Session.begin() as s:
        from datetime import timedelta

        stale = s.scalars(
            select(CollectionJob)
            .where(
                CollectionJob.status.in_(("RUNNING", "DISPATCHED")),
                CollectionJob.updated < utcnow() - timedelta(seconds=300),
            )
            .with_for_update(skip_locked=True)
        ).all()
        for job in stale:
            job.status = "QUEUED"
            record(s, None, "collection_lease_recovered", {"job_id": job.id})
        jobs = s.scalars(
            select(CollectionJob)
            .where(CollectionJob.status == "QUEUED")
            .with_for_update(skip_locked=True)
            .limit(10)
        ).all()
        for job in jobs:
            collect_username.apply_async(args=[job.id], task_id=job.id)
            job.status = "DISPATCHED"
            job.updated = utcnow()
            count += 1
    return count

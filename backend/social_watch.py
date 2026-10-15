"""Official X API v2 collection with durable cursors, provenance and visible access limits."""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field, ConfigDict

API = "https://api.x.com/2"


class Feed(BaseModel):
    """An explicit public-query feed; no private-account access or credential probing."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    query: str = Field(min_length=1, max_length=512)
    mode: Literal["recent", "full_archive", "filtered_stream"] = "recent"
    interval_seconds: int = Field(default=120, ge=60, le=86400)
    acquire_media: bool = False


def normalise_posts(payload: dict) -> list[dict]:
    """Interpret API fields literally; author IDs are not verified real-world identities."""
    users = {
        u["id"]: u
        for u in payload.get("includes", {}).get("users", [])
        if isinstance(u, dict) and "id" in u
    }
    media = {
        m["media_key"]: m
        for m in payload.get("includes", {}).get("media", [])
        if isinstance(m, dict) and "media_key" in m
    }
    records = payload.get("data", [])
    if isinstance(records, dict):
        records = [records]
    result = []
    for post in records[:100]:
        if (
            not isinstance(post, dict)
            or not str(post.get("id", "")).isdigit()
            or not isinstance(post.get("text"), str)
        ):
            continue
        author = users.get(post.get("author_id"), {})
        result.append(
            {
                "id": str(post["id"]),
                "text": post["text"],
                "author_id": post.get("author_id"),
                "username_reported": author.get("username"),
                "post_created_at_reported": post.get("created_at"),
                "public_metrics_reported": post.get("public_metrics", {}),
                "edit_history_tweet_ids": post.get("edit_history_tweet_ids", []),
                "referenced_tweets": post.get("referenced_tweets", []),
                "url": "https://x.com/i/web/status/" + str(post["id"]),
                "media": [
                    media[k]
                    for k in post.get("attachments", {}).get("media_keys", [])
                    if k in media
                ],
                "attribution": "PLATFORM REPORTED; no real-world identity merge; historical ownership and pre-event publication require independent evidence",
            }
        )
    return result


def install(core: Any) -> dict:
    """Install restart-safe polling/stream adapters and source-preserving post ingestion."""
    with core.db() as db:
        db.executescript("""
CREATE TABLE IF NOT EXISTS social_feeds(id TEXT PRIMARY KEY,created TEXT,enabled INTEGER,next_due REAL,data TEXT);
CREATE TABLE IF NOT EXISTS social_polls(id TEXT PRIMARY KEY,feed_id TEXT,created TEXT,status TEXT,data TEXT);
CREATE TABLE IF NOT EXISTS social_posts(id TEXT PRIMARY KEY,created TEXT,source_evidence_id TEXT,data TEXT);
CREATE TABLE IF NOT EXISTS social_observations(post_id TEXT,evidence_id TEXT,created TEXT,data TEXT,PRIMARY KEY(post_id,evidence_id));
CREATE TABLE IF NOT EXISTS social_feed_posts(feed_id TEXT,post_id TEXT,PRIMARY KEY(feed_id,post_id));
""")
    feed_locks = {}
    guard = threading.Lock()
    stream_slot = threading.BoundedSemaphore(1)

    def ingest(fid: str, payload: dict, raw: bytes, url: str) -> dict:
        """Preserve the exact API response before interpreting any reported post fields."""
        if len(raw) > 10 * 1024**2:
            raise ValueError("X response exceeds 10 MB")
        eid = core.preserve(
            raw,
            "X API capture · " + fid,
            url,
            {"content-type": "application/json"},
            "Official X API v2; app-authorised public source capture",
        )
        core.process(eid)
        posts = normalise_posts(payload)
        config = json.loads(
            core.rows("SELECT data FROM social_feeds WHERE id=?", (fid,))[0]["data"]
        )
        for post in posts:
            core.execute(
                "INSERT OR IGNORE INTO social_observations VALUES(?,?,?,?)",
                (post["id"], eid, core.now(), json.dumps(post)),
            )
            core.execute(
                "INSERT INTO social_posts VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET source_evidence_id=excluded.source_evidence_id,data=excluded.data",
                (post["id"], core.now(), eid, json.dumps(post)),
            )
            core.execute(
                "INSERT OR IGNORE INTO social_feed_posts VALUES(?,?)", (fid, post["id"])
            )
            if config.get("acquire_media"):
                for media in post["media"][:4]:
                    url = (
                        media.get("url")
                        if media.get("type") == "photo"
                        else media.get("preview_image_url")
                    )
                    if url:
                        try:
                            if hasattr(core, "media_reports"):
                                core.media_reports["register"](
                                    url,
                                    {
                                        "kind": "X_PLATFORM_MEDIA_ATTACHMENT",
                                        "feed_id": fid,
                                        "parent_evidence_id": eid,
                                        "post_url": post["url"],
                                        "post_id": post["id"],
                                        "post_created_at_reported": post.get(
                                            "post_created_at_reported"
                                        ),
                                        "attribution": "Platform attachment in preserved API response; no identity or historical ownership verification",
                                    },
                                )
                            core.queue(
                                core.Acquire(
                                    url=url, title="X public media · post " + post["id"]
                                )
                            )
                        except Exception as ex:
                            core.log(
                                "social_media_acquisition_failed",
                                {"post_id": post["id"], "error": type(ex).__name__},
                            )
        return {
            "source_evidence_id": eid,
            "post_ids": [p["id"] for p in posts],
            "posts_received": len(posts),
        }

    def poll(fid: str) -> dict:
        """Collect bounded pages or a bounded live stream session without erasing other rules."""
        with guard:
            gate = feed_locks.setdefault(fid, threading.Lock())
        if not gate.acquire(blocking=False):
            return {"status": "ALREADY_RUNNING"}
        try:
            rows = core.rows("SELECT * FROM social_feeds WHERE id=?", (fid,))
            if not rows:
                raise HTTPException(404, "X feed not found")
            data = json.loads(rows[0]["data"])
            rid = core.uid("X-POLL")
            out = {"posts_received": 0, "captures": []}
            token = os.environ.get("X_BEARER_TOKEN", "")
            state = "COMPLETE"
            backoff = data.get("interval_seconds", 120)
            try:
                if not token:
                    state = "NOT_CONFIGURED"
                    out["reason"] = (
                        "X_BEARER_TOKEN is not configured. A permitted X developer account and endpoint access are required; no live feed or internet-wide X coverage is claimed."
                    )
                else:
                    with httpx.Client(
                        timeout=httpx.Timeout(35, read=30),
                        headers={"Authorization": "Bearer " + token},
                    ) as client:
                        mode = data.get("mode", "recent")
                        params = {
                            "tweet.fields": "created_at,author_id,public_metrics,attachments,edit_history_tweet_ids,referenced_tweets",
                            "expansions": "author_id,attachments.media_keys",
                            "user.fields": "username,name",
                            "media.fields": "url,preview_image_url,type,width,height",
                        }
                        if mode == "filtered_stream":
                            # Add only this feed's tagged rule; never delete or replace another application's rules.
                            rules = client.get(API + "/tweets/search/stream/rules")
                            rules.raise_for_status()
                            tag = "sherlock:" + fid
                            owned_rules = {
                                str(r["id"])
                                for r in rules.json().get("data", [])
                                if r.get("tag") == tag
                                and r.get("value") == data["query"]
                            }
                            if not owned_rules:
                                added = client.post(
                                    API + "/tweets/search/stream/rules",
                                    json={
                                        "add": [{"value": data["query"], "tag": tag}]
                                    },
                                )
                                added.raise_for_status()
                                if added.json().get("errors"):
                                    raise ValueError(
                                        "X rejected the supplied stream rule"
                                    )
                                owned_rules = {
                                    str(r["id"])
                                    for r in added.json().get("data", [])
                                    if r.get("tag") == tag
                                }
                            if not owned_rules:
                                raise ValueError(
                                    "X did not confirm the owned stream rule identifier"
                                )
                            if not stream_slot.acquire(blocking=False):
                                raise ValueError(
                                    "One filtered-stream session is already running"
                                )
                            try:
                                started = time.monotonic()
                                with client.stream(
                                    "GET", API + "/tweets/search/stream", params=params
                                ) as response:
                                    response.raise_for_status()
                                    for line in response.iter_lines():
                                        if (
                                            core.stopping.is_set()
                                            or time.monotonic() - started > 40
                                        ):
                                            break
                                        if not line:
                                            continue
                                        payload = json.loads(line)
                                        if not any(
                                            str(r.get("id")) in owned_rules
                                            for r in payload.get("matching_rules", [])
                                        ):
                                            out["other_rule_messages_ignored"] = (
                                                out.get(
                                                    "other_rule_messages_ignored", 0
                                                )
                                                + 1
                                            )
                                            continue
                                        capture = ingest(
                                            fid,
                                            payload,
                                            line.encode(),
                                            str(response.url),
                                        )
                                        out["captures"].append(capture)
                                        out["posts_received"] += capture[
                                            "posts_received"
                                        ]
                                        if len(out["captures"]) >= 50:
                                            break
                            finally:
                                stream_slot.release()
                        else:
                            endpoint = (
                                API
                                + "/tweets/search/"
                                + ("all" if mode == "full_archive" else "recent")
                            )
                            params.update(query=data["query"], max_results=100)
                            if data.get("since_id"):
                                params["since_id"] = data["since_id"]
                            if data.get("next_token"):
                                params["next_token"] = data["next_token"]
                            for _ in range(2):
                                response = client.get(endpoint, params=params)
                                response.raise_for_status()
                                raw = response.content
                                payload = response.json()
                                if payload.get("errors") and not payload.get("data"):
                                    raise ValueError(
                                        "X API returned errors without post data"
                                    )
                                capture = ingest(fid, payload, raw, str(response.url))
                                out["captures"].append(capture)
                                out["posts_received"] += capture["posts_received"]
                                newest = payload.get("meta", {}).get("newest_id")
                                if newest and (
                                    not data.get("pending_newest")
                                    or int(newest) > int(data["pending_newest"])
                                ):
                                    data["pending_newest"] = newest
                                next_token = payload.get("meta", {}).get("next_token")
                                data["next_token"] = next_token
                                if not next_token:
                                    if data.get("pending_newest"):
                                        data["since_id"] = data.pop("pending_newest")
                                    break
                                params["next_token"] = next_token
                            out["pagination_pending"] = bool(data.get("next_token"))
            except httpx.HTTPStatusError as ex:
                code = ex.response.status_code
                state = (
                    "RATE_LIMITED"
                    if code == 429
                    else "ACCESS_DENIED"
                    if code in (401, 403)
                    else "HTTP_FAILED"
                )
                out.update(
                    http_status=code,
                    reason="X API access/rate/plan restriction; inspect the permitted endpoint entitlement. Authentication headers are never recorded.",
                )
                if code == 429:
                    try:
                        backoff = max(
                            backoff,
                            min(
                                86400,
                                int(ex.response.headers.get("x-rate-limit-reset", "0"))
                                - int(time.time()),
                            ),
                        )
                    except ValueError:
                        backoff = max(backoff, 900)
            except httpx.ReadTimeout:
                state = "IDLE_TIMEOUT"
                out["reason"] = (
                    "Stream read timed out; retained posts remain preserved and the session will reconnect."
                )
            except Exception as ex:
                state = "FAILED"
                out["reason"] = str(ex)[:500]
            data.update(
                last_status=state, last_checked_utc=core.now(), last_poll_id=rid
            )
            core.execute(
                "INSERT INTO social_polls VALUES(?,?,?,?,?)",
                (rid, fid, core.now(), state, json.dumps(out)),
            )
            delay = (
                1
                if data.get("mode") == "filtered_stream"
                and state in ("COMPLETE", "IDLE_TIMEOUT")
                else max(60, backoff)
            )
            core.execute(
                "UPDATE social_feeds SET next_due=?,data=? WHERE id=?",
                (time.time() + delay, json.dumps(data), fid),
            )
            core.log(
                "social_feed_poll",
                {
                    "feed_id": fid,
                    "status": state,
                    "posts_received": out["posts_received"],
                },
            )
            return {"id": rid, "status": state, **out}
        finally:
            gate.release()

    class ImportRecord(BaseModel):
        evidence_id: str = Field(min_length=1, max_length=100)

    @core.app.post("/api/social/import")
    def import_records(value: ImportRecord) -> dict:
        """Analyse an acquired API JSON capture or user-authorised X archive without executing it."""
        try:
            evidence, metadata, digest = core.forensics["source"](value.evidence_id)
            text = evidence["text"]
            if len(text) > 10 * 1024**2:
                raise ValueError(
                    "Imported X dataset exceeds 10 MB; use bounded export parts"
                )
            if text.lstrip().startswith("window.YTD."):
                text = text.split("=", 1)[1].strip().rstrip(";")
            payload = json.loads(text)
            if isinstance(payload, list):
                if len(payload) > 10000:
                    raise ValueError("Import is limited to 10,000 records per source")
                records = []
                for item in payload:
                    row = item.get("tweet", item)
                    if not isinstance(row, dict):
                        continue
                    records.append(
                        {
                            "id": str(row.get("id_str", row.get("id", ""))),
                            "text": row.get("full_text", row.get("text", "")),
                            "author_id": row.get("user_id_str"),
                            "created_at": row.get("created_at"),
                            "edit_history_tweet_ids": row.get(
                                "edit_history_tweet_ids", []
                            ),
                        }
                    )
                payload = {"data": records}
            if not isinstance(payload, dict) or not isinstance(
                payload.get("data"), list
            ):
                raise ValueError(
                    "Use an X API JSON response or a user-authorised tweets archive part"
                )
            if len(payload["data"]) > 10000:
                raise ValueError("Import is limited to 10,000 records")
            fid = core.uid("X-IMPORT")
            core.execute(
                "INSERT INTO social_feeds VALUES(?,?,?,?,?)",
                (
                    fid,
                    core.now(),
                    0,
                    time.time(),
                    json.dumps(
                        {
                            "name": "Imported authorised dataset",
                            "query": "imported source",
                            "mode": "import",
                            "interval_seconds": 120,
                        }
                    ),
                ),
            )
            count = 0
            records = payload["data"]
            if len(records) > 10000:
                raise ValueError("Import is limited to 10,000 records")
            for offset in range(0, len(records), 100):
                chunk = {**payload, "data": records[offset : offset + 100]}
                for post in normalise_posts(chunk):
                    post["attribution"] = (
                        "USER-SUPPLIED ACQUIRED DATASET / NOT A LIVE X API OBSERVATION; claimed timestamps and account attribution require source verification"
                    )
                    core.execute(
                        "INSERT OR IGNORE INTO social_observations VALUES(?,?,?,?)",
                        (post["id"], value.evidence_id, core.now(), json.dumps(post)),
                    )
                    core.execute(
                        "INSERT INTO social_posts VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET source_evidence_id=excluded.source_evidence_id,data=excluded.data",
                        (post["id"], core.now(), value.evidence_id, json.dumps(post)),
                    )
                    core.execute(
                        "INSERT OR IGNORE INTO social_feed_posts VALUES(?,?)",
                        (fid, post["id"]),
                    )
                    count += 1
            core.log(
                "social_dataset_imported",
                {
                    "feed_id": fid,
                    "source_evidence_id": value.evidence_id,
                    "posts": count,
                },
            )
            return {
                "feed_id": fid,
                "source_evidence_id": value.evidence_id,
                "posts_imported": count,
                "live_collection": False,
                "source_sha256": evidence["sha256"],
            }
        except (ValueError, TypeError, KeyError) as ex:
            raise HTTPException(422, str(ex)) from ex

    @core.app.get("/api/social")
    def overview() -> dict:
        """Report actual access readiness and stored coverage, never claim a global firehose."""
        return {
            "configured": bool(os.environ.get("X_BEARER_TOKEN")),
            "provider": "Official X API v2",
            "feeds": [
                {**r, "data": json.loads(r["data"])}
                for r in core.rows("SELECT * FROM social_feeds ORDER BY created DESC")
            ],
            "polls": [
                {**r, "data": json.loads(r["data"])}
                for r in core.rows(
                    "SELECT * FROM social_polls ORDER BY created DESC LIMIT 50"
                )
            ],
            "posts": [
                {**r, "data": json.loads(r["data"])}
                for r in core.rows(
                    "SELECT * FROM social_posts ORDER BY created DESC LIMIT 200"
                )
            ],
            "coverage": "Only configured queries and API-entitled accessible records. Recent search, archive search and filtered streaming have different access/coverage. One stream session is supported; sessions reconnect with possible gaps. Permitted search backfill and independent archives are needed for completeness. No unrestricted all-Twitter claim.",
            "setup": "Configure X_BEARER_TOKEN in the existing private mode-0600 provider configuration or service environment, then restart the core. Never paste tokens into case notes.",
        }

    @core.app.post("/api/social/feeds")
    def create(value: Feed) -> dict:
        """Save an explicit permitted public-query monitor, ready for autonomous collection."""
        if len(core.rows("SELECT id FROM social_feeds LIMIT 26")) >= 25:
            raise HTTPException(422, "Feed limit reached")
        fid = core.uid("X-FEED")
        core.execute(
            "INSERT INTO social_feeds VALUES(?,?,?,?,?)",
            (fid, core.now(), 1, time.time(), value.model_dump_json()),
        )
        return {"id": fid, "data": value.model_dump()}

    @core.app.post("/api/social/feeds/{fid}/{action}")
    def control(fid: str, action: Literal["pause", "resume", "poll"]) -> dict:
        """Persist source-monitor controls without deleting observations or platform rules."""
        if not core.rows("SELECT id FROM social_feeds WHERE id=?", (fid,)):
            raise HTTPException(404, "Feed not found")
        if action == "poll":
            return poll(fid)
        core.execute(
            "UPDATE social_feeds SET enabled=?,next_due=? WHERE id=?",
            (int(action == "resume"), time.time(), fid),
        )
        return {"id": fid, "enabled": action == "resume"}

    def loop() -> None:
        """Poll feeds in a separate background service so collection does not block analysis."""
        inflight = {}
        with ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="sherlock-x"
        ) as workers:
            while not core.stopping.wait(3):
                for fid, future in list(inflight.items()):
                    if future.done():
                        try:
                            future.result()
                        except Exception as ex:
                            core.log(
                                "social_worker_error", {"error": type(ex).__name__}
                            )
                        del inflight[fid]
                for row in core.rows(
                    "SELECT id FROM social_feeds WHERE enabled=1 AND next_due<=? ORDER BY next_due LIMIT 4",
                    (time.time(),),
                ):
                    if row["id"] not in inflight and len(inflight) < 2:
                        inflight[row["id"]] = workers.submit(poll, row["id"])

    @core.app.on_event("startup")
    def start() -> None:
        """Resume due query feeds from durable cursor and rate-limit checkpoints."""
        threading.Thread(target=loop, daemon=True).start()

    return {"poll": poll, "create": create, "ingest": ingest, "overview": overview}

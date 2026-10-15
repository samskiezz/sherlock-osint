"""Idempotently configure broad, bounded public-media discovery through the authenticated API."""

import json
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    """Keep the single-image example separate from recurring collection-wide work."""
    client = httpx.Client(
        base_url="http://127.0.0.1:8010", trust_env=False, timeout=120
    )
    credentials = json.loads(
        (ROOT / "data/foundation-secrets/admin-login.json").read_text()
    )
    login = client.post("/api/v1/auth/login", json=credentials)
    login.raise_for_status()
    client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
    campaigns = client.get("/api/research")
    campaigns.raise_for_status()
    state = campaigns.json()
    # Publicly indexed images and publisher pages, not an assertion of hidden messages.
    config = {
        "name": "Continuous media research · hybrid images, memes and reuse references",
        "question": "Acquire publicly accessible hybrid-image and optical-illusion references and related source pages. Compare incoming acquired media against the collection; preserve inconclusive results and do not infer predictions or intentional messages from resemblance.",
        "queries": ["hybrid image", "optical illusion"],
        "providers": ["nasa_images", "public_web", "commons"],
        "seeds": [],
        "allowed_domains": [],
        "max_downloads": 12,
        "interval_minutes": 360,
        "cron_expression": "15 */6 * * *",
        "provider": "deterministic",
        "collect_images": True,
    }
    existing = state.get("campaigns", [])
    found = next((x for x in existing if x["name"] == config["name"]), None)
    if found:
        campaign_id = found["id"]
        if found["settings"].get("providers") != config["providers"]:
            response = client.patch("/api/research/" + campaign_id, json=config)
            response.raise_for_status()
            response = client.post("/api/research/" + campaign_id + "/run")
            response.raise_for_status()
    else:
        response = client.post("/api/research", json=config)
        response.raise_for_status()
        campaign_id = response.json()["id"]
    # A declared case-specific seed can include captionless images, within its existing budget.
    updated = []
    for old in existing:
        if old["name"] == "Cole Allen · public photograph and archive leads":
            settings = old["settings"]
            settings["collect_images"] = True
            settings["collect_all_seed_images"] = True
            response = client.patch("/api/research/" + old["id"], json=settings)
            response.raise_for_status()
            updated.append(old["id"])
    social = client.get("/api/social")
    social.raise_for_status()
    query = '(Bohrdom OR "Cole Allen" OR "hybrid image" OR "hidden image") has:images -is:retweet'
    feeds = social.json().get("feeds", [])
    feed = next((x for x in feeds if x["data"].get("query") == query), None)
    if not feed:
        response = client.post(
            "/api/social/feeds",
            json={
                "name": "Public media leads · case terms and image illusions",
                "query": query,
                "mode": "recent",
                "interval_seconds": 900,
                "acquire_media": True,
            },
        )
        response.raise_for_status()
        feed = response.json()
    output = {
        "campaign_id": campaign_id,
        "updated_seed_watches": updated,
        "x_feed_id": feed["id"],
        "x_live_collection_verified": False,
        "scope": "Bounded public searches every six hours. X collection waits for an authorised API credential; this configuration is not proof of acquired posts.",
    }
    (ROOT / "artifacts/media-watch-configuration-v13.json").write_text(
        json.dumps(output, indent=2)
    )
    print(json.dumps(output))


if __name__ == "__main__":
    main()

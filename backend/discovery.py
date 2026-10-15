"""Bounded public-source connectors for recurring online research."""

import json
import os
import re
from urllib.parse import urlencode, urljoin, urlparse, quote, parse_qs

import httpx
from defusedxml import ElementTree as ET

PROVIDERS = {
    "brave_images": "Brave · public image search (API key required)",
    "source_pages": "Publisher source watches · refresh public seed pages every run",
    "onion_mentions": "Onion document leads · addresses cited in acquired public records",
    "nasa_images": "NASA Image and Video Library · public image API",
    "commons": "Wikimedia Commons · public image originals and licence records",
    "public_web": "Public web index · Bing RSS (no API key)",
    "patents": "Google Patents · public patent search records",
    "internet_archive": "Internet Archive · public text/document collections",
    "arxiv": "arXiv · research papers, newest updates first",
    "nasa": "NASA NTRS · explicitly public technical reports",
    "crossref": "Crossref · publication metadata and document links",
    "gdelt": "GDELT · recent indexed news reports",
    "github": "GitHub · public repository records",
    "brave": "Brave · general web search (API key required)",
    "feeds": "Public RSS / Atom feeds and disclosure pages",
    "onion": "Public onion seeds · dedicated Tor route",
    "onion_index": "Ahmia · public onion search index",
}
DOCUMENT = re.compile(r"\.(?:pdf|docx?|txt|rtf|csv|json)(?:$|[?#])", re.I)


def feed_links(data, base, include_images=False):
    root = ET.fromstring(data)
    found = []
    for item in root.findall(".//item")[:20]:
        enclosure = item.find("enclosure")
        href = enclosure.get("url") if enclosure is not None else item.findtext("link")
        if href:
            found.append(
                {
                    "url": urljoin(base, href),
                    "title": item.findtext("title") or "Feed source",
                    "kind": "image"
                    if include_images
                    and enclosure is not None
                    and enclosure.get("type", "").startswith("image/")
                    else "document"
                    if enclosure is not None
                    else "webpage",
                }
            )
    atom = "{http://www.w3.org/2005/Atom}"
    for item in root.findall(".//" + atom + "entry")[:20]:
        links = item.findall(atom + "link")
        link = next((x for x in links if x.get("type") == "application/pdf"), None)
        if link is None:
            link = next(
                (x for x in links if x.get("rel", "alternate") == "alternate"), None
            )
        if link is not None and link.get("href"):
            found.append(
                {
                    "url": urljoin(base, link.get("href")),
                    "title": item.findtext(atom + "title") or "Publication",
                    "kind": "document"
                    if link.get("type") == "application/pdf"
                    else "webpage",
                }
            )
    if include_images:
        media = "{http://search.yahoo.com/mrss/}"
        entries = (
            root.findall(".//item")[:20] + root.findall(".//" + atom + "entry")[:20]
        )
        for item in entries:
            title = (
                item.findtext("title") or item.findtext(atom + "title") or "Feed media"
            )
            post_url = item.findtext("link")
            if not post_url:
                alternate = next(
                    (
                        x
                        for x in item.findall(atom + "link")
                        if x.get("rel", "alternate") == "alternate"
                    ),
                    None,
                )
                post_url = alternate.get("href") if alternate is not None else None
            candidates = (
                item.findall("enclosure")
                + item.findall(media + "content")
                + item.findall(media + "thumbnail")
                + item.findall(atom + "link")
            )
            for candidate in candidates[:10]:
                mime = candidate.get("type", "")
                is_thumbnail = candidate.tag == media + "thumbnail"
                if not (
                    mime.startswith("image/")
                    or is_thumbnail
                    or candidate.get("medium") == "image"
                ):
                    continue
                href = candidate.get("url") or candidate.get("href")
                if href:
                    found.append(
                        {
                            "url": urljoin(base, href),
                            "title": title,
                            "kind": "image",
                            "parent_post_url": urljoin(base, post_url)
                            if post_url
                            else None,
                            "discovery_method": "Explicit RSS/Atom media attachment; not subject attribution",
                        }
                    )
    unique = {}
    for hit in found:
        unique[(hit["url"], hit["kind"])] = hit
    return list(unique.values())


def relevant(title, query):
    # Conservative literal terms; provider search ranking alone is not evidence.
    terms = [
        x.lower()
        for x in re.findall(r"[\w-]+", query)
        if len(x) > 2
        and x.lower()
        not in {"and", "the", "for", "with", "documents", "evidence", "information"}
    ]
    return bool(terms) and all(term in title.lower() for term in terms)


def search(core, provider, query, seeds=(), limit=5):
    from .scheduler import nasa_downloads

    if provider not in PROVIDERS:
        raise ValueError("Unknown public research provider")
    if provider == "source_pages":
        hits = []
        parents = []
        failures = []
        for seed in seeds[:5]:
            if (urlparse(seed).hostname or "").endswith(".onion"):
                continue
            try:
                eid, body, final = preserve_response(
                    core, seed, "Public publisher source watch · " + query
                )
                source = core.get_evidence(eid)
                if not relevant(
                    (source["metadata"].get("document_title") or "")
                    + " "
                    + source["text"][:20000],
                    query,
                ):
                    continue
                metadata = source["metadata"]
                metadata["collection_role"] = "PUBLISHER ORIGINAL PAGE"
                core.execute(
                    "UPDATE evidence SET metadata=? WHERE id=?",
                    (json.dumps(metadata), eid),
                )
                hits.append(
                    {
                        "url": seed,
                        "title": source["metadata"].get("document_title")
                        or source["title"],
                        "kind": "webpage",
                        "pre_acquired_id": eid,
                        "attribution": "Publisher source snapshot; attribution needs review",
                    }
                )
                parents.append(eid)
            except Exception as ex:
                failures.append(
                    {"url": seed, "status": "NOT ACQUIRED", "reason": str(ex)[:500]}
                )
        if not parents and failures:
            raise ValueError(json.dumps(failures))
        result = package(core, provider, parents, hits, limit)
        result["failures"] = failures
        return result
    if provider == "onion_mentions":
        from .onion import validate_onion_url

        hits = []
        parents = []
        for e in core.rows(
            "SELECT id,title,text FROM evidence WHERE status='ORIGINAL VERIFIED' AND sha256 IS NOT NULL"
        ):
            if not relevant(e["title"] + " " + e["text"][:10000], query):
                continue
            for url in re.findall(
                r"https?://(?:[a-z0-9-]+\.)*[a-z2-7]{56}\.onion(?:/[^\s<>\"\)]+)?",
                e["text"],
                re.I,
            )[:20]:
                try:
                    validate_onion_url(url)
                except ValueError:
                    continue
                hits.append(
                    {
                        "url": url,
                        "title": "Publicly cited onion document lead · " + query,
                        "kind": "webpage",
                        "transport": "tor",
                        "parent_evidence_id": e["id"],
                        "attribution": "Address cited in an acquired document; site ownership and contents unverified",
                    }
                )
                parents.append(e["id"])
        return package(core, provider, list(dict.fromkeys(parents)), hits, limit)
    if provider == "nasa_images":
        url = "https://images-api.nasa.gov/search?" + urlencode(
            {"q": query, "media_type": "image", "page_size": min(20, limit)}
        )
        eid, body, _ = preserve_response(core, url, "NASA image catalogue · " + query)
        data = json.loads(body)
        hits = []
        for item in data.get("collection", {}).get("items", [])[:20]:
            descriptions = item.get("data", [])
            description = descriptions[0] if descriptions else {}
            searchable = (
                description.get("title", "") + " " + description.get("description", "")
            ).casefold()
            if query.strip().strip('"').casefold() not in searchable:
                continue  # NASA token matching can return unrelated hybrid-aircraft photographs.
            for link in item.get("links", [])[:10]:
                if link.get("render") != "image" or not link.get("href"):
                    continue
                hits.append(
                    {
                        "url": link["href"],
                        "title": description.get("title", "NASA library image"),
                        "kind": "image",
                        "catalogue_id": eid,
                        "nasa_id": description.get("nasa_id"),
                        "catalogue_date_created_reported": description.get(
                            "date_created"
                        ),
                        "description": description.get("description", "")[:4000],
                        "attribution": "NASA catalogue publisher rendition; not a camera original or independent historical authentication. Image-specific credits and usage rights require review.",
                    }
                )
                break
        return package(core, provider, [eid], hits, limit)
    if provider == "commons":
        url = "https://commons.wikimedia.org/w/api.php?" + urlencode(
            {
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": 6,
                "gsrlimit": 10,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "format": "json",
            }
        )
        eid, body, final = preserve_response(
            core, url, "Public image catalogue response · " + query
        )
        data = json.loads(body)
        hits = []
        for page in data.get("query", {}).get("pages", {}).values():
            for info in page.get("imageinfo", [])[:1]:
                if info.get("url") and relevant(page.get("title", ""), query):
                    metadata = info.get("extmetadata", {})
                    licence = metadata.get("LicenseShortName", {}).get(
                        "value", "Unknown"
                    )
                    hits.append(
                        {
                            "url": info["url"],
                            "title": page.get("title", "Public image"),
                            "kind": "image",
                            "catalogue_id": eid,
                            "licence": licence,
                            "description_url": info.get("descriptionurl"),
                            "attribution": "Catalogue/publisher subject label; independent identity review required",
                        }
                    )
        return package(core, provider, [eid], hits, limit)
    if provider == "public_web":
        eid, body, final = preserve_response(
            core,
            "https://www.bing.com/search?" + urlencode({"q": query, "format": "rss"}),
            "Public web search response · " + query,
        )
        return package(core, provider, [eid], feed_links(body, final), limit)
    if provider == "patents":
        eid, body, final = preserve_response(
            core,
            "https://patents.google.com/xhr/query?"
            + urlencode(
                {"url": urlencode({"q": query, "num": 20, "language": "ENGLISH"})}
            ),
            "Patent search response · " + query,
        )
        data = json.loads(body)
        hits = []
        for cluster in data.get("results", {}).get("cluster", []):
            for result in cluster.get("result", []):
                record = result.get("patent", {})
                number = re.sub(
                    "[^A-Z0-9]", "", record.get("publication_number", "").upper()
                )
                if not re.fullmatch(r"[A-Z]{2}\d+[A-Z]\d?", number):
                    continue
                hits.append(
                    {
                        "url": "https://patents.google.com/patent/" + number + "/en",
                        "title": number
                        + " · "
                        + re.sub("<[^>]+>", "", record.get("title", "Patent record")),
                        "kind": "patent",
                        "publication_number": number,
                        "attribution": "Patent disclosure, not experimentally established performance",
                    }
                )
        return package(core, provider, [eid], hits, limit)
    if provider == "onion":
        core.onion["require"]()
        from .onion import validate_onion_url

        hits = []
        for seed in seeds:
            if (urlparse(seed).hostname or "").endswith(".onion"):
                validate_onion_url(seed)
                hits.append(
                    {
                        "url": seed,
                        "title": "Public onion research seed · " + query,
                        "kind": "webpage",
                        "transport": "tor",
                    }
                )
        if not hits:
            raise ValueError("Add at least one public v3 onion seed URL")
        return {
            "provider": provider,
            "catalogues": [],
            "hits": hits[:limit],
            "verification": "Seed address supplied by investigator; site content not yet acquired",
        }
    if provider == "feeds":
        results, catalogues = [], []
        for seed in seeds[:5]:
            if (urlparse(seed).hostname or "").endswith(".onion"):
                continue
            eid, body, final = preserve_response(
                core, seed, "Public disclosure feed · " + query
            )
            catalogues.append(eid)
            source = core.get_evidence(eid)
            if "html" in source["mime"]:
                links = [
                    {
                        "url": urljoin(final, link["href"]),
                        "title": link["label"],
                        "kind": "document",
                    }
                    for link in source["metadata"].get("links", [])
                    if DOCUMENT.search(link["href"])
                    and relevant(link["label"] + " " + link["href"], query)
                ]
            else:
                links = [
                    x
                    for x in feed_links(body, final, include_images=True)
                    if relevant(x["title"], query)
                ]
            results.extend(links)
        if not catalogues:
            raise ValueError("Add a public feed or disclosure-page seed URL")
        return package(core, provider, catalogues, results, limit)
    if provider == "onion_index":
        from .onion import validate_onion_url

        eid, _, final = preserve_response(
            core,
            "https://ahmia.fi/search/?" + urlencode({"q": query}),
            "Public onion index response · " + query,
        )
        hits = []
        source = core.get_evidence(eid)
        for link in source["metadata"].get("links", []):
            url = urljoin(final, link["href"])
            redirected = parse_qs(urlparse(url).query).get("redirect_url")
            candidate = redirected[0] if redirected else url
            try:
                validate_onion_url(candidate)
            except ValueError:
                continue
            if relevant(link["label"], query):
                hits.append(
                    {
                        "url": candidate,
                        "title": link["label"] or "Indexed public onion source",
                        "kind": "webpage",
                        "transport": "tor",
                        "parent_evidence_id": eid,
                        "attribution": "Public index listing; onion site content not yet acquired",
                    }
                )
        return package(core, provider, [eid], hits, limit)
    endpoints = {
        "internet_archive": (
            "https://archive.org/advancedsearch.php",
            {
                "q": f"({query}) AND mediatype:texts AND -access-restricted-item:true",
                "output": "json",
                "rows": 10,
                "fl[]": ["identifier", "title", "date"],
                "sort[]": "addeddate desc",
            },
        ),
        "arxiv": (
            "https://export.arxiv.org/api/query",
            {
                "search_query": 'all:"' + query.replace('"', "") + '"',
                "start": 0,
                "max_results": 10,
                "sortBy": "lastUpdatedDate",
                "sortOrder": "descending",
            },
        ),
        "nasa": (
            "https://ntrs.nasa.gov/api/citations/search",
            {"keyword": query, "page.size": 10},
        ),
        "crossref": (
            "https://api.crossref.org/works",
            {
                "query.bibliographic": query,
                "rows": 10,
                "sort": "published",
                "order": "desc",
            },
        ),
        "gdelt": (
            "https://api.gdeltproject.org/api/v2/doc/doc",
            {
                "query": query,
                "mode": "artlist",
                "format": "json",
                "maxrecords": 10,
                "timespan": "7d",
                "sort": "datedesc",
            },
        ),
        "github": (
            "https://api.github.com/search/repositories",
            {"q": query, "per_page": 10, "sort": "updated"},
        ),
        "brave_images": (
            "https://api.search.brave.com/res/v1/images/search",
            {"q": query, "count": 10},
        ),
        "brave": (
            "https://api.search.brave.com/res/v1/web/search",
            {"q": query, "count": 10},
        ),
    }
    base, params = endpoints[provider]
    url = base + "?" + urlencode(params, doseq=True)
    headers = None
    if provider in ("brave", "brave_images"):
        key = os.environ.get("BRAVE_SEARCH_API_KEY")
        if not key:
            raise ValueError(
                "BRAVE_SEARCH_API_KEY is not configured; no search was sent"
            )
        headers = {"X-Subscription-Token": key, "Accept": "application/json"}
    eid, body, final = preserve_response(
        core, url, PROVIDERS[provider] + " search response · " + query, headers
    )
    if provider == "arxiv":
        return package(
            core,
            provider,
            [eid],
            [
                x
                for x in feed_links(body, final, include_images=True)
                if relevant(x["title"], query)
            ],
            limit,
        )
    data = json.loads(body)
    hits = []
    if provider == "internet_archive":
        for item in data.get("response", {}).get("docs", [])[:limit]:
            identifier, title = item.get("identifier", ""), item.get("title", "")
            if (
                not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", identifier)
                or re.search(r"cracked|keygen|credential.dump", title, re.I)
                or not relevant(title, query)
            ):
                continue
            metadata_url = "https://archive.org/metadata/" + quote(identifier)
            mid, payload, _ = preserve_response(
                core, metadata_url, "Archive document inventory · " + title
            )
            metadata = json.loads(payload)
            catalogues = metadata.get("metadata", {})
            if (
                metadata.get("is_dark")
                or str(catalogues.get("access-restricted-item", "false")).lower()
                == "true"
            ):
                continue
            for file in metadata.get("files", [])[:200]:
                name = file.get("name", "")
                if name.lower().endswith(".pdf") and not file.get("private"):
                    hits.append(
                        {
                            "url": "https://archive.org/download/"
                            + quote(identifier)
                            + "/"
                            + quote(name, safe=""),
                            "title": title + " · " + name,
                            "kind": "document",
                            "catalogue_id": mid,
                            "licence": catalogues.get("licenseurl", "Unknown"),
                        }
                    )
                    break
    elif provider == "nasa":
        hits = [
            {"url": url, "title": title, "kind": "document"}
            for url, title in nasa_downloads(data)
        ]
    elif provider == "crossref":
        for item in data.get("message", {}).get("items", []):
            title = (item.get("title") or [""])[0]
            if not relevant(title, query):
                continue
            links = [
                x.get("URL")
                for x in item.get("link", [])
                if x.get("content-type") == "application/pdf"
            ]
            href = next((x for x in links if x), None) or item.get("URL")
            if href:
                hits.append(
                    {
                        "url": href,
                        "title": title,
                        "kind": "document" if links else "publication record",
                    }
                )
    elif provider == "gdelt":
        hits = [
            {
                "url": x["url"],
                "title": x.get("title", "News record"),
                "kind": "news report",
                "indexed_date": x.get("seendate"),
            }
            for x in data.get("articles", [])
            if x.get("url") and relevant(x.get("title", ""), query)
        ]
    elif provider == "github":
        hits = [
            {
                "url": x["html_url"],
                "title": x.get("full_name", "Public repository"),
                "kind": "repository record",
                "attribution": "Repository authorship not linked to a case person",
            }
            for x in data.get("items", [])
            if not x.get("private")
            and x.get("html_url")
            and relevant(
                x.get("full_name", "") + " " + (x.get("description") or ""), query
            )
        ]
    elif provider == "brave_images":
        hits = [
            {
                "url": x["properties"]["url"],
                "title": x.get("title", "Indexed public image"),
                "kind": "image",
                "publisher_url": x.get("url"),
                "attribution": "Search index/publisher label; independent subject and provenance review required",
            }
            for x in data.get("results", [])
            if x.get("properties", {}).get("url")
        ]
    elif provider == "brave":
        hits = [
            {
                "url": x["url"],
                "title": x.get("title", "Web search result"),
                "kind": "webpage",
                "description": x.get("description", ""),
            }
            for x in data.get("web", {}).get("results", [])
            if x.get("url")
        ]
    return package(core, provider, [eid], hits, limit)


def preserve_response(core, url, title, headers=None):
    core.robots_allowed(url)
    if headers:
        # Fixed trusted API endpoint; keys live only in the request header.
        core.safe_url(url)
        with httpx.Client(
            timeout=35,
            follow_redirects=False,
            headers={**core.CLIENT_HEADERS, **headers},
        ) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 5 * 1024 * 1024:
                        raise ValueError("Discovery response exceeds 5 MB")
                body, final, response_headers = (
                    bytes(body),
                    str(response.url),
                    dict(response.headers),
                )
    else:
        body, final, response_headers, _ = core.fetch(url)
    if len(body) > 5 * 1024 * 1024:
        raise ValueError("Discovery response exceeds 5 MB")
    eid = core.preserve(
        body, title[:200], final, response_headers, "Public research connector response"
    )
    existing = core.get_evidence(eid)
    good, reason = (
        core.investigator["integrity"](existing)
        if getattr(core, "investigator", None)
        else (False, "No audit adapter")
    )
    if not good:
        core.process(eid)
    return eid, body, final


def package(core, provider, catalogues, hits, limit):
    valid, seen = [], set()
    for hit in hits:
        try:
            if hit.get("transport") == "tor":
                from .onion import validate_onion_url

                validate_onion_url(hit["url"])
            else:
                core.validate_url(hit["url"])
        except (ValueError, KeyError):
            continue
        if hit["url"] in seen:
            continue
        seen.add(hit["url"])
        valid.append(
            {
                **hit,
                "provider": provider,
                "catalogue_id": hit.get("catalogue_id")
                or (catalogues[0] if catalogues else None),
                "status": "ORIGINAL ACQUIRED BY SOURCE CONNECTOR"
                if hit.get("pre_acquired_id")
                else "DISCOVERED · ORIGINAL NOT YET ACQUIRED",
            }
        )
    return {
        "provider": provider,
        "catalogues": catalogues,
        "hits": valid[:limit],
        "verification": "Search/disclosure provenance is not authentication of an allegation",
    }

"""Token-protected Docker-to-local-core bridge; no caller-selected destination."""

import hmac
from typing import AsyncIterator
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from . import config

app = FastAPI(docs_url=None, openapi_url=None)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request) -> Response:
    """Forward only authenticated internal traffic to the owned loopback evidence service."""
    if not config.CORE_TOKEN or not hmac.compare_digest(
        request.headers.get("x-sherlock-core-token", ""), config.CORE_TOKEN
    ):
        return Response("Internal authentication required", status_code=401)
    body = await request.body()
    if len(body) > 26 * 1024 * 1024:
        return Response("Body too large", status_code=413)
    client = httpx.AsyncClient(trust_env=False, timeout=120)
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() in ("content-type", "range", "if-none-match")
    }
    response = await client.send(
        client.build_request(
            request.method,
            "http://127.0.0.1:8000/" + path.lstrip("/"),
            params=request.query_params,
            content=body,
            headers=headers,
        ),
        stream=True,
    )

    async def stream() -> AsyncIterator[bytes]:
        """Stream original media with deterministic resource cleanup."""
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    output = {
        k: v
        for k, v in response.headers.items()
        if k.lower()
        in (
            "content-type",
            "content-disposition",
            "etag",
            "content-range",
            "accept-ranges",
            "content-security-policy",
            "x-content-type-options",
            "cache-control",
        )
    }
    return StreamingResponse(stream(), status_code=response.status_code, headers=output)

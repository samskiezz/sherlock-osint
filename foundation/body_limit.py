"""Bound actual HTTP body bytes, including chunked requests without a length."""
from collections import deque

from starlette.responses import Response

MAX_REQUEST_BODY_BYTES = 26 * 1024 * 1024


class RequestBodyLimit:
    def __init__(self, app, limit=MAX_REQUEST_BODY_BYTES):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        messages = deque()
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > self.limit:
                    return await Response("Request exceeds 26 MiB gateway limit", status_code=413)(scope, receive, send)
            messages.append(message)
            if message["type"] != "http.request" or not message.get("more_body", False):
                break

        async def replay():
            if messages:
                return messages.popleft()
            return await receive()

        await self.app(scope, replay, send)

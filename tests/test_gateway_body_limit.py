"""Exercise the streaming ASGI boundary without allocating large test bodies."""
import asyncio

from starlette.responses import Response

from foundation.body_limit import RequestBodyLimit


def exercise(chunks, limit):
    requests = [{"type":"http.request", "body":chunk, "more_body":i < len(chunks)-1}
                for i, chunk in enumerate(chunks)]
    sent = []
    consumed = []
    forwarded = []
    async def receive():
        consumed.append(True)
        return requests.pop(0)
    async def send(message):
        sent.append(message)
    async def app(scope, receive, send):
        while True:
            message = await receive()
            forwarded.append(message["body"])
            if not message.get("more_body",False):
                break
        await Response(b"ok")(scope,receive,send)
    scope={"type":"http", "method":"POST", "path":"/", "headers":[(b"content-length",b"0")]}
    asyncio.run(RequestBodyLimit(app,limit)(scope,receive,send))
    return sent,consumed,forwarded


def test_exact_limit_replays_all_chunks_without_changing_bytes():
    sent,consumed,forwarded=exercise([b"ab",b"cd"],4)
    assert sent[0]["status"]==200 and forwarded==[b"ab",b"cd"] and len(consumed)==2


def test_streaming_overflow_stops_before_route_and_before_reading_remaining_chunks():
    sent,consumed,forwarded=exercise([b"ab",b"cde",b"never read"],4)
    assert sent[0]["status"]==413 and not forwarded and len(consumed)==2


def test_single_oversized_chunk_is_rejected_despite_zero_declared_length():
    sent,consumed,forwarded=exercise([b"abcde"],4)
    assert sent[0]["status"]==413 and not forwarded and len(consumed)==1


def test_non_http_scope_is_forwarded_without_consuming_messages():
    seen=[]
    async def app(scope,receive,send):
        seen.append(scope["type"])
    async def receive():
        raise AssertionError("Non-HTTP traffic must not be consumed")
    asyncio.run(RequestBodyLimit(app,4)({"type":"websocket"},receive,None))
    assert seen==["websocket"]

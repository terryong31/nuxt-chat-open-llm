"""Request-scoped logging.

Streaming makes interleaved logs hard to read: two generations in flight
produce alternating lines with nothing to tell them apart. Stamping a request
id on every record fixes that, and is the natural place to hang a tracing
exporter later.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def current_request_id() -> str:
    return _request_id.get()


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    handler.addFilter(_RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # uvicorn installs its own handlers on import; clearing them stops every
    # access log line appearing twice once the root handler is in place.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


class RequestContextMiddleware:
    """Assigns a request id and echoes it back as `x-request-id`.

    Written as raw ASGI rather than `BaseHTTPMiddleware` on purpose: that base
    class wraps every response in an anyio task group, which adds a hop per SSE
    chunk and has a long history of interfering with disconnect propagation --
    exactly the two things this server depends on.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Honour an id set by an upstream proxy so logs correlate across hops.
        incoming = dict(scope["headers"]).get(b"x-request-id")
        request_id = incoming.decode() if incoming else uuid.uuid4().hex[:12]
        token = _request_id.set(request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("x-request-id", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            _request_id.reset(token)

"""Request-ID + structlog contextvars middleware (M4).

For every incoming request:

1. Read inbound `X-Request-ID` header — if present and a valid UUID, reuse it;
   otherwise mint a fresh `uuid4()`. Malformed inbound ids are discarded
   silently (we don't want to honor caller-controlled strings of unknown
   shape — only UUIDs).
2. Stash on `request.state.request_id` so handlers can read it.
3. Bind `request_id` (and other request-scoped keys) into
   `structlog.contextvars` so every log line emitted during the request
   inherits them. The streaming handler binds `conversation_id` etc. on top.
4. Echo the request id on the response header `X-Request-ID`.
5. Emit a single info-level access log at request end with method, path,
   status, duration_ms.
6. Clear contextvars in `finally` so request-scoped state doesn't leak into
   the next request on the same worker.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_HEADER = "X-Request-ID"
_log = structlog.get_logger("request")


def _coerce_request_id(raw: str | None) -> str:
    """Return a valid UUID string. If the inbound is a UUID, reuse; else mint.

    Inbound `X-Request-ID` is honored only when it parses cleanly as a UUID.
    A malformed value is dropped silently so callers can't bypass our id
    scheme by passing arbitrary strings.
    """
    if raw is not None:
        try:
            return str(UUID(raw))
        except ValueError:
            pass
    return str(uuid4())


class RequestIDMiddleware(BaseHTTPMiddleware):
    """ASGI middleware: per-request id + structlog contextvars + access log."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = _coerce_request_id(request.headers.get(_HEADER))
        request.state.request_id = request_id

        # Bind early so any log emitted during request handling inherits the id.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started_at = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[_HEADER] = request_id
            return response
        finally:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            # Access log. `request_id` is already in contextvars; we add the
            # rest. Use info level so a real prod logger can filter as needed.
            _log.info(
                "request.access",
                method=request.method,
                path=request.url.path,
                status=status_code,
                duration_ms=duration_ms,
            )
            structlog.contextvars.clear_contextvars()

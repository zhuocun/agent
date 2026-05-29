"""Slowapi-based rate limiter singleton.

Exposes `limiter` so routes can decorate handlers with `@limiter.limit(...)`
(see `app/routes/conversations.py`, `app/auth/routes.py`). The limiter is
wired into the FastAPI app in `app/main.py` via `SlowAPIMiddleware` + the
`RateLimitExceeded` exception handler.

Storage is in-process (slowapi's default `MemoryStorage`). A future
multi-worker prod deploy will swap this for Redis via `storage_uri=` — at that
point the per-route limits stay accurate across workers. For M4 the
single-uvicorn-worker assumption is fine.

`default_limits=[]` keeps the global default empty: every limit is opt-in via
`@limiter.limit(...)` on individual routes. `headers_enabled=True` writes the
standard `X-RateLimit-*` headers + `Retry-After` on every limited response so
clients (and tests) can observe the budget.

`key_func=get_remote_address` rate-limits by client IP. Cookie-based per-user
keying is out of scope here; the per-user Anthropic LRU cache (in
`app/providers/anthropic.py`) handles connection churn for BYOK users.

`RateLimitMiddleware` is a thin wrapper around slowapi's `SlowAPIMiddleware`
that also treats routes with a DYNAMIC limit (callable `limit_value`) as
"already handled by the decorator", which slowapi's own `_should_exempt`
does not (it only checks `_route_limits`, not `_dynamic_route_limits`).
Without this, the middleware double-injects `X-RateLimit-*` headers on
limit-exceeded responses (one set from the exception handler, one from the
middleware's post-call_next `_inject_headers`).
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware, _find_route_handler, _get_route_name
from slowapi.util import get_remote_address
from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    headers_enabled=True,
)


class RateLimitMiddleware(SlowAPIMiddleware):
    """SlowAPIMiddleware that exempts decorated routes regardless of limit shape.

    Slowapi's stock `_should_exempt` checks only `_route_limits` (static
    limits), so a decorator using a callable / dynamic limit (e.g.
    `@limiter.limit(lambda: get_settings().rate_limit_messages)`) is NOT
    exempted, and the middleware re-injects headers AFTER the decorator
    (or the `RateLimitExceeded` exception handler) already did — producing
    duplicate `X-RateLimit-*` headers (e.g. "X-RateLimit-Limit: 2, 2").

    We override `dispatch` so any route registered in either `_route_limits`
    or `_dynamic_route_limits` is treated as decorator-managed and skipped
    by the middleware. Routes without a decorator still flow through stock
    `SlowAPIMiddleware` behavior (so future application/global limits would
    apply normally).
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        app = request.app
        lim: Limiter = app.state.limiter
        if not lim.enabled:
            return await call_next(request)
        handler = _find_route_handler(app.routes, request.scope)
        if handler is not None:
            name = _get_route_name(handler)
            # Either flavor of route-level limit means "the decorator owns it".
            if name in lim._route_limits or name in lim._dynamic_route_limits:
                return await call_next(request)
        return await super().dispatch(request, call_next)

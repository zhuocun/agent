"""FastAPI application entrypoint.

Wires:
- env-driven `CORSMiddleware` (echoes Origin from `CORS_ALLOWED_ORIGINS`,
  cookie auth → `allow_credentials=True`, headers restricted to Content-Type,
  preflight TTL 600s).
- `RequestIDMiddleware` (M4): per-request id, structlog contextvars binding,
  access log. Added AFTER CORS so preflight responses still carry CORS
  headers but every other response carries `X-Request-ID`.
- structlog configuration at import time (single global config, idempotent).
- exception handlers for `AppError`, Pydantic `RequestValidationError`, and a
  catch-all for unhandled exceptions (envelope serialized `by_alias=True`).
- routes: bootstrap, conversations, auth, account/BYOK, account export/delete,
  preferences, feedback, first-party analytics, and public share reads.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.auth.routes import router as auth_router
from app.config import Settings, get_settings
from app.db.session import get_session_factory
from app.errors import register_exception_handlers
from app.logging_setup import configure_logging
from app.maintenance.purge import purge_once, run_purge_loop
from app.middleware.ratelimit import RateLimitMiddleware, limiter
from app.middleware.request_id import RequestIDMiddleware
from app.observability import init_sentry, instrument_fastapi
from app.routes.account import router as account_router
from app.routes.account_activity import router as account_activity_router
from app.routes.account_data import router as account_data_router
from app.routes.account_memory import router as account_memory_router
from app.routes.account_prompt_templates import (
    router as account_prompt_templates_router,
)
from app.routes.analytics import router as analytics_router
from app.routes.billing import router as billing_router
from app.routes.bootstrap import router as bootstrap_router
from app.routes.conversations import router as conversations_router
from app.routes.feedback import router as feedback_router
from app.routes.models import router as models_router
from app.routes.preferences import router as preferences_router
from app.routes.projects import router as projects_router
from app.routes.share import router as share_router
from app.routes.status import router as status_router
from app.streaming.handler import cancel_all_producers
from app.streaming.reaper import reap_once, run_reaper_loop
from app.streaming.state import close_stream_state, configure_stream_state

_log = structlog.get_logger(__name__)


def _build_lifespan(settings: Settings) -> Any:
    """Build the ASGI lifespan: orphan-stream reaper + scheduled retention purge
    + resumable-producer cleanup.

    Two reaper trigger seams (see `app.streaming.reaper`):

    1. Startup sweep: one best-effort `reap_once` on boot. A fresh process
       knows any `active` `stream` row it didn't create is orphaned from a
       prior hard crash (SIGKILL / OOM / power loss ran no Python cleanup).
       Best-effort — `reap_once` swallows + logs, so a DB hiccup never blocks
       startup.
    2. Background loop: a detached `asyncio` task that re-sweeps on an
       interval, cancelled cleanly on shutdown. Catches the slow drip of
       crashes during a long-running process.

    Both are gated on `stream_reap_after_seconds > 0`; the background loop
    additionally needs `stream_reap_interval_seconds > 0`. The session factory
    is the process-wide one (never a request session). Multi-worker prod runs
    one loop per process — harmless (the bulk UPDATE is idempotent) but a
    production-grade reaper belongs in a single coordinated job; see the
    `stream_reap_after_seconds` doc in `app.config`.

    A SECOND pair of seams runs the scheduled retention purge (D31; see
    `app.maintenance.purge`): a startup sweep plus a detached interval loop that
    delete expired conversations across all users (per-conversation override
    else the owner's global retention). Gated on `retention_purge_enabled` AND
    `retention_purge_interval_seconds > 0`; cancelled cleanly on shutdown. The
    opportunistic read-path purges keep working regardless of this flag.

    Shutdown also cancels any detached resumable-stream producers
    (`cancel_all_producers`). When `resumable_streams_enabled` is on, the
    provider pump runs as a detached task that outlives its originating request;
    on a graceful shutdown / deploy we cancel any still-running producer so it
    doesn't leak past the process. No-op when the flag is off (the producer set
    is empty). A hard crash bypasses this — that gap is the orphan-reaper's job.
    """

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        ttl_seconds = settings.stream_reap_after_seconds
        interval_seconds = settings.stream_reap_interval_seconds
        task: asyncio.Task[None] | None = None
        purge_task: asyncio.Task[None] | None = None
        if ttl_seconds > 0:
            older_than = timedelta(seconds=ttl_seconds)
            factory = get_session_factory()
            # Startup sweep — best-effort, never blocks boot.
            await reap_once(factory, older_than=older_than)
            # Background loop — only if an interval is configured.
            if interval_seconds > 0:
                task = asyncio.create_task(
                    run_reaper_loop(
                        factory,
                        older_than=older_than,
                        interval_seconds=interval_seconds,
                    )
                )
        # Scheduled retention purge (D31). Independent of the reaper gate: a
        # startup sweep plus a detached interval loop deleting expired
        # conversations across all users. The opportunistic read-path purges
        # keep working regardless of this flag.
        purge_interval = settings.retention_purge_interval_seconds
        if settings.retention_purge_enabled and purge_interval > 0:
            purge_factory = get_session_factory()
            # Startup sweep — best-effort, never blocks boot.
            await purge_once(purge_factory)
            purge_task = asyncio.create_task(
                run_purge_loop(
                    purge_factory,
                    interval_seconds=purge_interval,
                )
            )
        try:
            yield
        finally:
            for background_task in (task, purge_task):
                if background_task is not None:
                    background_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await background_task
            # Cancel any detached resumable-stream producers (no-op when the
            # resumable flag is off — the producer set is empty).
            await cancel_all_producers()
            await close_stream_state()

    return lifespan


def create_app() -> FastAPI:
    settings = get_settings()
    settings.assert_prod_safe()
    configure_stream_state(settings)

    # [observability] Sentry init — must run BEFORE any middleware is added so
    # the SDK's request-scope hooks see the full ASGI chain. No-op when
    # SENTRY_DSN is unset; in production we log a startup warning so the
    # absence is visible in the deploy log. See app/observability/errors.py.
    init_sentry(settings)

    # Idempotent: structlog config is safe to call once per app instance
    # (tests build many; the configure call replaces the global config).
    configure_logging()

    # Swagger / redoc / OpenAPI on in dev/test; disabled in production so the
    # schema and interactive docs aren't exposed publicly.
    docs_kwargs: dict[str, Any] = {}
    if settings.env == "production":
        docs_kwargs = {"docs_url": None, "redoc_url": None, "openapi_url": None}

    app = FastAPI(
        title="API",
        version="0.1.0",
        lifespan=_build_lifespan(settings),
        **docs_kwargs,
    )

    # [observability] OTel instrumentation — wires FastAPI server spans and
    # SQLAlchemy DB spans onto the global tracer provider. No-op when
    # OTEL_EXPORTER_OTLP_ENDPOINT is unset; in production we log a startup
    # warning. See app/observability/tracing.py.
    instrument_fastapi(app, settings=settings)

    # CORS — auth is cookie-only, so `Authorization` is NOT in allow_headers.
    # CORS must be the OUTERMOST middleware so preflight (OPTIONS) responses
    # are unconditionally tagged with CORS headers, including for paths that
    # fail to match a route. Starlette runs `add_middleware` calls in LIFO,
    # so the last `add_middleware` becomes the outermost — we register CORS
    # AFTER request_id (and SlowAPIMiddleware) below.
    app.add_middleware(RequestIDMiddleware)
    # [ratelimit] limiter + middleware + handler.
    # `RateLimitMiddleware` (a thin SlowAPIMiddleware subclass — see
    # `app/middleware/ratelimit.py`) runs INSIDE CORS so preflight OPTIONS
    # keeps its CORS headers even if a route somehow trips the limiter on
    # OPTIONS. The exception handler (`_rate_limit_exceeded_handler`) builds
    # a 429 JSON response with `X-RateLimit-*` headers via the limiter's
    # header-injection path; routes opt in to per-route limits via
    # `@limiter.limit(...)`.
    app.state.limiter = limiter
    app.add_middleware(RateLimitMiddleware)
    # slowapi's handler is typed as `(Request, RateLimitExceeded) -> Response`,
    # narrower than Starlette's `(Request, Exception) -> ...`. Localize the
    # variance instead of laundering it through Any.
    app.add_exception_handler(
        RateLimitExceeded,
        _rate_limit_exceeded_handler,  # type: ignore[arg-type]
    )
    # [/ratelimit]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_origin_regex=None,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID"],
        max_age=settings.cors_max_age,
    )

    register_exception_handlers(app)

    app.include_router(bootstrap_router)
    app.include_router(conversations_router)
    app.include_router(feedback_router)
    app.include_router(preferences_router)
    app.include_router(account_router)
    app.include_router(account_data_router)
    app.include_router(account_activity_router)
    app.include_router(account_memory_router)
    app.include_router(account_prompt_templates_router)
    app.include_router(projects_router)
    app.include_router(analytics_router)
    app.include_router(billing_router)
    app.include_router(auth_router)
    # Model & data-policy directory (anonymous-allowed, registry-derived).
    app.include_router(models_router)
    # Public-by-link share read. Distinct prefix (/api/share), NO current_user
    # dependency — it's one of the two unauthenticated reads in the API.
    app.include_router(share_router)
    # Public platform status. NO current_user dependency — the second
    # unauthenticated read, used by the public status page + degraded banner.
    app.include_router(status_router)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app: FastAPI = create_app()

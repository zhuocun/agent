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
- routes: bootstrap, conversations, auth.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.auth.routes import router as auth_router
from app.config import get_settings
from app.errors import register_exception_handlers
from app.logging_setup import configure_logging
from app.middleware.ratelimit import RateLimitMiddleware, limiter
from app.middleware.request_id import RequestIDMiddleware
from app.observability import init_sentry, instrument_fastapi
from app.routes.account import router as account_router
from app.routes.bootstrap import router as bootstrap_router
from app.routes.conversations import router as conversations_router
from app.routes.feedback import router as feedback_router
from app.routes.preferences import router as preferences_router


def create_app() -> FastAPI:
    settings = get_settings()
    settings.assert_prod_safe()

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
    # which is narrower than Starlette's `(Request, Exception) -> ...`. Cast
    # locally so mypy stays strict elsewhere.
    app.add_exception_handler(
        RateLimitExceeded,
        cast(
            "Any",
            _rate_limit_exceeded_handler,
        ),
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
    app.include_router(auth_router)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app: FastAPI = create_app()

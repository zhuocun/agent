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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.routes import router as auth_router
from app.config import get_settings
from app.errors import register_exception_handlers
from app.logging_setup import configure_logging
from app.middleware.request_id import RequestIDMiddleware
from app.routes.account import router as account_router
from app.routes.bootstrap import router as bootstrap_router
from app.routes.conversations import router as conversations_router
from app.routes.feedback import router as feedback_router
from app.routes.preferences import router as preferences_router


def create_app() -> FastAPI:
    settings = get_settings()
    settings.assert_prod_safe()

    # Idempotent: structlog config is safe to call once per app instance
    # (tests build many; the configure call replaces the global config).
    configure_logging()

    app = FastAPI(
        title="API",
        version="0.1.0",
        # Swagger / redoc default on; harmless in M0.
    )

    # CORS — auth is cookie-only, so `Authorization` is NOT in allow_headers.
    # CORS must be the OUTERMOST middleware so preflight (OPTIONS) responses
    # are unconditionally tagged with CORS headers, including for paths that
    # fail to match a route. Starlette runs `add_middleware` calls in LIFO,
    # so the last `add_middleware` becomes the outermost — we register CORS
    # AFTER request_id below.
    app.add_middleware(RequestIDMiddleware)
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

"""FastAPI application entrypoint.

Wires:
- env-driven `CORSMiddleware` (echoes Origin from `CORS_ALLOWED_ORIGINS`,
  cookie auth → `allow_credentials=True`, headers restricted to Content-Type,
  preflight TTL 600s).
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
from app.routes.bootstrap import router as bootstrap_router
from app.routes.conversations import router as conversations_router


def create_app() -> FastAPI:
    settings = get_settings()
    settings.assert_prod_safe()

    app = FastAPI(
        title="API",
        version="0.1.0",
        # Swagger / redoc default on; harmless in M0.
    )

    # CORS — auth is cookie-only, so `Authorization` is NOT in allow_headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_origin_regex=None,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
        expose_headers=[],
        max_age=settings.cors_max_age,
    )

    register_exception_handlers(app)

    app.include_router(bootstrap_router)
    app.include_router(conversations_router)
    app.include_router(auth_router)

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app: FastAPI = create_app()

"""ErrorEnvelope, AppError, and FastAPI exception handlers.

Every error response (REST and the future SSE `error` frame) uses the same
envelope. Handlers serialize with `by_alias=True` so `retry_after_ms` ->
`retryAfterMs` on the wire.
"""

from __future__ import annotations

from typing import Any, Literal

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field

from app.schemas.common import CamelModel

log = structlog.get_logger(__name__)


Severity = Literal["info", "warning", "error", "fatal"]
ActionKind = Literal["retry", "open_settings", "dismiss"]


class ErrorAction(CamelModel):
    label: str
    kind: ActionKind


class ErrorEnvelope(CamelModel):
    code: str
    severity: Severity
    title: str
    body: str
    actions: list[ErrorAction] | None = None
    retry_after_ms: int | None = None
    meta: dict[str, Any] | None = Field(default=None)


class AppError(Exception):
    """Raised by routes / services to short-circuit with a typed envelope."""

    def __init__(self, envelope: ErrorEnvelope, status_code: int):
        super().__init__(envelope.code)
        self.envelope = envelope
        self.status_code = status_code


def _envelope_response(envelope: ErrorEnvelope, status_code: int) -> JSONResponse:
    return JSONResponse(
        {"error": envelope.model_dump(by_alias=True, exclude_none=True)},
        status_code=status_code,
    )


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return _envelope_response(exc.envelope, exc.status_code)


async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    safe_errors = [
        {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
        for e in exc.errors()
    ]
    envelope = ErrorEnvelope(
        code="INVALID_INPUT",
        severity="error",
        title="Invalid request",
        body="The request body or query failed validation.",
        meta={"errors": safe_errors},
    )
    return _envelope_response(envelope, status.HTTP_400_BAD_REQUEST)


def fatal_response() -> JSONResponse:
    """Build the FATAL 500 `ErrorEnvelope` response (no logging side effect)."""
    envelope = ErrorEnvelope(
        code="FATAL",
        severity="fatal",
        title="Something went wrong",
        body="The server hit an unexpected error. Please try again.",
    )
    return _envelope_response(envelope, status.HTTP_500_INTERNAL_SERVER_ERROR)


async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled_exception", exc_info=exc)
    return fatal_response()


def register_exception_handlers(app: FastAPI) -> None:
    """Wire all three handlers onto the FastAPI app."""
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)


# Common envelope factories ----------------------------------------------------


def not_found(what: str) -> AppError:
    return AppError(
        ErrorEnvelope(
            code="NOT_FOUND",
            severity="error",
            title="Not found",
            body=f"The requested {what} was not found.",
        ),
        status.HTTP_404_NOT_FOUND,
    )

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


def platform_budget_warning_envelope(*, percent: int) -> ErrorEnvelope:
    """Pre-wall budget alert (PRD 08 §5.4, T21).

    A transparency callout, NOT a block (`severity: "warning"`): surfaced in the
    bootstrap usage object once spend crosses the configured threshold (e.g.
    80%) of the effective quota. `percent` is the rounded fraction of quota
    already spent. The hard block (`PLATFORM_BUDGET_EXCEEDED`) still governs
    send — this only warns ahead of it.
    """
    return ErrorEnvelope(
        code="PLATFORM_BUDGET_WARNING",
        severity="warning",
        title="Approaching your budget",
        body=(
            f"You've used about {percent}% of your usage budget for this period."
        ),
        actions=[ErrorAction(label="View usage", kind="open_settings")],
        meta={"percent": percent},
    )


def platform_budget_soft_cap_envelope(*, percent: int) -> ErrorEnvelope:
    """Soft-cap reached (PRD 08 §5.4, T21).

    Surfaced in the bootstrap usage object once spend reaches 100% of the
    effective quota. `severity: "warning"` and a transparency callout, NOT the
    hard 429 block — that remains `PLATFORM_BUDGET_EXCEEDED` on the send path.
    """
    return ErrorEnvelope(
        code="PLATFORM_BUDGET_SOFT_CAP",
        severity="warning",
        title="Budget reached",
        body=(
            "You've reached your usage budget for this period. New platform-paid "
            "turns may be blocked until it resets or you add credits."
        ),
        actions=[ErrorAction(label="View usage", kind="open_settings")],
        meta={"percent": percent},
    )


def platform_guest_limit_envelope(*, limit: int) -> AppError:
    """Anonymous-guest hard sign-up wall (PRD 08 §5.4 / §7.4, T06).

    A BLOCK (raised as `AppError`): once a guest has sent `limit` persisted
    messages, the next send is refused until they sign up / sign in. Distinct
    from `PLATFORM_GUEST_DOWNGRADE`, which is a non-blocking transparency
    callout that fires earlier (premium-allotment exhausted). The copy names the
    limit per the PRD 08 copy rule ("state the limit").
    """
    return AppError(
        ErrorEnvelope(
            code="PLATFORM_GUEST_LIMIT",
            severity="warning",
            title="Sign up to keep chatting",
            body=(
                f"You've reached the {limit}-message limit for guests. Sign up or "
                "sign in to keep going — your current chat is preserved."
            ),
        ),
        status.HTTP_403_FORBIDDEN,
    )


def platform_guest_downgrade_envelope(*, served_tier_label: str) -> ErrorEnvelope:
    """Anonymous-guest model downgrade callout (PRD 08 §5.4 / §7.4, T06).

    A transparency callout (`severity: "info"`), NOT a block: once a guest has
    exhausted their premium-tier allotment, the next premium turn is served by
    the cheaper `fast` tier instead. Generation CONTINUES — only
    `PLATFORM_GUEST_LIMIT` blocks send. Per the PRD this reuses the §5.4
    substitution-callout (a guest downgrade is never silent), so on the wire the
    turn also carries an `auto_downgrade` substitution on its attribution.
    """
    return ErrorEnvelope(
        code="PLATFORM_GUEST_DOWNGRADE",
        severity="info",
        title=f"Now answering with {served_tier_label}",
        body=(
            f"You've used your premium guest allotment, so this turn is answered "
            f"by {served_tier_label}. Sign up to keep the better model."
        ),
    )

"""Error-envelope coverage (M4).

Asserts every error path (`AppError`, `RequestValidationError`, unhandled
exception, SSE stream-error frame) goes through the PRD-08 envelope shape
with camelCase keys.

The first three tests mount a tiny throwaway FastAPI app so we can exercise
the handlers without depending on real DB-backed routes. The SSE-error test
goes through the real `encode_error` helper.
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import AppError, ErrorEnvelope, register_exception_handlers
from app.streaming.sse import encode_error


def _build_handlers_app() -> FastAPI:
    """Tiny app exposing the three error paths exhaustively.

    Kept local to this module so handler tests don't entangle with the prod
    routes' auth / DB dependencies — we want to assert the handler shape,
    not the route plumbing.
    """
    app = FastAPI()
    register_exception_handlers(app)

    class _Echo(BaseModel):
        required_field: str

    @app.post("/app-error")
    async def _raise_app_error() -> dict[str, str]:
        raise AppError(
            ErrorEnvelope(
                code="WIDGET_BROKEN",
                severity="warning",
                title="Widget broken",
                body="The widget is not responding.",
                retry_after_ms=3000,
            ),
            status_code=409,
        )

    @app.post("/unhandled")
    async def _raise_unhandled() -> dict[str, str]:
        raise RuntimeError("kaboom")

    @app.post("/validate")
    async def _validate(body: _Echo) -> dict[str, str]:
        return {"value": body.required_field}

    return app


def test_app_error_returns_envelope_with_camel_keys() -> None:
    """AppError → JSONResponse with camelCase envelope and matching status."""
    client = TestClient(_build_handlers_app(), raise_server_exceptions=False)
    resp = client.post("/app-error")
    assert resp.status_code == 409
    body = resp.json()
    assert "error" in body
    err = body["error"]
    assert err["code"] == "WIDGET_BROKEN"
    assert err["severity"] == "warning"
    assert err["title"] == "Widget broken"
    assert err["body"].startswith("The widget")
    # camelCase: retryAfterMs, not retry_after_ms.
    assert err["retryAfterMs"] == 3000
    assert "retry_after_ms" not in err


def test_unhandled_exception_returns_fatal_500() -> None:
    """A bare exception in a route → catch-all FATAL 500 envelope."""
    client = TestClient(_build_handlers_app(), raise_server_exceptions=False)
    resp = client.post("/unhandled")
    assert resp.status_code == 500
    err = resp.json()["error"]
    assert err["code"] == "FATAL"
    assert err["severity"] == "fatal"
    assert err["title"] == "Something went wrong"


def test_validation_error_returns_invalid_input_400() -> None:
    """Pydantic validation failure → INVALID_INPUT 400 envelope."""
    client = TestClient(_build_handlers_app(), raise_server_exceptions=False)
    resp = client.post("/validate", json={"wrong_field": "x"})
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["code"] == "INVALID_INPUT"
    assert err["severity"] == "error"
    # The validator stashes the safe error fields under `meta.errors` for debug.
    assert "meta" in err
    assert "errors" in err["meta"]


def test_validation_error_does_not_leak_submitted_body() -> None:
    """A malformed body must not be reflected back — no secret, no `input` key.

    Pydantic v2's `errors()` includes an `input` field that, on a missing-field
    error, is the ENTIRE submitted body. A BYOK write with a wrong shape would
    otherwise echo the secret `apiKey` straight back to the caller.
    """
    client = TestClient(_build_handlers_app(), raise_server_exceptions=False)
    secret = "sk-supersecret-1234"
    resp = client.post("/validate", json={"apiKey": secret})
    assert resp.status_code == 400
    raw = resp.text
    assert secret not in raw
    meta_errors = resp.json()["error"]["meta"]["errors"]
    assert meta_errors  # the missing-field error is still reported
    for entry in meta_errors:
        assert set(entry.keys()) == {"loc", "msg", "type"}
        assert "input" not in entry
        assert "ctx" not in entry
        assert "url" not in entry


def test_sse_error_frame_carries_parseable_envelope() -> None:
    """`encode_error(envelope)` produces `event: error\\ndata: <json>` bytes
    with a fully-shaped envelope JSON (`code`, `severity`, `title`, `body`)."""
    envelope = ErrorEnvelope(
        code="PROVIDER_UPSTREAM",
        severity="error",
        title="Streaming failed",
        body="The provider stream errored.",
    )
    sse_event = encode_error(envelope)
    # Render as wire bytes via sse-starlette's `encode()` (str-out interface).
    encoded = sse_event.encode()
    text = encoded.decode("utf-8") if isinstance(encoded, bytes | bytearray) else encoded
    assert "event: error" in text
    assert "data: " in text
    # Pull the data: line out and parse as JSON.
    data_lines = [
        ln[len("data:"):].strip() for ln in text.splitlines() if ln.startswith("data:")
    ]
    assert data_lines, "encoded event has no data: line"
    payload = json.loads("".join(data_lines))
    assert payload["code"] == "PROVIDER_UPSTREAM"
    assert payload["severity"] == "error"
    assert payload["title"] == "Streaming failed"
    assert payload["body"] == "The provider stream errored."


def test_misconfigured_provider_app_error_renders_clean() -> None:
    """`build_provider()` raises AppError(MISCONFIGURED 500) when
    PROVIDER_BACKEND=anthropic and the API key is missing.

    Asserts the envelope reaches the response in the expected shape.
    """
    from app.config import Settings
    from app.providers.factory import build_provider

    bad = Settings(
        provider_backend="anthropic",
        anthropic_api_key=None,
        env="dev",
    )
    with pytest.raises(AppError) as exc_info:
        build_provider(bad)
    assert exc_info.value.status_code == 500
    assert exc_info.value.envelope.code == "MISCONFIGURED"
    assert exc_info.value.envelope.severity == "fatal"

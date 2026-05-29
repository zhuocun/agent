"""Regression: wire-layer Pydantic models must NOT strip string whitespace.

The base `CamelModel` previously set `str_strip_whitespace=True`, which
silently mutated every string field on construction. Two known-bad effects
this caused (both shipped in production before being caught):

1. Streaming text deltas: `AnswerDeltaEvent(text=" ready")` -> `"ready"`.
   DeepSeek (and OpenAI proper) stream tokens that include their leading
   space; the auto-strip removed it on every chunk, so the FE rendered
   "Alright,I'mready" instead of "Alright, I'm ready".

2. Auth: `UpgradeRequest(password=" secret ")` -> `"secret"`. Silently
   trimming password whitespace changes the credential the user thinks they
   set.

These tests pin the fix: the base config no longer strips, so string fields
round-trip whitespace unchanged. If a future schema genuinely wants
strip-on-input behaviour, it should opt in explicitly via a Pydantic
`field_validator`, not via a base-class default that affects every model.
"""

from __future__ import annotations

import json

from app.auth.routes import UpgradeRequest
from app.schemas.stream_events import AnswerDeltaEvent, ReasoningDeltaEvent
from app.streaming.sse import encode_answer_delta, encode_reasoning_delta


def test_answer_delta_preserves_leading_space() -> None:
    ev = AnswerDeltaEvent(text=" ready")
    assert ev.text == " ready"


def test_answer_delta_preserves_trailing_space() -> None:
    ev = AnswerDeltaEvent(text="ready ")
    assert ev.text == "ready "


def test_answer_delta_preserves_only_whitespace() -> None:
    ev = AnswerDeltaEvent(text=" ")
    assert ev.text == " "


def test_reasoning_delta_preserves_leading_space() -> None:
    ev = ReasoningDeltaEvent(text=" thinking")
    assert ev.text == " thinking"


def test_answer_delta_wire_json_preserves_whitespace() -> None:
    """The actual JSON serialized to SSE must contain the spaces."""
    ev = AnswerDeltaEvent(text=" ready")
    payload = ev.model_dump_json(by_alias=True, exclude_none=True)
    assert json.loads(payload) == {"text": " ready"}


def test_encode_answer_delta_sse_payload_preserves_whitespace() -> None:
    """End-to-end through the SSE encoder used by handler.py."""
    sse = encode_answer_delta(AnswerDeltaEvent(text=" Alright"))
    assert sse.data is not None
    assert json.loads(sse.data) == {"text": " Alright"}


def test_encode_reasoning_delta_sse_payload_preserves_whitespace() -> None:
    sse = encode_reasoning_delta(ReasoningDeltaEvent(text=" thinking "))
    assert sse.data is not None
    assert json.loads(sse.data) == {"text": " thinking "}


def test_upgrade_request_password_preserves_whitespace() -> None:
    """Passwords must round-trip exactly; trimming changes the credential."""
    req = UpgradeRequest(email="user@example.com", password=" sec ret ")
    assert req.password == " sec ret "


def test_realistic_deepseek_stream_assembles_with_spaces() -> None:
    """Simulate the wire format DeepSeek actually sends: each token is one
    delta, leading spaces glued to words. Joining the decoded SSE payloads
    must reconstruct readable English."""
    tokens = ["Alright", ",", " I", "'m", " ready", ".", " Let", "'s", " go", "."]
    assembled = "".join(
        json.loads(encode_answer_delta(AnswerDeltaEvent(text=t)).data or "{}")["text"]
        for t in tokens
    )
    assert assembled == "Alright, I'm ready. Let's go."

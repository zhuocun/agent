"""SSE event encoders.

Wire format (plan §"Streaming"):

    event: <snake_case_type>
    data: <camelCase JSON payload>
    <blank line>

Event names use the names in the plan §"POST /api/conversations/:id/messages"
(`submitted`, `reasoning_delta`, `reasoning_done`, `status`, `answer_delta`,
`terminal`, `error`). Payloads serialize via `model_dump(by_alias=True)` so
field names land as camelCase on the wire.

`sse-starlette`'s `ServerSentEvent` handles the framing — we hand it
`{event, data}` and it produces the correctly-formatted bytes.
"""

from __future__ import annotations

from sse_starlette import ServerSentEvent

from app.errors import ErrorEnvelope
from app.schemas.stream_events import (
    AnswerDeltaEvent,
    ReasoningDeltaEvent,
    ReasoningDoneEvent,
    StatusEvent,
    SubmittedEvent,
    TerminalEvent,
)


def encode_submitted(payload: SubmittedEvent) -> ServerSentEvent:
    return ServerSentEvent(
        event="submitted",
        data=payload.model_dump_json(by_alias=True, exclude_none=True),
    )


def encode_reasoning_delta(payload: ReasoningDeltaEvent) -> ServerSentEvent:
    return ServerSentEvent(
        event="reasoning_delta",
        data=payload.model_dump_json(by_alias=True, exclude_none=True),
    )


def encode_reasoning_done(payload: ReasoningDoneEvent) -> ServerSentEvent:
    return ServerSentEvent(
        event="reasoning_done",
        data=payload.model_dump_json(by_alias=True, exclude_none=True),
    )


def encode_status(payload: StatusEvent) -> ServerSentEvent:
    return ServerSentEvent(
        event="status",
        data=payload.model_dump_json(by_alias=True, exclude_none=True),
    )


def encode_answer_delta(payload: AnswerDeltaEvent) -> ServerSentEvent:
    return ServerSentEvent(
        event="answer_delta",
        data=payload.model_dump_json(by_alias=True, exclude_none=True),
    )


def encode_terminal(payload: TerminalEvent) -> ServerSentEvent:
    return ServerSentEvent(
        event="terminal",
        data=payload.model_dump_json(by_alias=True, exclude_none=True),
    )


def encode_error(envelope: ErrorEnvelope) -> ServerSentEvent:
    return ServerSentEvent(
        event="error",
        data=envelope.model_dump_json(by_alias=True, exclude_none=True),
    )

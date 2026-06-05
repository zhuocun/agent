"""SSE event payload schemas.

These payload shapes lock in the wire contract for the streaming turn at
`POST /api/conversations/:id/messages`. They are emitted by the streaming
handler (`app.streaming.handler`) over the SSE channel.
"""

from __future__ import annotations

from typing import Literal

from app.schemas.common import CamelModel
from app.schemas.message import ModelAttribution, ToolCallPart, ToolResultPart
from app.search.protocol import SourceItem


class SubmittedEvent(CamelModel):
    message_id: str
    stream_id: str | None = None


class ReasoningDeltaEvent(CamelModel):
    text: str


class ReasoningDoneEvent(CamelModel):
    pass


class StatusEvent(CamelModel):
    label: str
    state: Literal["active", "done"]


class SourcesEvent(CamelModel):
    """Resolved source / citation list for a web-search turn.

    `items` carries the ordered `SourceItem`s (1-based ids) the search backend
    returned. `SourceItem`'s fields are all single lowercase words, so the wire
    camelCase form is identical to snake_case — no aliases needed; we serialize
    the `SourceItem` models directly.

    `requested` mirrors `SourcesPart.requested`: True when web search was
    effective for the turn. Grounded ⇔ `items` non-empty; an empty `items` with
    `requested=True` is the ungrounded state the FE renders as "Answered without
    live sources".
    """

    items: list[SourceItem]
    requested: bool = False


class ToolCallEvent(ToolCallPart):
    pass


class ToolResultEvent(ToolResultPart):
    pass


class AnswerDeltaEvent(CamelModel):
    text: str


class TerminalEvent(CamelModel):
    # `awaiting_approval` is the human-in-the-loop pause terminal: the turn ended
    # because an approval-gated tool needs a decision. The FE reads the pending
    # `tool_call` part + this widened terminal to render the approval UI; a
    # follow-up `toolApproval` resume POST continues the turn. Default stays
    # `done` so every existing emit site is unchanged.
    status: Literal["done", "awaiting_approval"] = "done"
    message_id: str
    attribution: ModelAttribution

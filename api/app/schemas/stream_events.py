"""SSE event payload schemas (M0: declared but not emitted).

Reserved for M1 wiring of `POST /api/conversations/:id/messages`. We declare
the payload shapes now so the wire contract is locked in and routes can be
implemented later without schema work.
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
    """

    items: list[SourceItem]


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

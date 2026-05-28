"""SSE event payload schemas (M0: declared but not emitted).

Reserved for M1 wiring of `POST /api/conversations/:id/messages`. We declare
the payload shapes now so the wire contract is locked in and routes can be
implemented later without schema work.
"""

from __future__ import annotations

from typing import Literal

from app.schemas.common import CamelModel
from app.schemas.message import ModelAttribution


class SubmittedEvent(CamelModel):
    message_id: str


class ReasoningDeltaEvent(CamelModel):
    text: str


class ReasoningDoneEvent(CamelModel):
    pass


class StatusEvent(CamelModel):
    label: str
    state: Literal["active", "done"]


class AnswerDeltaEvent(CamelModel):
    text: str


class TerminalEvent(CamelModel):
    status: Literal["done"] = "done"
    message_id: str
    attribution: ModelAttribution

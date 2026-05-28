"""Conversation + ConversationSummary schemas."""

from __future__ import annotations

from app.schemas.common import CamelModel, ModelTierId
from app.schemas.message import ChatMessage


class Conversation(CamelModel):
    id: str
    title: str
    messages: list[ChatMessage]
    selected_tier_id: ModelTierId
    is_temporary: bool


class ConversationSummary(CamelModel):
    id: str
    title: str
    updated_at: str
    is_temporary: bool | None = None
    pinned: bool | None = None


class CreateConversationRequest(CamelModel):
    """Body for POST /api/conversations."""

    selected_tier_id: ModelTierId
    is_temporary: bool = False


class SendMessageRequest(CamelModel):
    """Body for POST /api/conversations/:id/messages.

    M1 implements `client_message_id`, `tier_id`, `text`, `is_temporary`.
    `regenerate` / `edit_message_id` ship in M2 — they're declared here so the
    FE can't accidentally pass them without a 501 from the handler.
    """

    client_message_id: str
    tier_id: ModelTierId
    text: str
    is_temporary: bool = False
    regenerate: bool = False
    edit_message_id: str | None = None

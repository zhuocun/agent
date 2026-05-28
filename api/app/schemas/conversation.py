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

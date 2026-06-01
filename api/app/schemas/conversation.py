"""Conversation + ConversationSummary schemas."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints

from app.schemas.common import CamelModel, ModelTierId
from app.schemas.message import AttachmentPart, ChatMessage


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


class ConversationSearchResult(ConversationSummary):
    match_snippet: str
    matched_message_id: str | None = None


class CreateConversationRequest(CamelModel):
    """Body for POST /api/conversations."""

    selected_tier_id: ModelTierId
    is_temporary: bool = False
    provider_id: str | None = None


class BranchConversationRequest(CamelModel):
    """Body for POST /api/conversations/:id/branch."""

    message_id: str


class PatchConversationRequest(CamelModel):
    """Body for PATCH /api/conversations/:id.

    Both fields optional; the handler rejects an empty patch with INVALID_INPUT
    (no point in PATCHing nothing). Sentinel-less: unset fields are left alone.
    """

    # Constrained ONLY when present: a partial PATCH may omit `title` entirely
    # (stays None / unset). When supplied it is stripped and must be 1..200
    # chars after stripping — a whitespace-only title collapses to "" and is
    # rejected as INVALID_INPUT, never silently persisted as a blank title.
    title: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
        ]
        | None
    ) = None
    pinned: bool | None = None


class SendMessageRequest(CamelModel):
    """Body for POST /api/conversations/:id/messages.

    M1 implements `client_message_id`, `tier_id`, `text`, `is_temporary`.
    `regenerate` / `edit_message_id` ship in M2 — they're declared here so the
    FE can't accidentally pass them without a 501 from the handler.
    """

    client_message_id: str
    tier_id: ModelTierId
    provider_id: str | None = None
    # Bounded so a single submission can't ship an unbounded prompt (the text is
    # persisted AND replayed to the provider every turn). 32k chars is generous
    # for chat input while capping per-request memory / token blowup. No
    # whitespace strip — chat text may intentionally carry leading/trailing
    # whitespace (code blocks, formatting).
    text: Annotated[str, StringConstraints(max_length=32000)]
    is_temporary: bool = False
    regenerate: bool = False
    edit_message_id: str | None = None
    # Opt this turn into web search. Wire alias `webSearch`. The route degrades
    # it to False (silently, no error) when the served binding doesn't support
    # search or no search backend is configured.
    web_search: bool = False
    # Attachment parts for the user turn. Requests may include transient
    # payload bytes on each part; persistence strips those fields and stores
    # metadata only.
    attachments: list[AttachmentPart] = Field(default_factory=list, max_length=10)

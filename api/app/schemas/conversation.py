"""Conversation + ConversationSummary schemas."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, model_validator

from app.schemas.common import CamelModel, ModelTierId, ReasoningEffortId
from app.schemas.message import AttachmentPart, ChatMessage


class ToolApprovalDecision(CamelModel):
    """A human-in-the-loop decision for a paused, approval-gated tool call.

    Sent on a follow-up `POST .../messages` (wire field `toolApproval`) to resume
    a turn that ended in `awaiting_approval`. `tool_call_id` must match the
    pending `tool_call` part on the trailing assistant message; `decision`
    approves or denies it. `edited_input` optionally replaces the tool input
    before execution — the route RE-VALIDATES it server-side (the approval gate
    is the trust boundary) and re-runs the safety preflight before running the
    tool.
    """

    tool_call_id: str
    decision: Literal["approve", "deny"]
    edited_input: dict[str, Any] | None = None


class ResponseFormatRequest(CamelModel):
    """Structured-output opt-in for a send turn (wire alias `responseFormat`).

    `type="json_object"` requests any single valid JSON value; `json_schema`
    additionally constrains the answer to `schema` (a JSON Schema document). The
    BE threads this to the provider and validates the model's output at the
    boundary (`ModelAttribution.outputFormat` / `outputValid`).

    `schema_` carries a trailing underscore because `schema` shadows pydantic's
    `BaseModel.schema`; the wire field is `schema` via the alias. `json_schema`
    without a `schema` is rejected as INVALID_INPUT (the RequestValidationError
    handler maps the raised ValueError).
    """

    type: Literal["json_object", "json_schema"]
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")

    @model_validator(mode="after")
    def _schema_required_for_json_schema(self) -> ResponseFormatRequest:
        if self.type == "json_schema" and self.schema_ is None:
            raise ValueError("response_format.schema is required when type is 'json_schema'")
        return self


class Conversation(CamelModel):
    id: str
    title: str
    messages: list[ChatMessage]
    selected_tier_id: ModelTierId
    is_temporary: bool
    # Per-conversation retention override in days (D31). `None` = inherit the
    # user's global `preferences.retention_days`. Surfaced so the FE can show
    # "expires in ~N days" and pre-fill the per-conversation retention control.
    retention_days: int | None = None
    # Project/Space membership (D20). `None` = unfiled. Surfaced so the FE can
    # group the conversation under its Project and default the picker to it.
    project_id: str | None = None


class ConversationSummary(CamelModel):
    id: str
    title: str
    updated_at: str
    is_temporary: bool | None = None
    pinned: bool | None = None
    # Per-conversation retention override in days (D31), echoed on the sidebar
    # summary so the kebab control + "expires in ~N days" hint render without a
    # follow-up GET. `None` = inherit the user's global retention.
    retention_days: int | None = None
    # Project/Space membership (D20), echoed on the sidebar summary so the
    # Projects grouping renders without a follow-up GET. `None` = unfiled.
    project_id: str | None = None


class ConversationSearchResult(ConversationSummary):
    match_snippet: str
    matched_message_id: str | None = None
    # Transparency-native fields for the advanced history-search dialog. All
    # additive + optional so the existing search callers (sidebar box, Cmd+K
    # palette) keep working unchanged. Populated from the MATCHED assistant
    # message when the hit is on message content: `served_model_label` from
    # `attribution.servedModelLabel`, `cost_usd` from the message's `cost_usd`
    # column, `matched_at` from the matched message's `created_at`. Stay `None`
    # for a title-only match (no matched message) or a user-message match (no
    # attribution / cost).
    served_model_label: str | None = None
    cost_usd: float | None = None
    matched_at: str | None = None


class CreateConversationRequest(CamelModel):
    """Body for POST /api/conversations."""

    selected_tier_id: ModelTierId
    is_temporary: bool = False
    provider_id: str | None = None
    # Optional Project/Space to file the new conversation under (D20). When the
    # project has a `defaultTierId`, the route pre-seeds the conversation's
    # `selectedTierId` from it (a create-time default, not a send-path lock).
    # Ignored on the temporary branch (temp chats have no persisted row).
    project_id: str | None = None


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
    # Per-conversation retention override in days (D31). THREE-VALUED on the
    # wire: omitted = leave unchanged; an integer 1..3650 = set the override;
    # explicit `null` = CLEAR the override (inherit the global retention). The
    # route reads `model_fields_set` to tell "omitted" from an explicit `null`,
    # so the field type permits `None` while the bound (>= 1) only applies when
    # an integer is sent. Capped at 3650 (~10y) as a sanity bound.
    retention_days: Annotated[int, Field(ge=1, le=3650)] | None = None
    # Project/Space membership (D20). THREE-VALUED on the wire like
    # `retentionDays`: omitted = leave unchanged; a project id (UUID string) =
    # file the conversation under it; explicit `null` = un-file (detach). The
    # route reads `model_fields_set` to tell "omitted" from an explicit `null`.
    project_id: str | None = None


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
    # Continue a turn the user previously Stopped: keep the persisted partial
    # assistant message and stream a NEW assistant message linked to the SAME
    # user message (via `responds_to_message_id`), rather than discarding the
    # partial like `regenerate` does. Wire alias `continueTurn`. Mutually
    # exclusive with `regenerate` / `edit_message_id` (enforced in the route).
    continue_turn: bool = False
    # Opt this turn into web search. Wire alias `webSearch`. The route degrades
    # it to False (silently, no error) when the served binding doesn't support
    # search or no search backend is configured.
    web_search: bool = False
    # Attachment parts for the user turn. Requests may include transient
    # payload bytes on each part; persistence strips those fields and stores
    # metadata only.
    attachments: list[AttachmentPart] = Field(default_factory=list, max_length=10)
    # Per-turn reasoning-effort override. Wire alias `reasoningEffort`. None /
    # "auto" defers to the served binding's default; "minimal" forces thinking
    # off for a latency win; "standard"/"extended" select provider effort
    # levels. The route degrades it silently (no error) for providers that
    # don't support effort hints — it is a hint, never a hard requirement.
    reasoning_effort: ReasoningEffortId | None = None
    # Resume a turn paused on an approval-gated tool (HITL). Wire alias
    # `toolApproval`. When set, this POST is a RESUME of a prior turn that ended
    # in `awaiting_approval`: it reuses the existing user message (links a NEW
    # assistant row via `responds_to_message_id`) and applies the approve/deny
    # decision. Mutually exclusive with `regenerate` / `editMessageId` /
    # `continueTurn` (enforced in the route).
    tool_approval: ToolApprovalDecision | None = None
    # Opt this turn into structured output (JSON mode). Wire alias
    # `responseFormat`. None (the default) leaves the turn unchanged. The route
    # threads it to the provider and the handler validates the output at the
    # boundary, surfacing the result on the assistant attribution.
    response_format: ResponseFormatRequest | None = None

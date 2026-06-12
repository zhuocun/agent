"""Message parts, attribution, cost breakdown, ChatMessage.

Mirrors `web/src/lib/types.ts` exactly. `MessagePart` is a discriminated union
of the variants the FE renders (`text` | `reasoning` | `status` | `sources` |
`attachment` | `tool_call` | `tool_result`).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, StringConstraints, model_validator

from app.schemas.common import (
    CamelModel,
    CostConfidence,
    Feedback,
    MessageRole,
    ModelTierId,
    StreamStatus,
    SubstitutionReasonCode,
)
from app.search.protocol import SourceItem
from app.uploads import TEXT_MIME_TYPES


class TextPart(CamelModel):
    type: Literal["text"] = "text"
    text: str
    # Agentic mode only: the orchestrator subagent that produced this part. None
    # (omitted via `exclude_none`) for every non-agentic message, so the
    # persisted/wire shape is byte-for-byte unchanged off the agentic path.
    subagent_id: str | None = None


class ReasoningPart(CamelModel):
    type: Literal["reasoning"] = "reasoning"
    text: str
    duration_sec: float | None = None
    subagent_id: str | None = None


class StatusPart(CamelModel):
    type: Literal["status"] = "status"
    label: str
    state: Literal["active", "done"]


class SourcesPart(CamelModel):
    """Persisted source / citation list for a web-search turn.

    Mirrors the `sources` SSE event. `SourceItem`'s fields are all single
    lowercase words, so the wire camelCase form equals snake_case — the
    `SourceItem` models serialize directly with no alias churn.
    """

    type: Literal["sources"] = "sources"
    items: list[SourceItem]
    # Honesty rule (PRD 07 §4.3): `requested=True` means web search was
    # EFFECTIVE for this turn. A turn is grounded iff `items` is non-empty; an
    # empty `items` with `requested=True` is the ungrounded state ("Answered
    # without live sources"). When search was never requested, no sources part
    # is persisted at all, so this defaults to False for any legacy/non-search
    # part and never has to be backfilled.
    requested: bool = False


class AttachmentPart(CamelModel):
    """User-provided attachment metadata.

    Persisted message parts store metadata only. Incoming send requests may add
    a transient `dataUrl` or `contentBase64` payload; those fields are excluded
    from `model_dump(...)` so raw bytes never enter message history.
    """

    type: Literal["attachment"] = "attachment"
    id: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    name: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    media_type: Literal["image", "pdf", "text"]
    mime_type: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    size_bytes: int = Field(ge=0, le=25 * 1024 * 1024)
    storage_policy: Literal["transient"] = "transient"
    data_url: Annotated[str, StringConstraints(max_length=7 * 1024 * 1024)] | None = Field(
        default=None,
        exclude=True,
    )
    content_base64: Annotated[
        str, StringConstraints(max_length=7 * 1024 * 1024)
    ] | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _mime_matches_media_type(self) -> AttachmentPart:
        if self.media_type == "image" and not self.mime_type.startswith("image/"):
            raise ValueError("image attachments must use an image/* MIME type")
        if self.media_type == "pdf" and self.mime_type != "application/pdf":
            raise ValueError("PDF attachments must use application/pdf")
        if self.media_type == "text" and not (
            self.mime_type.startswith("text/") or self.mime_type in TEXT_MIME_TYPES
        ):
            raise ValueError("text attachments must use a text MIME type")
        return self


ToolApprovalState = Literal[
    "not_required",
    "pending",
    "approved",
    "rejected",
]

ToolRunStatus = Literal[
    "pending",
    "awaiting_approval",
    "running",
    "succeeded",
    "failed",
    "cancelled",
]


class ToolCallPart(CamelModel):
    """A model-requested tool/function call.

    `approval_state` is explicit so a future human-in-the-loop flow can add
    approval endpoints without changing the transcript shape.
    """

    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    label: str | None = None
    status: ToolRunStatus = "pending"
    approval_state: ToolApprovalState = "not_required"
    input: dict[str, Any] | None = None
    subagent_id: str | None = None


class ToolResultPart(CamelModel):
    """The result produced for a prior `tool_call` part."""

    type: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    name: str
    label: str | None = None
    status: ToolRunStatus = "succeeded"
    approval_state: ToolApprovalState = "not_required"
    summary: str | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    subagent_id: str | None = None


class AppliedTier(CamelModel):
    label: str
    threshold_tokens: int
    price_in_per_m: float
    price_out_per_m: float


class SessionMultiplier(CamelModel):
    input: float
    output: float


class LongContext(CamelModel):
    flat: bool
    tier_scope: Literal["session", "overage"] | None = None
    tokens_repriced: Literal["all", "above_threshold", "none"] | None = None
    applied_tier: AppliedTier | None = None
    session_multiplier: SessionMultiplier | None = None

    @model_validator(mode="after")
    def _exclusive_pricing_choice(self) -> LongContext:
        # Invariant: exactly one of sessionMultiplier or appliedTier when not
        # flat. Never both. Never either when flat is True.
        has_session = self.session_multiplier is not None
        has_tier = self.applied_tier is not None
        if self.flat:
            if has_session or has_tier:
                raise ValueError(
                    "LongContext.flat=True forbids sessionMultiplier and appliedTier"
                )
        else:
            if has_session and has_tier:
                raise ValueError(
                    "LongContext: provide either sessionMultiplier or appliedTier, not both"
                )
        return self


class CostBreakdown(CamelModel):
    currency: str = "USD"
    list_price_in_per_m: float
    list_price_out_per_m: float
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cached_input_tokens: int
    long_context: LongContext
    promo_applied: bool = False
    subtotal_usd: float
    session_surcharge_usd: float = 0.0


class Substitution(CamelModel):
    reason_code: SubstitutionReasonCode
    reason_text: str


class ModelAttribution(CamelModel):
    requested_tier_id: ModelTierId
    served_tier_id: ModelTierId
    served_model_label: str
    provider_id: str | None = None
    provider_label: str | None = None
    is_byok: bool
    cost_usd: float
    cost_confidence: CostConfidence
    breakdown: CostBreakdown
    substitution: Substitution | None = None
    # Structured-output (JSON mode) result for the turn. Populated ONLY when a
    # `response_format` was requested; otherwise both stay None and the wire
    # emits no `outputFormat`/`outputValid`. `output_valid` reflects boundary
    # validation: JSON parse (always) plus JSON Schema validation (for
    # `json_schema`). Invalid output never hard-fails the turn — it is surfaced
    # here while the raw text is preserved. Kept at the END so existing
    # positional/test usage is unaffected.
    output_format: Literal["json_object", "json_schema"] | None = None
    output_valid: bool | None = None
    # Transparent long-term memory (D19): how many saved facts were injected into
    # this turn. Present (and > 0) ONLY when memory was applied; omitted otherwise
    # so the wire is unchanged for memory-off turns. The FE renders the "Memory
    # used here" chip from this turn-level count. Kept at the END so existing
    # positional/test usage is unaffected.
    memory_applied: int | None = None
    # The ids of the memory facts injected into this turn (D19). Present (and
    # non-empty) only alongside `memory_applied`; lets the FE link the "Memory
    # used here" chip back to the exact ledger rows. Omitted (None) for
    # memory-off turns so the wire shape is unchanged.
    memory_fact_ids: list[str] | None = None


class SubagentPart(CamelModel):
    """Agentic mode: a marker part opening one orchestrator subagent's section.

    Persisted (and streamed) ahead of that subagent's tagged content parts so a
    reload can group the transcript by subagent and render per-subagent
    attribution / spend. `role` is the orchestration role (`primary` / `worker`
    / `aggregator`); `attribution` and `cost_usd` are optional so a section can
    render before its subagent finishes. Present ONLY on agentic turns — a
    non-agentic message never carries this part, so the union addition is inert
    for every existing message.
    """

    type: Literal["subagent"] = "subagent"
    subagent_id: str
    label: str
    role: str
    attribution: ModelAttribution | None = None
    cost_usd: float | None = None


MessagePart = Annotated[
    TextPart
    | ReasoningPart
    | StatusPart
    | SourcesPart
    | AttachmentPart
    | ToolCallPart
    | ToolResultPart
    | SubagentPart,
    Field(discriminator="type"),
]


class ChatMessage(CamelModel):
    id: str
    role: MessageRole
    parts: list[MessagePart]
    created_at: str
    status: StreamStatus | None = None
    attribution: ModelAttribution | None = None
    feedback: Feedback | None = None

"""Message parts, attribution, cost breakdown, ChatMessage.

Mirrors `web/src/lib/types.ts` exactly. `MessagePart` is a discriminated union
of the three variants the FE renders (`text` | `reasoning` | `status`). The
wider PRD-04 §6 schema (e.g. `tool-call`) is deliberately not in M0.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas.common import (
    CamelModel,
    CostConfidence,
    Feedback,
    MessageRole,
    ModelTierId,
    StreamStatus,
    SubstitutionReasonCode,
)


class TextPart(CamelModel):
    type: Literal["text"] = "text"
    text: str


class ReasoningPart(CamelModel):
    type: Literal["reasoning"] = "reasoning"
    text: str
    duration_sec: float | None = None


class StatusPart(CamelModel):
    type: Literal["status"] = "status"
    label: str
    state: Literal["active", "done"]


MessagePart = Annotated[
    TextPart | ReasoningPart | StatusPart,
    Field(discriminator="type"),
]


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
    is_byok: bool
    cost_usd: float
    cost_confidence: CostConfidence
    breakdown: CostBreakdown
    substitution: Substitution | None = None


class ChatMessage(CamelModel):
    id: str
    role: MessageRole
    parts: list[MessagePart]
    created_at: str
    status: StreamStatus | None = None
    attribution: ModelAttribution | None = None
    feedback: Feedback | None = None

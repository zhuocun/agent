"""UserPreferences schema."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.schemas.common import CamelModel, ModelTierId

CustomInstructions = Annotated[str, StringConstraints(max_length=4000)]


class UserPreferences(CamelModel):
    default_tier_id: ModelTierId
    temporary_by_default: bool
    training_opt_in: bool
    send_on_enter: bool
    auto_expand_reasoning: bool
    telemetry_enabled: bool
    custom_instructions: CustomInstructions = ""
    # None means "retain forever"; finite choices stay intentionally narrow.
    retention_days: Literal[30, 90] | None = None
    # User-set monthly platform-spend cap in USD. None means "no user cap" (only
    # the operator's `USAGE_BUDGET_USD` applies, if any). When both are set the
    # lower one wins (see `usage._effective_quota_usd`).
    monthly_budget_usd: float | None = None
    # User-set per-conversation platform-spend ceiling in USD. None means "no
    # per-conversation cap". Enforced in the send-gate for platform-key turns
    # (BYOK/temporary turns are exempt) once a conversation's accumulated
    # assistant cost reaches it.
    per_conversation_budget_usd: float | None = None
    # Transparent long-term memory opt-in (D19). OFF by default. When True (and
    # the turn is not temporary) the user's saved facts are injected into the
    # turn — see `app.streaming.handler._apply_memory`.
    memory_enabled: bool = False


class UserPreferencesRequest(CamelModel):
    default_tier_id: ModelTierId
    temporary_by_default: bool
    training_opt_in: bool
    send_on_enter: bool
    auto_expand_reasoning: bool
    telemetry_enabled: bool | None = None
    custom_instructions: CustomInstructions | None = None
    # None means "retain forever"; finite choices stay intentionally narrow.
    retention_days: Literal[30, 90] | None = None
    # User-set monthly platform-spend cap in USD. Non-negative; None clears it.
    monthly_budget_usd: Annotated[float, Field(ge=0)] | None = None
    # User-set per-conversation platform-spend ceiling in USD. Non-negative;
    # None clears it.
    per_conversation_budget_usd: Annotated[float, Field(ge=0)] | None = None
    # Transparent long-term memory opt-in (D19). Optional for stale clients;
    # omission preserves the existing saved value (mirrors `telemetry_enabled`).
    memory_enabled: bool | None = None

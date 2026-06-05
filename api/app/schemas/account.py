"""AccountInfo + UsageBudget schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.conversation import Conversation
from app.schemas.memory import MemoryFact
from app.schemas.preferences import UserPreferences


class AccountByokKey(CamelModel):
    provider_id: str
    provider_label: str
    masked_key: str
    usable: bool


class BillingState(CamelModel):
    plan_id: Literal["free", "pro"]
    plan_label: str
    pro_enabled: bool
    billing_provider: Literal["stripe", "fake"] | None = None
    # Legacy alias for Pro checkout availability. Kept so stale clients that
    # only know `checkoutAvailable` keep gating the upgrade action correctly.
    checkout_available: bool = False
    pro_checkout_available: bool = False
    credit_checkout_available: bool = False
    portal_available: bool = False
    credit_balance_usd: float = 0.0


class AccountInfo(CamelModel):
    name: str
    email: str
    is_anonymous: bool
    plan_label: str
    billing: BillingState = Field(
        default_factory=lambda: BillingState(
            plan_id="free",
            plan_label="Free",
            pro_enabled=False,
        )
    )
    byok_enabled: bool
    byok_masked_key: str | None = None
    byok_keys: list[AccountByokKey] = Field(default_factory=list)


class UsageLedgerEntry(CamelModel):
    id: str
    entry_type: Literal["grant", "platform_debit", "adjustment"]
    amount_usd: float
    description: str | None = None
    reference_type: str | None = None
    reference_id: str | None = None
    created_at: str


class UsageBudget(CamelModel):
    used: int
    limit: int
    period_label: str
    is_byok: bool
    monthly_spend_usd: float = 0.0
    monthly_quota_usd: float = 0.0
    credit_balance_usd: float = 0.0
    platform_remaining_usd: float | None = None
    # The user's own monthly budget cap (from preferences), if set. None when the
    # user has not set one.
    user_budget_usd: float | None = None
    # The cap actually enforced this period: min of the operator quota and the
    # user cap (whichever positive caps exist). None when neither caps spend.
    effective_quota_usd: float | None = None
    recent_ledger_entries: list[UsageLedgerEntry] = Field(default_factory=list)


class SpendDayBucket(CamelModel):
    date: str  # "YYYY-MM-DD" (UTC day)
    cost_usd: float
    message_count: int


class SpendModelBucket(CamelModel):
    label: str
    tier_id: str | None = None
    provider_id: str | None = None
    cost_usd: float
    message_count: int


class SpendConversationBucket(CamelModel):
    conversation_id: str
    title: str
    cost_usd: float
    message_count: int


class SpendAnalytics(CamelModel):
    """Longitudinal spend analytics for the caller (PRD 05 §4.5 D27).

    Two cost bases are surfaced HONESTLY because they legitimately differ
    (see `app/db/repositories/usage.py` module docstring):

    - `cumulative_meter_usd`: `sum(usage_rollup.cost_usd)` over the periods
      intersecting the range — every generation triggered, including
      regenerated/edited turns whose assistant messages were later deleted.
    - `surviving_messages_usd`: `sum(message.cost_usd)` over the caller's
      assistant messages STILL in their threads within the range.
    """

    range_days: int
    currency: Literal["USD"] = "USD"
    surviving_messages_usd: float
    cumulative_meter_usd: float
    daily: list[SpendDayBucket] = Field(default_factory=list)
    by_model: list[SpendModelBucket] = Field(default_factory=list)
    by_conversation: list[SpendConversationBucket] = Field(default_factory=list)


class AccountExportMetadata(CamelModel):
    id: str
    created_at: str
    is_anonymous: bool


class ByokKeyMetadata(CamelModel):
    provider: str
    masked_key: str
    created_at: str


class UsageRollupExport(CamelModel):
    period_start: str
    used: int
    limit: int
    cost_usd: float
    is_byok: bool


class AuditEventExport(CamelModel):
    event_type: str
    created_at: str
    details: dict[str, Any] = Field(default_factory=dict)


class AnalyticsEventExport(CamelModel):
    event_type: str
    created_at: str
    properties: dict[str, Any] = Field(default_factory=dict)


class AccountExport(CamelModel):
    """GDPR data-export envelope (PRD 05 §7.3).

    A single self-contained JSON document of everything we hold for the caller.
    Deliberately reuses the existing wire schemas so the export mirrors what the
    FE already renders. It must NEVER carry secrets: `account` is the
    byok-masked `AccountInfo` (no ciphertext, no decrypted key), and there is no
    session-secret / session-row material anywhere in the shape.
    """

    account: AccountInfo
    account_metadata: AccountExportMetadata
    preferences: UserPreferences
    usage: UsageBudget
    usage_credit_ledger: list[UsageLedgerEntry]
    usage_rollups: list[UsageRollupExport]
    byok_keys: list[ByokKeyMetadata]
    conversations: list[Conversation]
    audit_events: list[AuditEventExport]
    analytics_events: list[AnalyticsEventExport]
    # Transparent long-term memory (D19): the caller's full editable fact ledger.
    memory_facts: list[MemoryFact]
    exported_at: str


class AccountDeleteRequest(CamelModel):
    confirmation: str

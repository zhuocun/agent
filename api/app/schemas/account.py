"""AccountInfo + UsageBudget schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.conversation import Conversation
from app.schemas.preferences import UserPreferences


class AccountInfo(CamelModel):
    name: str
    email: str
    is_anonymous: bool
    plan_label: str
    byok_enabled: bool
    byok_masked_key: str | None = None


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
    recent_ledger_entries: list[UsageLedgerEntry] = Field(default_factory=list)


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
    usage_rollups: list[UsageRollupExport]
    byok_keys: list[ByokKeyMetadata]
    conversations: list[Conversation]
    audit_events: list[AuditEventExport]
    exported_at: str


class AccountDeleteRequest(CamelModel):
    confirmation: str

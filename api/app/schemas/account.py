"""AccountInfo + UsageBudget schemas."""

from __future__ import annotations

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


class UsageBudget(CamelModel):
    used: int
    limit: int
    period_label: str
    is_byok: bool


class AccountExport(CamelModel):
    """GDPR data-export envelope (PRD 05 §7.3).

    A single self-contained JSON document of everything we hold for the caller.
    Deliberately reuses the existing wire schemas so the export mirrors what the
    FE already renders. It must NEVER carry secrets: `account` is the
    byok-masked `AccountInfo` (no ciphertext, no decrypted key), and there is no
    session-secret / session-row material anywhere in the shape.
    """

    account: AccountInfo
    preferences: UserPreferences
    usage: UsageBudget
    conversations: list[Conversation]
    exported_at: str

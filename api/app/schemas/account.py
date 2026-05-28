"""AccountInfo + UsageBudget schemas."""

from __future__ import annotations

from app.schemas.common import CamelModel


class AccountInfo(CamelModel):
    name: str
    email: str
    plan_label: str
    byok_enabled: bool
    byok_masked_key: str | None = None


class UsageBudget(CamelModel):
    used: int
    limit: int
    period_label: str
    is_byok: bool

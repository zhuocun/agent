"""UserPreferences schema."""

from __future__ import annotations

from typing import Literal

from app.schemas.common import CamelModel, ModelTierId


class UserPreferences(CamelModel):
    default_tier_id: ModelTierId
    temporary_by_default: bool
    training_opt_in: bool
    send_on_enter: bool
    auto_expand_reasoning: bool
    telemetry_enabled: bool
    # None means "retain forever"; finite choices stay intentionally narrow.
    retention_days: Literal[30, 90] | None = None


class UserPreferencesRequest(CamelModel):
    default_tier_id: ModelTierId
    temporary_by_default: bool
    training_opt_in: bool
    send_on_enter: bool
    auto_expand_reasoning: bool
    telemetry_enabled: bool | None = None
    # None means "retain forever"; finite choices stay intentionally narrow.
    retention_days: Literal[30, 90] | None = None

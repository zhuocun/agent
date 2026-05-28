"""UserPreferences schema."""

from __future__ import annotations

from app.schemas.common import CamelModel, ModelTierId


class UserPreferences(CamelModel):
    default_tier_id: ModelTierId
    temporary_by_default: bool
    training_opt_in: bool
    send_on_enter: bool
    auto_expand_reasoning: bool

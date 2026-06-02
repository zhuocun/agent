"""UserPreferences schema."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import StringConstraints

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

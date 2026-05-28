"""BootstrapResponse — one round-trip replacement for all MOCK_* imports."""

from __future__ import annotations

from app.schemas.account import AccountInfo, UsageBudget
from app.schemas.common import CamelModel
from app.schemas.conversation import ConversationSummary
from app.schemas.preferences import UserPreferences
from app.schemas.tier import ModelTier, PromptSuggestion


class BootstrapResponse(CamelModel):
    account: AccountInfo
    preferences: UserPreferences
    usage: UsageBudget
    model_tiers: list[ModelTier]
    suggestions: list[PromptSuggestion]
    conversations: list[ConversationSummary]

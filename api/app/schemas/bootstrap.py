"""BootstrapResponse — one round-trip replacement for all MOCK_* imports."""

from __future__ import annotations

from app.schemas.account import AccountInfo, UsageBudget
from app.schemas.common import CamelModel
from app.schemas.conversation import ConversationSummary
from app.schemas.preferences import UserPreferences
from app.schemas.project import ProjectSummary
from app.schemas.tag import Tag
from app.schemas.tier import ModelTier, PromptSuggestion


class BootstrapResponse(CamelModel):
    account: AccountInfo
    preferences: UserPreferences
    usage: UsageBudget
    model_tiers: list[ModelTier]
    suggestions: list[PromptSuggestion]
    conversations: list[ConversationSummary]
    # Projects/Spaces (D20): the caller's scoping containers, so the sidebar can
    # render the Projects section and the settings panel on first paint.
    projects: list[ProjectSummary]
    # Tags (Conversation Org v2): the caller's labels, so the sidebar can render
    # the Tags section + tag chips on first paint (mirrors `projects`).
    tags: list[Tag]
    # Agentic mode availability. True only when the server has BOTH
    # `AGENTIC_ENABLED` and `TOOLS_ENABLED` on (the orchestrator builds on the
    # tool seam). The FE gates its agentic-mode picker on this so it never offers
    # a mode the server would ignore. Defaults False so a flag-off build's
    # bootstrap shape is unchanged.
    agentic_enabled: bool = False

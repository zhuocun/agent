"""ModelTier + PromptSuggestion wire schemas."""

from __future__ import annotations

from typing import Literal

from app.schemas.common import CamelModel, CostHint, ModelTierId, SpeedHint


class ModelTier(CamelModel):
    id: ModelTierId
    label: str
    description: str
    speed_hint: SpeedHint
    cost_hint: CostHint
    context_hint: str


class PromptSuggestion(CamelModel):
    id: str
    icon: Literal["code", "explain", "write", "analyze", "brainstorm", "debug"]
    title: str
    prompt: str

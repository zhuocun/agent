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
    # Curated display name of the model the tier actually serves (e.g.
    # "DeepSeek V4 Flash") — a friendly label, never a raw model id (PRD 06
    # §5.6). Populated by bootstrap from the ACTIVE backend's binding, so it
    # reflects what really answers. Empty for `auto` (the router picks per
    # message, so there is no single model) and as the backend-independent
    # default on the canonical tier objects.
    model_label: str = ""
    # Whether this tier can ground a turn with web search. The wire flag is
    # `binding.supports_web_search AND search_enabled(settings)` — set by
    # `list_tiers` so the FE only shows the affordance when a search backend is
    # actually configured. Defaults to False as the backend-independent default
    # on the canonical tier objects.
    supports_web_search: bool = False


class PromptSuggestion(CamelModel):
    id: str
    icon: Literal["code", "explain", "write", "analyze", "brainstorm", "debug"]
    title: str
    prompt: str

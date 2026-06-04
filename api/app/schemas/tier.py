"""ModelTier + PromptSuggestion wire schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel, CostHint, ModelTierId, SpeedHint


class ProviderDataPolicy(CamelModel):
    """Route-level data handling metadata surfaced with each tier.

    This is intentionally provider-route metadata, not a user preference: it
    tells the picker what the currently active backend's platform route does by
    default so DeepSeek/Western/BYOK choices can be disclosed honestly.
    """

    trains_on_data: bool
    training_default: Literal["never", "opt_in", "opt_out", "unknown"]
    data_residency: str
    retention_days: int | None = None
    zero_data_retention_available: bool = False
    policy_label: str


class ProviderRouteOption(CamelModel):
    """Selectable provider route metadata for a single tier."""

    provider_id: str
    label: str
    status: Literal["available", "pending", "unavailable"]
    model_label: str = ""
    supports_web_search: bool = False
    supports_attachments: bool = False
    supports_vision: bool = False
    default_route_eligible: bool = False
    data_policy: ProviderDataPolicy | None = None


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
    # Whether this tier accepts user attachments with native provider payloads.
    # Metadata-only fallback is not advertised as attachment support.
    supports_attachments: bool = False
    # Whether this tier can INTERPRET images (and native PDF *document* blocks).
    # DISTINCT from `supports_attachments`: a tier may accept files (text/PDF as
    # transcript text) without being multimodal. The FE composer auto-removes
    # image attachments (keeping PDFs/text) when this is False.
    supports_vision: bool = False
    # Active provider route metadata. Populated by `list_tiers` from the backend
    # registry so the FE can disclose the route/policy without hardcoded model
    # facts. Empty defaults keep canonical tier objects backend-independent.
    provider_id: str = ""
    provider_label: str = ""
    provider_route_status: Literal["available", "pending", "unavailable"] = "available"
    default_route_eligible: bool = False
    data_policy: ProviderDataPolicy | None = None
    provider_options: list[ProviderRouteOption] = Field(default_factory=list)


class PromptSuggestion(CamelModel):
    id: str
    icon: Literal["code", "explain", "write", "analyze", "brainstorm", "debug"]
    title: str
    prompt: str

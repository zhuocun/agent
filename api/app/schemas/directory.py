"""Model & data-policy directory wire schemas (PRD 05 §4.5 / PRD 07 §5).

A browsable catalog of every provider route in the registry plus its tiers'
capabilities and list prices, so a user can compare data policies and pricing
before choosing a route. Every field is derived from the live registry
(`app.providers.tiers`); nothing here is hardcoded model/policy fact.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel, ModelTierId
from app.schemas.tier import ProviderDataPolicy


class ProviderDirectoryTier(CamelModel):
    """One tier's capabilities + list prices for a provider route."""

    tier_id: ModelTierId
    model_label: str = ""
    list_price_in_per_m: float = 0.0
    list_price_out_per_m: float = 0.0
    supports_web_search: bool = False
    supports_attachments: bool = False
    supports_vision: bool = False


class ProviderDirectoryEntry(CamelModel):
    """One provider route in the directory catalog.

    `data_policy` is `None` for routes with no published policy (e.g. a pending
    roadmap route); the FE renders "policy unavailable" rather than guessing.
    `status` is the registry's static catalog status (`available`/`pending`/
    `unavailable`), independent of runtime key availability — this is a catalog,
    not a live route-health probe.
    """

    provider_id: str
    label: str
    status: Literal["available", "pending", "unavailable"]
    default_route_eligible: bool
    data_policy: ProviderDataPolicy | None = None
    tiers: list[ProviderDirectoryTier] = Field(default_factory=list)

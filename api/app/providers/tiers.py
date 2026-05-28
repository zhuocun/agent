"""BE model tier registry — single source of truth for capability tiers.

Mirrors `web/src/lib/model-tiers.ts` exactly on the wire, but is BE-owned.
Bootstrap returns this list so the FE can stop carrying its own copy once it
consumes `bootstrap.modelTiers`.

The shape `ModelTier` is the FE-facing slice. Internal extras (provider id,
model id, pricing) live as private fields used by `providers/pricing.py` and
the streaming handler — they are NOT serialized to the wire.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.common import CostHint, ModelTierId, SpeedHint
from app.schemas.tier import ModelTier


@dataclass(frozen=True)
class TierBinding:
    """BE-internal binding from tier id to concrete provider/model + pricing.

    `cache_read_per_m` (M4): optional per-million price for cache-read tokens.
    When set, `compute_cost_breakdown` bills `cached_input_tokens` at this rate
    instead of `list_price_in_per_m`. Anthropic cache reads are 10% of input
    price; populate accordingly. `None` falls back to 10% of the input rate
    (the Anthropic cache-read convention).
    """

    tier: ModelTier
    provider_id: str
    model_id: str
    list_price_in_per_m: float
    list_price_out_per_m: float
    long_context_flat: bool
    cache_read_per_m: float | None = None


def _tier(
    id_: ModelTierId,
    label: str,
    description: str,
    speed: SpeedHint,
    cost: CostHint,
    context: str,
) -> ModelTier:
    return ModelTier(
        id=id_,
        label=label,
        description=description,
        speed_hint=speed,
        cost_hint=cost,
        context_hint=context,
    )


# Order matters: the FE keeps the same order in its picker.
# Prices align with current Anthropic public per-million-token pricing
# (input / output). `cache_read_per_m` is 10% of input rate per Anthropic's
# cache-read pricing convention.
TIER_BINDINGS: tuple[TierBinding, ...] = (
    TierBinding(
        tier=_tier(
            "auto",
            "Auto",
            "Routes each message to the best-value model for the task.",
            "fast",
            "low",
            "Adaptive",
        ),
        provider_id="anthropic",
        model_id="claude-sonnet-4-6",
        list_price_in_per_m=3.0,
        list_price_out_per_m=15.0,
        long_context_flat=True,
        cache_read_per_m=0.30,
    ),
    TierBinding(
        tier=_tier(
            "fast",
            "Fast",
            "Quick, low-cost answers for everyday questions.",
            "fastest",
            "lowest",
            "128K",
        ),
        provider_id="anthropic",
        model_id="claude-haiku-4-5-20251001",
        list_price_in_per_m=1.0,
        list_price_out_per_m=5.0,
        long_context_flat=True,
        cache_read_per_m=0.10,
    ),
    TierBinding(
        tier=_tier(
            "smart",
            "Smart",
            "Balanced reasoning and speed for most work.",
            "balanced",
            "medium",
            "200K",
        ),
        provider_id="anthropic",
        model_id="claude-sonnet-4-6",
        list_price_in_per_m=3.0,
        list_price_out_per_m=15.0,
        long_context_flat=True,
        cache_read_per_m=0.30,
    ),
    TierBinding(
        tier=_tier(
            "pro",
            "Pro",
            "Maximum capability for hard, high-stakes tasks.",
            "slow",
            "high",
            "1M",
        ),
        provider_id="anthropic",
        model_id="claude-opus-4-7",
        list_price_in_per_m=15.0,
        list_price_out_per_m=75.0,
        long_context_flat=True,
        cache_read_per_m=1.50,
    ),
)


def list_tiers() -> list[ModelTier]:
    """Public tier list for bootstrap."""
    return [b.tier for b in TIER_BINDINGS]


def get_binding(tier_id: ModelTierId) -> TierBinding | None:
    """Return the binding for a tier id, or None if unknown."""
    for binding in TIER_BINDINGS:
        if binding.tier.id == tier_id:
            return binding
    return None


def is_known_tier(tier_id: str) -> bool:
    return any(b.tier.id == tier_id for b in TIER_BINDINGS)

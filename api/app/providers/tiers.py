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

from app.config import Settings, get_settings
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


# OpenAI(-compatible) per-tier pricing defaults (USD per million tokens),
# tracking the *default* model ids in `Settings` (gpt-4o-mini / gpt-4o / o1).
# `cache_read` is OpenAI's cached-input rate, which is 50% of the input rate for
# all of these models. Overriding the model via `OPENAI_MODEL_*` makes these
# prices APPROXIMATE — the binding still bills against these constants, not the
# substituted model's real card. Keyed by tier id.
_OPENAI_PRICING: dict[ModelTierId, tuple[float, float, float]] = {
    # tier id -> (in_per_m, out_per_m, cache_read_per_m)
    "fast": (0.15, 0.60, 0.075),  # gpt-4o-mini
    "smart": (2.50, 10.0, 1.25),  # gpt-4o
    "auto": (2.50, 10.0, 1.25),  # gpt-4o
    "pro": (15.0, 60.0, 7.50),  # o1
}


def _openai_model_for(tier_id: ModelTierId, s: Settings) -> str | None:
    """Map a tier id to its configured OpenAI model id, or None if unmapped."""
    return {
        "fast": s.openai_model_fast,
        "smart": s.openai_model_smart,
        "auto": s.openai_model_auto,
        "pro": s.openai_model_pro,
    }.get(tier_id)


def _openai_binding(tier_id: ModelTierId, s: Settings) -> TierBinding | None:
    """Build the OpenAI binding for a tier id, or None if unknown.

    Reuses the SAME `ModelTier` instance from `TIER_BINDINGS` so labels/hints
    stay byte-identical across backends (they're backend-independent and the FE
    contract must not change). Only the provider id, model id, and pricing
    differ.

    Returns None (rather than raising KeyError -> a 500 mid-request) if a future
    tier id lands in `TIER_BINDINGS` but isn't wired into `_OPENAI_PRICING` /
    `_openai_model_for` in lockstep; `get_binding` callers already treat None as
    an unknown tier.
    """
    base = next((b for b in TIER_BINDINGS if b.tier.id == tier_id), None)
    pricing = _OPENAI_PRICING.get(tier_id)
    model_id = _openai_model_for(tier_id, s)
    if base is None or pricing is None or model_id is None:
        return None
    in_per_m, out_per_m, cache_read_per_m = pricing
    return TierBinding(
        tier=base.tier,
        provider_id="openai",
        model_id=model_id,
        list_price_in_per_m=in_per_m,
        list_price_out_per_m=out_per_m,
        long_context_flat=True,
        cache_read_per_m=cache_read_per_m,
    )


def list_tiers() -> list[ModelTier]:
    """Public tier list for bootstrap.

    Backend-independent: tier ids/labels/hints never change with the provider,
    so this always reflects the canonical `TIER_BINDINGS` table.
    """
    return [b.tier for b in TIER_BINDINGS]


def get_binding(tier_id: ModelTierId, settings: Settings | None = None) -> TierBinding | None:
    """Return the binding for a tier id, or None if unknown.

    Backend-aware: when `PROVIDER_BACKEND=openai`, the returned binding points
    at the configured OpenAI model id + OpenAI pricing (reusing the canonical
    `ModelTier` so the FE-facing shape is identical). For `anthropic`/`fake`
    (the default), the canonical Anthropic `TIER_BINDINGS` table is used.

    `settings` is an optional override for tests / call sites that already hold
    a `Settings`; it defaults to the process-wide `get_settings()`.
    """
    s = settings if settings is not None else get_settings()
    if s.provider_backend == "openai":
        return _openai_binding(tier_id, s)
    for binding in TIER_BINDINGS:
        if binding.tier.id == tier_id:
            return binding
    return None


def is_known_tier(tier_id: str) -> bool:
    """Backend-independent: the set of known tier ids never changes."""
    return any(b.tier.id == tier_id for b in TIER_BINDINGS)


# Auto today routes to the same model class as "smart" (claude-sonnet-4-6 on
# Anthropic, gpt-4o on OpenAI). When real routing lands this constant becomes
# a per-request decision; for now it is a single mapping. The FE attribution
# row requires a concrete served tier (see
# `web/src/components/chat/attribution-row.tsx::assertServedTier`).
_AUTO_RESOLVES_TO: ModelTierId = "smart"


def resolve_served_tier(binding: TierBinding) -> tuple[ModelTierId, str]:
    """Resolve `(servedTierId, servedTierLabel)` for an attribution.

    For concrete tiers this is `(binding.tier.id, binding.tier.label)`. For the
    "auto" tier, the FE requires the wire to surface a concrete tier id so the
    attribution row can render which class of model actually served the turn —
    we resolve to the smart tier's id + label. Pricing still bills via the
    `binding` that was actually used (which for `auto` may be the auto-specific
    pricing if backends ever diverge).
    """
    if binding.tier.id == "auto":
        for candidate in TIER_BINDINGS:
            if candidate.tier.id == _AUTO_RESOLVES_TO:
                return candidate.tier.id, candidate.tier.label
    return binding.tier.id, binding.tier.label

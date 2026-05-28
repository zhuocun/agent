"""Cost computation + attribution assembly.

Per PRD 07 §7 rule 7: reasoning tokens bill at the OUTPUT rate and are never
cache-eligible. Enforced in `compute_cost_breakdown` — every call uses
output_per_m for reasoning_tokens, and cached_input_tokens never includes the
reasoning slice. A unit test asserts the delta.

For M1, cached input tokens are modeled at the input rate (no separate
`cache_read_per_m` in the tier registry yet). Documented as M1-only — M2 can
add a `cache_read_per_m` field on TierBinding when the FE renders it.
"""

from __future__ import annotations

from app.providers.protocol import UsageUpdate
from app.providers.tiers import TierBinding
from app.schemas.common import CostConfidence, ModelTierId
from app.schemas.message import (
    CostBreakdown,
    LongContext,
    ModelAttribution,
)


def compute_cost_breakdown(
    *,
    usage: UsageUpdate,
    binding: TierBinding,
) -> CostBreakdown:
    """Compute a CostBreakdown from accumulated usage + tier pricing.

    PRD 07 §7 rule 7: reasoning tokens x output_per_m / 1e6. Cached input
    tokens are modeled at input_per_m for M1 (no cache-read price column on
    TierBinding yet).
    """
    in_per_m = binding.list_price_in_per_m
    out_per_m = binding.list_price_out_per_m

    input_cost = usage.input_tokens * in_per_m / 1_000_000
    output_cost = usage.output_tokens * out_per_m / 1_000_000
    # PRD 07 §7 rule 7: reasoning bills at OUTPUT rate.
    reasoning_cost = usage.reasoning_tokens * out_per_m / 1_000_000
    # M1: model cached input at input rate. M2 can split out a cache_read price.
    cached_cost = usage.cached_input_tokens * in_per_m / 1_000_000

    subtotal = input_cost + output_cost + reasoning_cost + cached_cost

    # Anthropic = flat at M1 (PRD 07 §4.1). For tiered providers M2+ populates
    # appliedTier; the long_context invariant is enforced in the schema.
    long_context = LongContext(
        flat=binding.long_context_flat,
        tier_scope=None,
        tokens_repriced="none" if binding.long_context_flat else None,
        applied_tier=None,
        session_multiplier=None,
    )

    return CostBreakdown(
        currency="USD",
        list_price_in_per_m=in_per_m,
        list_price_out_per_m=out_per_m,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        long_context=long_context,
        promo_applied=False,
        subtotal_usd=subtotal,
        session_surcharge_usd=0.0,
    )


def build_attribution(
    *,
    requested_tier_id: ModelTierId,
    binding: TierBinding,
    breakdown: CostBreakdown,
    cost_confidence: CostConfidence,
    is_byok: bool = False,
) -> ModelAttribution:
    """Assemble a ModelAttribution. M1 never sets `substitution` — there is no
    fallback logic yet (M4)."""
    return ModelAttribution(
        requested_tier_id=requested_tier_id,
        served_tier_id=binding.tier.id,
        served_model_label=binding.tier.label,
        is_byok=is_byok,
        cost_usd=breakdown.subtotal_usd + breakdown.session_surcharge_usd,
        cost_confidence=cost_confidence,
        breakdown=breakdown,
        substitution=None,
    )

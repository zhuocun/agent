"""Cost computation + attribution assembly.

Per PRD 07 §7 rule 7: reasoning tokens bill at the OUTPUT rate and are never
cache-eligible. Enforced in `compute_cost_breakdown` — every call uses
output_per_m for reasoning_tokens, and cached_input_tokens never includes the
reasoning slice. A unit test asserts the delta.

Cache-read pricing (M4): when `TierBinding.cache_read_per_m` is set, cached
input tokens bill at that rate (Anthropic ~10% of input price). When None,
fall back to 10% of the input rate (the Anthropic cache-read convention).
"""

from __future__ import annotations

from app.providers.protocol import UsageUpdate
from app.providers.tiers import TierBinding, resolve_served_tier
from app.schemas.common import CostConfidence, ModelTierId
from app.schemas.message import (
    CostBreakdown,
    LongContext,
    ModelAttribution,
    Substitution,
)


def compute_cost_breakdown(
    *,
    usage: UsageUpdate,
    binding: TierBinding,
) -> CostBreakdown:
    """Compute a CostBreakdown from accumulated usage + tier pricing.

    PRD 07 §7 rule 7: reasoning tokens x output_per_m / 1e6. Cached input
    tokens bill at `cache_read_per_m` when the binding sets it (M4); otherwise
    they fall back to 10% of `input_per_m` (the Anthropic cache-read rate).
    """
    in_per_m = binding.list_price_in_per_m
    out_per_m = binding.list_price_out_per_m
    cache_per_m = (
        binding.cache_read_per_m
        if binding.cache_read_per_m is not None
        else 0.1 * in_per_m
    )

    input_cost = usage.input_tokens * in_per_m / 1_000_000
    output_cost = usage.output_tokens * out_per_m / 1_000_000
    # PRD 07 §7 rule 7: reasoning bills at OUTPUT rate.
    reasoning_cost = usage.reasoning_tokens * out_per_m / 1_000_000
    # M4: cache reads at their own per-million rate when set on the binding.
    cached_cost = usage.cached_input_tokens * cache_per_m / 1_000_000

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


_SUBSTITUTION_REASON_TEXT = {
    "auto_downgrade": "Downgraded by router for cost/latency.",
    "provider_fallback": "Provider unavailable; routed to a fallback model.",
    "rate_limited": "Primary provider was rate-limited; rerouted.",
    "capacity_reroute": "Capacity exceeded; rerouted to an available model.",
    "deprecated_model": "Requested model deprecated; substituted.",
    "gateway_route": "Gateway selected a different model.",
}


def build_attribution(
    *,
    requested_tier_id: ModelTierId,
    binding: TierBinding,
    breakdown: CostBreakdown,
    cost_confidence: CostConfidence,
    is_byok: bool = False,
    substitution: str | None = None,
    substituted_provider: str | None = None,
    substituted_model: str | None = None,
    substituted_display_label: str | None = None,
) -> ModelAttribution:
    """Assemble a ModelAttribution.

    M4: when `substitution` is set (one of the six wire-allowed
    `SubstitutionReasonCode` values), attach a `Substitution` object with a
    short canonical reason text. `substituted_display_label`, when provided,
    becomes `served_model_label` so the wire reflects the model actually
    served on a fallback (the whole point of the substitution feature);
    otherwise the registry default `binding.tier.label` is used.
    `substituted_provider`/`substituted_model` are not fields on the FE's
    `Substitution` shape today (the wire only carries `reasonCode` +
    `reasonText`) but are accepted so the call site can read them out of the
    same plumbing if needed later.
    """
    sub_obj: Substitution | None = None
    if substitution is not None:
        # Cast to the schema's literal at construction time — the schema's
        # SubstitutionReasonCode is the canonical guardrail.
        reason_text = _SUBSTITUTION_REASON_TEXT.get(substitution, "Substituted.")
        sub_obj = Substitution.model_validate(
            {"reasonCode": substitution, "reasonText": reason_text}
        )
    # Resolve `served_tier_id` + the default served-model label together so the
    # "auto" tier surfaces a concrete tier on the wire (see
    # `resolve_served_tier`) — the FE attribution row asserts a concrete tier.
    served_tier_id, served_tier_label = resolve_served_tier(binding)
    # On a fallback, show the served model's label; else the resolved label.
    served_model_label = (
        substituted_display_label
        if substituted_display_label is not None
        else served_tier_label
    )
    # `substituted_provider`/`substituted_model` have no wire field today;
    # reference them so unused-warning tooling stays quiet.
    _ = (substituted_provider, substituted_model)
    return ModelAttribution(
        requested_tier_id=requested_tier_id,
        served_tier_id=served_tier_id,
        served_model_label=served_model_label,
        is_byok=is_byok,
        cost_usd=breakdown.subtotal_usd + breakdown.session_surcharge_usd,
        cost_confidence=cost_confidence,
        breakdown=breakdown,
        substitution=sub_obj,
    )

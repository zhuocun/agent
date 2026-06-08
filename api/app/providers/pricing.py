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

from datetime import UTC, datetime

from app.providers.protocol import UsageUpdate
from app.providers.tiers import (
    PricingBand,
    TierBinding,
    get_provider_route,
    promo_active,
    resolve_served_tier,
)
from app.schemas.common import CostConfidence, ModelTierId
from app.schemas.message import (
    AppliedTier,
    CostBreakdown,
    LongContext,
    ModelAttribution,
    SessionMultiplier,
    Substitution,
)


def _base_rates(binding: TierBinding, now: datetime) -> tuple[float, float, float, bool]:
    """Resolve the (input, output, cache) per-million rates and the promo flag.

    A binding with an ACTIVE promo (T05) bills at the promo's rates; otherwise
    its list rates. The cache rate falls back to 10% of the input rate when the
    binding/promo leaves it unset (the Anthropic cache-read convention).
    """
    promo = binding.promo
    if promo_active(promo, now) and promo is not None:
        in_per_m = promo.price_in_per_m
        out_per_m = promo.price_out_per_m
        cache_source = (
            promo.cache_read_per_m
            if promo.cache_read_per_m is not None
            else binding.cache_read_per_m
        )
        promo_applied = True
    else:
        in_per_m = binding.list_price_in_per_m
        out_per_m = binding.list_price_out_per_m
        cache_source = binding.cache_read_per_m
        promo_applied = False
    cache_per_m = cache_source if cache_source is not None else 0.1 * in_per_m
    return in_per_m, out_per_m, cache_per_m, promo_applied


def _flat_subtotal(
    *,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
    cached_input_tokens: int,
    in_per_m: float,
    out_per_m: float,
    cache_per_m: float,
) -> float:
    """Baseline (no long-context surcharge) subtotal in USD.

    PRD 07 §7 rule 7: reasoning bills at the OUTPUT rate and is never
    cache-eligible. Cache reads bill at their own per-million rate.
    """
    input_cost = input_tokens * in_per_m / 1_000_000
    output_cost = output_tokens * out_per_m / 1_000_000
    reasoning_cost = reasoning_tokens * out_per_m / 1_000_000
    cached_cost = cached_input_tokens * cache_per_m / 1_000_000
    return input_cost + output_cost + reasoning_cost + cached_cost


def _select_band(bands: tuple[PricingBand, ...], context_tokens: int) -> PricingBand | None:
    """Highest band whose threshold the request context crossed, else None."""
    crossed = [b for b in bands if context_tokens >= b.threshold_tokens]
    if not crossed:
        return None
    return max(crossed, key=lambda b: b.threshold_tokens)


def compute_cost_breakdown(
    *,
    usage: UsageUpdate,
    binding: TierBinding,
    now: datetime | None = None,
    image_count: int = 0,
) -> CostBreakdown:
    """Compute a CostBreakdown from accumulated usage + tier pricing.

    Pricing layers, applied in order (each optional; with none set the result is
    byte-for-byte the historical flat computation):

    1. **Promo (T05).** An active `binding.promo` swaps the list rates for the
       promo rates and flips `promo_applied`. A lapsed promo is inert.
    2. **Image tokens (T19).** When image attachments are present and the binding
       sets an `image_token_formula`, its estimated tokens are added to the input
       bucket so multimodal turns bill for the image input.
    3. **Long-context surcharge (T05).** Either a whole-session reprice
       (`session_multiplier`, OpenAI style) or a stepped overage band
       (`pricing_tiers`, Gemini style) — never both (session wins if mis-set).
       The request-scoped delta over baseline is `session_surcharge_usd`.

    `now` defaults to the current UTC instant (drives the promo window) and is
    injectable so the promo-expiry boundary is unit-testable.
    """
    now = now if now is not None else datetime.now(UTC)
    in_per_m, out_per_m, cache_per_m, promo_applied = _base_rates(binding, now)

    # T19: image attachments add estimated input tokens on multimodal bindings.
    image_tokens = (
        binding.image_token_formula.tokens_for(image_count)
        if binding.image_token_formula is not None
        else 0
    )
    input_tokens = usage.input_tokens + image_tokens
    output_tokens = usage.output_tokens
    reasoning_tokens = usage.reasoning_tokens
    cached_input_tokens = usage.cached_input_tokens

    baseline = _flat_subtotal(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cached_input_tokens=cached_input_tokens,
        in_per_m=in_per_m,
        out_per_m=out_per_m,
        cache_per_m=cache_per_m,
    )

    # Token budget that decides whether a long-context threshold is crossed: the
    # prompt-side context (fresh input + cache reads). Output/reasoning are the
    # model's reply and don't count toward the prompt threshold.
    context_tokens = input_tokens + cached_input_tokens

    subtotal = baseline
    session_surcharge = 0.0
    long_context = LongContext(
        flat=binding.long_context_flat,
        tier_scope=None,
        tokens_repriced="none" if binding.long_context_flat else None,
        applied_tier=None,
        session_multiplier=None,
    )

    sm = binding.session_multiplier
    band = _select_band(binding.pricing_tiers, context_tokens) if binding.pricing_tiers else None

    if sm is not None and context_tokens >= sm.threshold_tokens:
        # (a) Whole-session reprice: input and output bill at list x multiplier.
        # Reasoning bills at the repriced OUTPUT rate; cache reads are unchanged.
        repriced = _flat_subtotal(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens,
            in_per_m=in_per_m * sm.input,
            out_per_m=out_per_m * sm.output,
            cache_per_m=cache_per_m,
        )
        session_surcharge = repriced - baseline
        subtotal = repriced
        long_context = LongContext(
            flat=False,
            tier_scope="session",
            tokens_repriced="all",
            applied_tier=None,
            session_multiplier=SessionMultiplier(input=sm.input, output=sm.output),
        )
    elif band is not None:
        # (b) Stepped overage band: only the input tokens ABOVE the band floor
        # reprice at the band's rate; everything below stays at the list rate.
        # The delta on those overflow tokens is the surcharge.
        over_input = max(0, input_tokens - band.threshold_tokens)
        surcharge = over_input * (band.price_in_per_m - in_per_m) / 1_000_000
        session_surcharge = surcharge
        subtotal = baseline + surcharge
        long_context = LongContext(
            flat=False,
            tier_scope="overage",
            tokens_repriced="above_threshold",
            applied_tier=AppliedTier(
                label=band.label,
                threshold_tokens=band.threshold_tokens,
                price_in_per_m=band.price_in_per_m,
                price_out_per_m=band.price_out_per_m,
            ),
            session_multiplier=None,
        )

    return CostBreakdown(
        currency="USD",
        list_price_in_per_m=in_per_m,
        list_price_out_per_m=out_per_m,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cached_input_tokens=cached_input_tokens,
        long_context=long_context,
        promo_applied=promo_applied,
        subtotal_usd=subtotal,
        session_surcharge_usd=session_surcharge,
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
    memory_applied: int = 0,
    memory_fact_ids: list[str] | None = None,
) -> ModelAttribution:
    """Assemble a ModelAttribution.

    M4: when `substitution` is set (one of the six wire-allowed
    `SubstitutionReasonCode` values), attach a `Substitution` object with a
    short canonical reason text. `substituted_display_label`, when provided,
    becomes `served_model_label` so the wire reflects the model actually
    served on a fallback (the whole point of the substitution feature);
    otherwise the served binding's `model_label` (e.g. "DeepSeek V4 Flash")
    is used, falling back to the tier label only when the binding carries no
    model label (the unrouted `auto` safety-net path).
    `substituted_provider`, when present, becomes the served provider identity
    on the attribution so persisted messages and logs disclose provider-side
    fallback. `substituted_model` is still bookkeeping only; the user-visible
    model name comes from `substituted_display_label`.
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
    # On a provider fallback, show the substituted model's label; otherwise the
    # served binding's model label (e.g. "DeepSeek V4 Flash"). Fall back to the
    # tier label only when the binding carries no model label (the unrouted
    # `auto` safety-net path), so the field is never empty.
    served_model_label = (
        substituted_display_label
        if substituted_display_label is not None
        else (binding.model_label or served_tier_label)
    )
    served_provider_id = substituted_provider or binding.provider_id
    route = get_provider_route(served_provider_id)
    # `substituted_model` has no wire field today; reference it so
    # unused-warning tooling stays quiet.
    _ = substituted_model
    return ModelAttribution(
        requested_tier_id=requested_tier_id,
        served_tier_id=served_tier_id,
        served_model_label=served_model_label,
        provider_id=served_provider_id,
        provider_label=route.label if route is not None else served_provider_id,
        is_byok=is_byok,
        cost_usd=breakdown.subtotal_usd + breakdown.session_surcharge_usd,
        cost_confidence=cost_confidence,
        breakdown=breakdown,
        substitution=sub_obj,
        # Omit a zero count so memory-off turns keep the pre-memory wire shape;
        # surface the positive count so the FE can render the "Memory used here"
        # chip (D19).
        memory_applied=memory_applied or None,
        # The injected fact ids ride alongside the count; empty ⇒ None so the
        # wire shape is unchanged for memory-off turns.
        memory_fact_ids=(list(memory_fact_ids) if memory_fact_ids else None),
    )

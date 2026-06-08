"""Pricing math unit tests.

Two required tests (per M1 spec):

1. PRD 07 §7 rule 7: reasoning tokens bill at the OUTPUT rate. Compute cost
   with and without reasoning_tokens; the delta must equal
   reasoning_tokens x output_per_m / 1e6.

2. LongContext invariant: `flat=True` produces no `appliedTier` and no
   `sessionMultiplier`. The schema's model_validator enforces "exactly one"
   when not flat — we cover both branches.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.providers.pricing import build_attribution, compute_cost_breakdown
from app.providers.protocol import UsageUpdate
from app.providers.tiers import TierBinding, get_binding
from app.schemas.message import AppliedTier, LongContext, SessionMultiplier


def test_reasoning_tokens_bill_at_output_rate() -> None:
    binding = get_binding("smart")
    assert binding is not None
    out_per_m = binding.list_price_out_per_m  # 15.0

    base = UsageUpdate(input_tokens=1000, output_tokens=500, reasoning_tokens=0)
    with_reasoning = UsageUpdate(
        input_tokens=1000, output_tokens=500, reasoning_tokens=200
    )

    b_base = compute_cost_breakdown(usage=base, binding=binding)
    b_with = compute_cost_breakdown(usage=with_reasoning, binding=binding)

    delta = b_with.subtotal_usd - b_base.subtotal_usd
    expected = 200 * out_per_m / 1_000_000

    assert delta == pytest.approx(expected, rel=1e-9)
    # And the cached input slot stays at zero — reasoning is never
    # cache-eligible (rule 7 second clause).
    assert b_base.cached_input_tokens == 0
    assert b_with.cached_input_tokens == 0


def test_long_context_flat_forbids_applied_tier_and_session_multiplier() -> None:
    # Flat=True with no extras succeeds.
    lc = LongContext(flat=True, tier_scope=None, tokens_repriced="none")
    assert lc.applied_tier is None
    assert lc.session_multiplier is None

    # Flat=True + appliedTier → ValidationError.
    with pytest.raises(ValidationError):
        LongContext(
            flat=True,
            applied_tier=AppliedTier(
                label="t1",
                threshold_tokens=128_000,
                price_in_per_m=5.0,
                price_out_per_m=15.0,
            ),
        )

    # Flat=True + sessionMultiplier → ValidationError.
    with pytest.raises(ValidationError):
        LongContext(
            flat=True,
            session_multiplier=SessionMultiplier(input=1.5, output=1.5),
        )

    # Flat=False + BOTH → ValidationError ("either, never both").
    with pytest.raises(ValidationError):
        LongContext(
            flat=False,
            applied_tier=AppliedTier(
                label="t1",
                threshold_tokens=128_000,
                price_in_per_m=5.0,
                price_out_per_m=15.0,
            ),
            session_multiplier=SessionMultiplier(input=1.5, output=1.5),
        )

    # Flat=False + appliedTier alone is fine.
    lc2 = LongContext(
        flat=False,
        applied_tier=AppliedTier(
            label="t1",
            threshold_tokens=128_000,
            price_in_per_m=5.0,
            price_out_per_m=15.0,
        ),
    )
    assert lc2.applied_tier is not None
    assert lc2.session_multiplier is None


def test_compute_cost_breakdown_includes_all_token_buckets() -> None:
    binding = get_binding("smart")
    assert binding is not None

    usage = UsageUpdate(
        input_tokens=2000,
        output_tokens=1000,
        reasoning_tokens=100,
        cached_input_tokens=500,
    )
    bd = compute_cost_breakdown(usage=usage, binding=binding)

    # Hand-computed: input + output + reasoning(@output) + cache(@cache_read).
    # Prices come from the binding (canonical DeepSeek table) so the assertion
    # stays backend-independent.
    cache_per_m = binding.cache_read_per_m
    assert cache_per_m is not None  # M4: smart tier sets cache_read_per_m.
    in_per_m = binding.list_price_in_per_m
    out_per_m = binding.list_price_out_per_m
    expected = (
        2000 * in_per_m / 1_000_000
        + 1000 * out_per_m / 1_000_000
        + 100 * out_per_m / 1_000_000
        + 500 * cache_per_m / 1_000_000
    )
    assert bd.subtotal_usd == pytest.approx(expected, rel=1e-9)
    assert bd.long_context.flat is True


def test_cache_read_uses_cache_read_per_m_when_set() -> None:
    """M4: cached input tokens bill at `cache_read_per_m`, not input_per_m.

    Per the M4 plan, when a binding sets `cache_read_per_m` the pricing math
    uses it. Expected cost is
    `(input * input_per_m + cached * cache_read_per_m) / 1_000_000` — never
    `(input + cached) * input_per_m / 1_000_000`.
    """
    binding = get_binding("smart")
    assert binding is not None
    cache_per_m = binding.cache_read_per_m
    assert cache_per_m is not None
    assert cache_per_m != binding.list_price_in_per_m

    usage = UsageUpdate(input_tokens=1000, cached_input_tokens=500)
    bd = compute_cost_breakdown(usage=usage, binding=binding)

    expected = (
        1000 * binding.list_price_in_per_m + 500 * cache_per_m
    ) / 1_000_000
    naive_wrong = 1500 * binding.list_price_in_per_m / 1_000_000

    assert bd.subtotal_usd == pytest.approx(expected, rel=1e-9)
    # Sanity: the M1 "model both at input rate" path would have produced
    # `naive_wrong`. Confirm we're not silently regressing.
    assert bd.subtotal_usd != pytest.approx(naive_wrong, rel=1e-9)


def test_cache_read_falls_back_to_ten_percent_of_input_when_unset() -> None:
    """When `cache_read_per_m` is None, fall back to 10% of input_per_m.

    Anthropic cache reads bill at ~10% of the input rate; the None fallback
    must reflect that, NOT the full input rate (which over-charges cache reads).
    """
    from app.providers.tiers import TierBinding
    from app.schemas.tier import ModelTier

    tier = ModelTier(
        id="smart",
        label="Smart",
        description="x",
        speed_hint="balanced",
        cost_hint="medium",
        context_hint="x",
    )
    legacy = TierBinding(
        tier=tier,
        provider_id="anthropic",
        model_id="x",
        list_price_in_per_m=3.0,
        list_price_out_per_m=15.0,
        long_context_flat=True,
        # cache_read_per_m omitted → None.
    )
    usage = UsageUpdate(input_tokens=1000, cached_input_tokens=500)
    bd = compute_cost_breakdown(usage=usage, binding=legacy)
    # Cache reads at 10% of input; input tokens at the full input rate.
    expected = (1000 * 3.0 + 500 * 0.1 * 3.0) / 1_000_000
    assert bd.subtotal_usd == pytest.approx(expected, rel=1e-9)
    # The old (wrong) fallback billed the cache bucket at the full input rate.
    naive_wrong = 1500 * 3.0 / 1_000_000
    assert bd.subtotal_usd != pytest.approx(naive_wrong, rel=1e-9)


def test_build_attribution_done_path() -> None:
    binding = get_binding("smart")
    assert binding is not None
    usage = UsageUpdate(input_tokens=10, output_tokens=20, reasoning_tokens=5)
    bd = compute_cost_breakdown(usage=usage, binding=binding)
    attr = build_attribution(
        requested_tier_id="smart",
        binding=binding,
        breakdown=bd,
        cost_confidence="exact",
    )
    assert attr.requested_tier_id == "smart"
    assert attr.served_tier_id == "smart"
    assert attr.cost_confidence == "exact"
    assert attr.substitution is None  # M1: no substitution.
    assert attr.cost_usd == pytest.approx(bd.subtotal_usd, rel=1e-9)


def test_build_attribution_uses_substituted_label_when_provided() -> None:
    """On a fallback, served_model_label must reflect the model actually served."""
    binding = get_binding("smart")
    assert binding is not None
    usage = UsageUpdate(input_tokens=10, output_tokens=20)
    bd = compute_cost_breakdown(usage=usage, binding=binding)

    # With a substituted label, the wire shows the served model, not the default.
    attr = build_attribution(
        requested_tier_id="smart",
        binding=binding,
        breakdown=bd,
        cost_confidence="estimate",
        substitution="provider_fallback",
        substituted_provider="openai",
        substituted_model="gpt-x",
        substituted_display_label="Fallback Model X",
    )
    assert attr.served_model_label == "Fallback Model X"
    assert attr.provider_id == "openai"
    assert attr.provider_label == "OpenAI"
    assert attr.served_model_label != binding.tier.label
    assert attr.substitution is not None
    assert attr.substitution.reason_code == "provider_fallback"

    # Without a substituted label, use the served binding's model label.
    attr_default = build_attribution(
        requested_tier_id="smart",
        binding=binding,
        breakdown=bd,
        cost_confidence="exact",
    )
    assert attr_default.served_model_label == binding.model_label
    assert attr_default.provider_id == binding.provider_id
    # The model label is distinct from the tier label, so this is non-trivial.
    assert binding.model_label != binding.tier.label


# Tiered long-context + promo + image pricing (T05 / T19) ---------------------


def _flat_binding(**overrides: object) -> TierBinding:
    """A minimal flat binding to layer tiered-pricing extras onto."""
    from app.schemas.tier import ModelTier

    tier = ModelTier(
        id="smart",
        label="Smart",
        description="x",
        speed_hint="balanced",
        cost_hint="medium",
        context_hint="x",
    )
    base: dict[str, object] = {
        "tier": tier,
        "provider_id": "deepseek",
        "model_id": "m",
        "list_price_in_per_m": 1.0,
        "list_price_out_per_m": 2.0,
        "long_context_flat": True,
        "cache_read_per_m": 0.1,
    }
    base.update(overrides)
    return TierBinding(**base)  # type: ignore[arg-type]


def test_session_multiplier_reprices_whole_request_above_threshold() -> None:
    """T05: a session multiplier reprices input AND output at list x multiplier
    once the prompt context crosses the threshold; the delta is the surcharge."""
    from app.providers.tiers import SessionMultiplierPricing

    binding = _flat_binding(
        long_context_flat=False,
        session_multiplier=SessionMultiplierPricing(
            threshold_tokens=1000, input=2.0, output=3.0
        ),
    )
    usage = UsageUpdate(input_tokens=2000, output_tokens=500)
    bd = compute_cost_breakdown(usage=usage, binding=binding)

    baseline = (2000 * 1.0 + 500 * 2.0) / 1_000_000
    repriced = (2000 * 1.0 * 2.0 + 500 * 2.0 * 3.0) / 1_000_000
    assert bd.subtotal_usd == pytest.approx(repriced, rel=1e-9)
    assert bd.session_surcharge_usd == pytest.approx(repriced - baseline, rel=1e-9)
    assert bd.long_context.flat is False
    assert bd.long_context.tier_scope == "session"
    assert bd.long_context.session_multiplier is not None
    assert bd.long_context.session_multiplier.input == 2.0


def test_session_multiplier_inert_below_threshold() -> None:
    """Below the threshold the session multiplier is a no-op (flat billing)."""
    from app.providers.tiers import SessionMultiplierPricing

    binding = _flat_binding(
        long_context_flat=False,
        session_multiplier=SessionMultiplierPricing(
            threshold_tokens=10_000, input=2.0, output=3.0
        ),
    )
    usage = UsageUpdate(input_tokens=1000, output_tokens=500)
    bd = compute_cost_breakdown(usage=usage, binding=binding)
    assert bd.session_surcharge_usd == 0.0
    assert bd.subtotal_usd == pytest.approx((1000 * 1.0 + 500 * 2.0) / 1_000_000)


def test_pricing_band_surcharges_only_overflow_input_tokens() -> None:
    """T05: a Gemini-style band reprices only the input tokens ABOVE the band
    floor at the band rate; tokens below stay at the list rate."""
    from app.providers.tiers import PricingBand

    binding = _flat_binding(
        long_context_flat=False,
        pricing_tiers=(
            PricingBand(
                threshold_tokens=1000,
                price_in_per_m=5.0,
                price_out_per_m=10.0,
                label="long",
            ),
        ),
    )
    usage = UsageUpdate(input_tokens=3000, output_tokens=100)
    bd = compute_cost_breakdown(usage=usage, binding=binding)

    baseline = (3000 * 1.0 + 100 * 2.0) / 1_000_000
    over_input = 3000 - 1000
    surcharge = over_input * (5.0 - 1.0) / 1_000_000
    assert bd.session_surcharge_usd == pytest.approx(surcharge, rel=1e-9)
    assert bd.subtotal_usd == pytest.approx(baseline + surcharge, rel=1e-9)
    assert bd.long_context.tier_scope == "overage"
    assert bd.long_context.applied_tier is not None
    assert bd.long_context.applied_tier.threshold_tokens == 1000


def test_session_multiplier_wins_when_both_pricing_modes_set() -> None:
    """When a binding mis-sets BOTH a session multiplier and bands, the
    whole-session reprice wins and the bands are ignored (documented behavior)."""
    from app.providers.tiers import PricingBand, SessionMultiplierPricing

    binding = _flat_binding(
        long_context_flat=False,
        session_multiplier=SessionMultiplierPricing(
            threshold_tokens=1000, input=2.0, output=2.0
        ),
        pricing_tiers=(
            PricingBand(threshold_tokens=1000, price_in_per_m=99.0, price_out_per_m=99.0),
        ),
    )
    usage = UsageUpdate(input_tokens=2000, output_tokens=500)
    bd = compute_cost_breakdown(usage=usage, binding=binding)
    assert bd.long_context.tier_scope == "session"


def test_active_promo_reprices_at_promo_rates() -> None:
    """T05: an active promo bills at the promo rates and flips `promo_applied`."""
    from datetime import UTC, datetime, timedelta

    from app.providers.tiers import PromoPricing

    now = datetime.now(UTC)
    binding = _flat_binding(
        promo=PromoPricing(
            promo_id="launch",
            price_in_per_m=0.5,
            price_out_per_m=1.0,
            effective_until=now + timedelta(days=1),
        ),
    )
    usage = UsageUpdate(input_tokens=1000, output_tokens=1000)
    bd = compute_cost_breakdown(usage=usage, binding=binding, now=now)
    assert bd.promo_applied is True
    assert bd.subtotal_usd == pytest.approx((1000 * 0.5 + 1000 * 1.0) / 1_000_000)
    assert bd.list_price_in_per_m == 0.5


def test_lapsed_promo_is_inert() -> None:
    """An expired promo reverts to list rates with no other change."""
    from datetime import UTC, datetime, timedelta

    from app.providers.tiers import PromoPricing

    now = datetime.now(UTC)
    binding = _flat_binding(
        promo=PromoPricing(
            promo_id="launch",
            price_in_per_m=0.5,
            price_out_per_m=1.0,
            effective_until=now - timedelta(seconds=1),
        ),
    )
    usage = UsageUpdate(input_tokens=1000, output_tokens=1000)
    bd = compute_cost_breakdown(usage=usage, binding=binding, now=now)
    assert bd.promo_applied is False
    assert bd.subtotal_usd == pytest.approx((1000 * 1.0 + 1000 * 2.0) / 1_000_000)


def test_image_token_formula_adds_input_tokens_only_when_present() -> None:
    """T19: image attachments add estimated input tokens on a multimodal binding;
    a binding with no formula is unchanged, and zero images add nothing."""
    from app.providers.tiers import ImageTokenFormula

    binding = _flat_binding(
        image_token_formula=ImageTokenFormula(base_tokens=85, tokens_per_image=170),
    )
    usage = UsageUpdate(input_tokens=1000, output_tokens=0)

    # No images -> no image tokens.
    none_bd = compute_cost_breakdown(usage=usage, binding=binding, image_count=0)
    assert none_bd.input_tokens == 1000

    # Two images -> base + 2*per_image extra INPUT tokens, billed at input rate.
    bd = compute_cost_breakdown(usage=usage, binding=binding, image_count=2)
    extra = 85 + 170 * 2
    assert bd.input_tokens == 1000 + extra
    assert bd.subtotal_usd == pytest.approx((1000 + extra) * 1.0 / 1_000_000)

    # A binding with no formula ignores image_count entirely.
    plain = _flat_binding()
    plain_bd = compute_cost_breakdown(usage=usage, binding=plain, image_count=5)
    assert plain_bd.input_tokens == 1000


def test_tiered_pricing_fields_default_to_flat_billing() -> None:
    """Backward compat: a binding that sets NONE of the T05/T19 extras bills
    exactly the historical flat amount (`long_context_flat` stays authoritative)."""
    binding = _flat_binding()
    assert binding.session_multiplier is None
    assert binding.pricing_tiers == ()
    assert binding.promo is None
    assert binding.image_token_formula is None
    usage = UsageUpdate(input_tokens=1000, output_tokens=500, cached_input_tokens=200)
    bd = compute_cost_breakdown(usage=usage, binding=binding)
    expected = (1000 * 1.0 + 500 * 2.0 + 200 * 0.1) / 1_000_000
    assert bd.subtotal_usd == pytest.approx(expected, rel=1e-9)
    assert bd.session_surcharge_usd == 0.0
    assert bd.long_context.flat is True


def test_build_attribution_unrouted_auto_falls_back_to_tier_label() -> None:
    """The raw `auto` binding (unrouted safety-net) carries no model_label, so
    served_model_label falls back to the resolved tier label — never empty."""
    binding = get_binding("auto")
    assert binding is not None
    assert binding.model_label == ""  # safety-net precondition
    usage = UsageUpdate(input_tokens=10, output_tokens=20)
    bd = compute_cost_breakdown(usage=usage, binding=binding)

    attr = build_attribution(
        requested_tier_id="auto",
        binding=binding,
        breakdown=bd,
        cost_confidence="estimate",
    )
    # resolve_served_tier maps auto -> smart, label "Smart".
    assert attr.served_tier_id == "smart"
    assert attr.served_model_label == "Smart"
    assert attr.served_model_label != ""

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
from app.providers.tiers import get_binding
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
    # The model label is distinct from the tier label, so this is non-trivial.
    assert binding.model_label != binding.tier.label


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

"""Auto-tier router (v0) unit tests.

Covers the deterministic complexity classifier in `app.providers.router` and
the honest-substitution contract it feeds: routing CHEAPER than the `smart`
baseline is a downgrade and must surface `auto_downgrade` in the attribution;
routing to the baseline (or escalating above it) surfaces no substitution.

The classifier is pure + synchronous, so these are plain table-driven cases —
no DB, no event loop, no provider.
"""

from __future__ import annotations

import pytest

from app.providers.pricing import build_attribution, compute_cost_breakdown
from app.providers.protocol import ChatMessage as ProviderChatMessage
from app.providers.protocol import UsageUpdate
from app.providers.router import AUTO_BASELINE_TIER, route_auto
from app.providers.tiers import get_binding
from app.schemas.common import ModelTierId


def _history(n: int) -> list[ProviderChatMessage]:
    """Build `n` alternating prior turns for the deep-history signal."""
    return [
        ProviderChatMessage(
            role="user" if i % 2 == 0 else "assistant", text=f"turn {i}"
        )
        for i in range(n)
    ]


@pytest.mark.parametrize(
    ("text", "expected_tier"),
    [
        # Short, signal-free small talk -> cheapest capable tier (score 0).
        ("hi", "fast"),
        ("thanks!", "fast"),
        ("what time is it in Tokyo?", "fast"),
        # A SINGLE light cue (one keyword, one math term) stays cheap: the v0
        # weights only lift to `smart` at score >= 2, so a lone cue (+1) is
        # still `fast`. Cheapest-capable by design.
        ("Solve the integral of x^2 dx.", "fast"),
        ("def foo(): return bar", "fast"),
        # A code FENCE (+2) is a strong enough single signal -> smart baseline.
        ("Here is a code block:\n```\nprint('x')\n```", "smart"),
        # Explicit reasoning cue alone (+2) -> smart baseline.
        ("Please analyze this situation.", "smart"),
        # Strong compound complexity (code fence +2, reasoning +2 = 4) -> pro.
        (
            "```python\ndef f(x): return x\n```\n"
            "Please reason step by step about why this is wrong and prove it.",
            "pro",
        ),
        # Reasoning (+2) + math (+1) + a code cue (+1) = 4 -> pro.
        (
            "Derive the theorem and prove it for matrix A: $$\\int_0^1 x\\,dx$$. "
            "Walk me through step by step; def helper() may be relevant.",
            "pro",
        ),
    ],
)
def test_route_auto_classifies_text(text: str, expected_tier: ModelTierId) -> None:
    routed = route_auto(text)
    assert routed.tier_id == expected_tier


def test_very_long_prompt_escalates_off_fast() -> None:
    """A very long prompt is itself a strong complexity signal (+2 -> smart)."""
    long_text = "Summarize the following document. " + ("word " * 800)
    routed = route_auto(long_text)
    assert "very_long_prompt" in routed.signals
    assert routed.tier_id in ("smart", "pro")
    assert routed.tier_id != "fast"


def test_deep_history_contributes_a_signal() -> None:
    """A deep back-and-forth contributes a complexity signal (+1).

    On its own (+1) it doesn't cross the `smart` threshold, but combined with a
    light cue it tips the turn off `fast` — exercising that depth is wired in.
    """
    shallow = route_auto("integral of x", _history(2))
    deep = route_auto("integral of x", _history(10))
    assert "deep_history" not in shallow.signals
    assert "deep_history" in deep.signals
    # Shallow: math cue alone (+1) -> fast. Deep: math (+1) + depth (+1) -> smart.
    assert shallow.tier_id == "fast"
    assert deep.tier_id == "smart"


def test_route_auto_is_deterministic() -> None:
    """Same input -> same output, every time (no randomness/I/O)."""
    text = "Explain why this code segfaults: int *p = 0; *p = 1;"
    first = route_auto(text)
    second = route_auto(text)
    assert first == second


def test_downgrade_flag_matches_baseline() -> None:
    """`is_downgrade` is True only when routed cheaper than the smart baseline."""
    assert AUTO_BASELINE_TIER == "smart"
    fast = route_auto("hi")
    assert fast.tier_id == "fast"
    assert fast.is_downgrade is True  # fast is cheaper than smart -> downgrade.

    smart = route_auto("Here is a code block:\n```\nprint('x')\n```")
    assert smart.tier_id == "smart"
    assert smart.is_downgrade is False  # baseline -> no downgrade.

    pro = route_auto(
        "```py\nx=1\n```\nplease reason step by step and prove correctness."
    )
    assert pro.tier_id == "pro"
    assert pro.is_downgrade is False  # escalation is not a downgrade.


# --- Honest-substitution contract through build_attribution -------------------


def test_downgrade_emits_auto_downgrade_substitution() -> None:
    """An auto downgrade (routed to `fast`) surfaces `auto_downgrade` honestly.

    Mirrors the route's seam: the routed concrete binding is what bills + sets
    the served tier; `requested_tier_id` stays `auto`; the router-side
    substitution is `auto_downgrade`.
    """
    routed = route_auto("hi")  # -> fast, downgrade
    assert routed.is_downgrade is True

    binding = get_binding(routed.tier_id)
    assert binding is not None
    usage = UsageUpdate(input_tokens=10, output_tokens=20)
    bd = compute_cost_breakdown(usage=usage, binding=binding)
    attr = build_attribution(
        requested_tier_id="auto",
        binding=binding,
        breakdown=bd,
        cost_confidence="exact",
        substitution="auto_downgrade" if routed.is_downgrade else None,
    )
    assert attr.requested_tier_id == "auto"
    # Served tier is the routed concrete tier (never "auto" on the wire).
    assert attr.served_tier_id == "fast"
    assert attr.substitution is not None
    assert attr.substitution.reason_code == "auto_downgrade"


def test_baseline_route_emits_no_substitution() -> None:
    """Routing to the baseline (`smart`) emits no substitution."""
    # A code fence (+2) is a single strong signal -> smart baseline.
    routed = route_auto("Here is a code block:\n```\nprint('x')\n```")
    assert routed.tier_id == "smart"
    assert routed.is_downgrade is False

    binding = get_binding(routed.tier_id)
    assert binding is not None
    usage = UsageUpdate(input_tokens=10, output_tokens=20)
    bd = compute_cost_breakdown(usage=usage, binding=binding)
    attr = build_attribution(
        requested_tier_id="auto",
        binding=binding,
        breakdown=bd,
        cost_confidence="exact",
        substitution="auto_downgrade" if routed.is_downgrade else None,
    )
    assert attr.served_tier_id == "smart"
    assert attr.substitution is None


def test_escalation_to_pro_emits_no_substitution() -> None:
    """Escalating above the baseline (`pro`) is not a downgrade -> no sub."""
    routed = route_auto(
        "```py\nx=1\n```\nplease reason step by step and prove correctness."
    )
    assert routed.tier_id == "pro"
    assert routed.is_downgrade is False

    binding = get_binding(routed.tier_id)
    assert binding is not None
    usage = UsageUpdate(input_tokens=10, output_tokens=20)
    bd = compute_cost_breakdown(usage=usage, binding=binding)
    attr = build_attribution(
        requested_tier_id="auto",
        binding=binding,
        breakdown=bd,
        cost_confidence="exact",
        substitution="auto_downgrade" if routed.is_downgrade else None,
    )
    assert attr.served_tier_id == "pro"
    assert attr.substitution is None

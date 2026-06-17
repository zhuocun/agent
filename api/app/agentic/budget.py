"""Agentic run budget: worst-case cost estimate + admission control (M3).

Reuses `app/providers/pricing.py` — there is NO parallel cost model. The per-run
budget is enforced at two gates (PRD 01 §"Cost & budget"):

- **Pre-spawn reservation** (`estimate_run_cost` + `admit`). Before fan-out, the
  orchestrator estimates the run's WORST-CASE cost and reserves it against the
  per-run cap (`AGENTIC_RUN_BUDGET_USD`) composed with the caller's remaining
  user/platform headroom. If the estimate already exceeds the effective cap the
  run is NOT admitted — the orchestrator degrades gracefully to a labeled
  empty/partial synthesis instead of silently overrunning.
- **Mid-flight kill** (`exceeds_cap`). Because the reservation is only an
  estimate, the orchestrator also checks the ACTUAL accumulated cost (from
  `pricing.py`, summed as each worker's `SubagentDone` lands) against the cap.
  On breach it stops spawning, cancels in-flight workers, and aggregates the
  workers that completed (a labeled partial synthesis).

The estimate is sized against the PRODUCT of the two FR-26g multipliers
(reasoning-token burn x multi-agent fan-out burn), not either alone, so the cap
guards the realistic worst case rather than a single-turn baseline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.config import Settings
from app.providers.pricing import compute_cost_breakdown
from app.providers.protocol import UsageUpdate
from app.providers.tiers import TierBinding

# A `CostForUsage`-style callable that prices an accumulated usage. Supplied by
# the handler so estimation stays provider-agnostic when a pre-built pricer is
# more convenient than a (binding, image_count) pair.
CostForUsage = Callable[[UsageUpdate], float]


@dataclass(frozen=True)
class BudgetDecision:
    """Outcome of the pre-spawn admission check."""

    estimated_usd: float
    cap_usd: float
    effective_cap_usd: float
    admitted: bool


def _subagent_count(sub_question_count: int, settings: Settings) -> int:
    """Worker count + aggregator (+ verifier passes when enabled)."""
    workers = max(1, sub_question_count)
    count = workers + 1  # + aggregator
    if settings.agentic_verifier:
        count += max(0, settings.agentic_verifier_n)
    return count


def _expected_subagent_usage(settings: Settings) -> UsageUpdate:
    """Worst-case per-subagent token expectation over the round bound."""
    rounds = max(1, settings.tool_max_rounds)
    return UsageUpdate(
        input_tokens=settings.agentic_expected_input_tokens_per_round * rounds,
        output_tokens=settings.agentic_expected_output_tokens_per_round * rounds,
    )


def estimate_run_cost(
    *,
    sub_question_count: int,
    binding: TierBinding,
    settings: Settings,
    image_count: int = 0,
) -> float:
    """Estimate a deep-research run's worst-case USD cost.

    `Σ subagent estimates x reasoning-multiplier x fan-out-multiplier`, where
    each subagent's estimate is `expected_tokens x tier_price` from
    `pricing.py`. This is the number the plan-approval terminal surfaces as the
    estimated cost and the number the pre-spawn reservation holds.
    """
    per_subagent = _expected_subagent_usage(settings)
    breakdown = compute_cost_breakdown(
        usage=per_subagent,
        binding=binding,
        image_count=image_count,
    )
    base = breakdown.subtotal_usd + breakdown.session_surcharge_usd
    subagents = _subagent_count(sub_question_count, settings)
    return (
        base
        * subagents
        * settings.agentic_reasoning_token_multiplier
        * settings.agentic_fanout_token_multiplier
    )


def effective_cap(*, cap_usd: float, headroom_usd: float | None) -> float:
    """Compose the per-run cap with the caller's remaining headroom.

    The run must fit BOTH the per-run cap and whatever user/platform budget the
    caller has left, so the effective cap is the minimum. A non-positive / None
    headroom means "no extra constraint" (cap only) — e.g. BYOK turns that are
    exempt from platform caps but still capped per-run.
    """
    if headroom_usd is None or headroom_usd <= 0:
        return cap_usd
    return min(cap_usd, headroom_usd)


def admit(
    *,
    estimated_usd: float,
    cap_usd: float,
    headroom_usd: float | None = None,
) -> BudgetDecision:
    """Pre-spawn reservation: admit iff the estimate fits the effective cap."""
    cap = effective_cap(cap_usd=cap_usd, headroom_usd=headroom_usd)
    return BudgetDecision(
        estimated_usd=estimated_usd,
        cap_usd=cap_usd,
        effective_cap_usd=cap,
        admitted=estimated_usd <= cap,
    )


def exceeds_cap(
    *,
    actual_usd: float,
    cap_usd: float,
    headroom_usd: float | None = None,
) -> bool:
    """Mid-flight check: has the ACTUAL accumulated cost breached the cap?"""
    return actual_usd > effective_cap(cap_usd=cap_usd, headroom_usd=headroom_usd)

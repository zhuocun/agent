"""`TurnMoney` — the turn's accounting owner (`app.streaming.turn_money`).

The arithmetic itself is covered where it always was: `test_pricing.py` pins the
per-phase image billing and the phase pricers through the handler, and
`test_arch_review_ledger_resume.py` pins the boundary triple. What is NOT covered
there is the one seam that carving the money out of `stream_and_persist`
introduced: the working route now has TWO writers. The handler rebinds its own
`binding` when a pre-first-token provider fallback fires, and `TurnMoney` holds
the same route so its pricers follow. A rebind that updates only one of them
would silently price a fallback-served turn on the primary route — so the
pairing is asserted structurally here rather than left to reviewer memory.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from app.config import get_settings
from app.providers.pricing import compute_cost_breakdown
from app.providers.protocol import UsageUpdate
from app.providers.tiers import get_binding
from app.streaming.turn_money import TurnMoney
from app.streaming.turn_reducer import TurnState


def _money() -> TurnMoney:
    primary = get_binding("smart")
    assert primary is not None
    # A synthetic fallback route: the wired tiers can share a price, and then
    # "priced on the other route" would be unobservable.
    fallback = replace(
        primary,
        list_price_in_per_m=primary.list_price_in_per_m * 3.0 + 1.0,
        list_price_out_per_m=primary.list_price_out_per_m * 3.0 + 1.0,
    )
    return TurnMoney(
        settings=get_settings(),
        binding=primary,
        fallback_binding=fallback,
        image_attachment_count=0,
        state=TurnState(),
        agentic_active=True,
        resume_seed=None,
    )


def test_rebind_moves_the_working_route_pricers_to_the_fallback() -> None:
    """A fallback rebuild must re-price AND re-estimate on the fallback route."""
    money = _money()
    usage = UsageUpdate(input_tokens=1000, output_tokens=500)
    primary_cost = money.cost_for_usage(usage)
    primary_verifier = money.verifier_cost_for_usage(usage)
    primary_estimate = money.estimate_run_cost(3)

    fallback = money.fallback_binding
    assert fallback is not None
    money.rebind(fallback)

    expected = compute_cost_breakdown(usage=usage, binding=fallback, image_count=0)
    assert money.cost_for_usage(usage) == pytest.approx(expected.subtotal_usd)
    assert money.verifier_cost_for_usage(usage) == pytest.approx(expected.subtotal_usd)
    assert money.cost_for_usage(usage) != pytest.approx(primary_cost)
    assert money.verifier_cost_for_usage(usage) != pytest.approx(primary_verifier)
    assert money.estimate_run_cost(3) != pytest.approx(primary_estimate)


def test_the_fallback_pricer_ignores_the_working_route_entirely() -> None:
    """`fallback_cost_for_usage` names its route; a rebind cannot move it."""
    money = _money()
    usage = UsageUpdate(input_tokens=1000, output_tokens=500)
    fallback = money.fallback_binding
    assert fallback is not None
    before = money.fallback_cost_for_usage(usage)
    money.rebind(replace(fallback, list_price_out_per_m=999.0))
    assert money.fallback_cost_for_usage(usage) == pytest.approx(before)


def test_every_working_route_rebind_also_rebinds_the_money_owner() -> None:
    """Two writers for one route, so the pairing is a static invariant.

    `stream_and_persist` reassigns its own `binding` on the one-shot provider
    fallback retry; `TurnMoney` must be pointed at the same route in the same
    breath. Asserted over the source because the alternative is a reviewer
    noticing — and the failure mode (a fallback-served turn priced on the primary
    route) is invisible on the wire.
    """
    source = (
        Path(__file__).resolve().parents[1] / "app" / "streaming" / "handler.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    handler = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "stream_and_persist"
    )

    def _assigns_binding(stmt: ast.stmt) -> bool:
        return isinstance(stmt, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "binding"
            for target in stmt.targets
        )

    def _rebinds_money(stmt: ast.stmt) -> bool:
        return (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Attribute)
            and stmt.value.func.attr == "rebind"
            and isinstance(stmt.value.func.value, ast.Name)
            and stmt.value.func.value.id == "turn_money"
        )

    rebinds = 0
    for node in ast.walk(handler):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        for index, stmt in enumerate(body):
            if not _assigns_binding(stmt):
                continue
            rebinds += 1
            following = body[index + 1 :]
            assert any(_rebinds_money(later) for later in following), (
                "line "
                f"{stmt.lineno}: `binding` was reassigned without a following "
                "`turn_money.rebind(...)`, so the turn's pricers would keep "
                "pricing the route the turn is no longer using"
            )
    # The fallback retry is the only rebind; if a second one appears the pairing
    # above covers it, but the count is pinned so a REMOVED rebind is not read as
    # a vacuously passing loop.
    assert rebinds == 1

"""One owner for a turn's money arithmetic.

Every dollar figure a streaming turn produces — the per-phase pricers handed to
the orchestrator, the pre-spawn admission estimate, and the
(breakdown, cumulative, newly billable) triple a persistable boundary needs —
is computed here rather than by closures captured inside
`handler.stream_and_persist`. The arithmetic is unchanged; what changes is that
it has a name and a constructor instead of reaching into a 2500-line function's
locals.

Two pieces of turn state are read at CALL time, not construction time, and that
is load-bearing:

- `binding` is the WORKING route. A pre-first-token provider fallback rebinds it
  mid-turn (`rebind`), and every pricer must follow — an estimate made after the
  rebuild has to price the fallback route.
- `state` is the turn's fold (`TurnReducer`'s only output). The estimate paths
  read whatever phase facts have landed by the time a boundary is reached.
"""

from __future__ import annotations

from typing import Protocol

from app.agentic import budget
from app.config import Settings
from app.providers.pricing import compute_cost_breakdown
from app.providers.protocol import UsageUpdate
from app.providers.tiers import TierBinding
from app.runtime.run_receipt import RunReceipt
from app.schemas.message import CostBreakdown
from app.streaming.turn_reducer import TurnState


class ResumeMoneySeed(Protocol):
    """The pause-ledger fields the already-billed floor reconstruction reads.

    Structural so this module does not import the handler that defines
    `ResumeToolSeed` (the handler imports this one). Only the money seeds are
    named here; everything else on a resume seed is the handler's business.
    """

    prior_run_cost_usd: float
    prior_receipt: RunReceipt | None
    agentic_continuation: object


class TurnMoney:
    """The turn's accounting collaborator, built once per turn.

    `binding` starts at the primary route and is replaced by `rebind` when a
    provider fallback retry fires, mirroring the handler's own working-route
    rebind so both price the same route.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        binding: TierBinding,
        fallback_binding: TierBinding | None,
        image_attachment_count: int,
        state: TurnState,
        agentic_active: bool,
        resume_seed: ResumeMoneySeed | None,
    ) -> None:
        self.settings = settings
        self.binding = binding
        self.fallback_binding = fallback_binding
        self.image_attachment_count = image_attachment_count
        self.state = state
        self.agentic_active = agentic_active
        self.resume_seed = resume_seed

    def rebind(self, binding: TierBinding) -> None:
        """Point the pricers at the route a provider fallback retry switched to."""
        self.binding = binding

    def phase_image_count(self, subagent_id: str | None, role: str | None) -> int:
        """Charging follows transport: a phase pays for what its stream sends.

        `image_token_formula` folds estimated image tokens into the input bucket,
        so a phase is charged the turn's `image_attachment_count` if and only if
        that phase's stream factory actually attaches the images. Every factory
        — `_build_raw_stream` (single primary, and the planner / worker /
        aggregator phases via `_agentic_make_stream`) and
        `_agentic_fallback_make_stream` — passes `attachments=attachments`
        unconditionally, so those prompts are NOT text-only and the provider
        re-charges the images on each of those calls.

        The verifier is the sole genuinely text-only phase:
        `_agentic_fresh_make_stream` passes `attachments=None` for its
        fresh-context judge session, so it never pays for the turn's images.

        (Supersedes FL-36, whose premise that planner / worker / aggregator
        prompts are text-only was false and made every deep_research turn with
        attachments under-bill the whole image component.)
        """
        _ = subagent_id
        if role == "verifier":
            return 0
        return self.image_attachment_count

    def cost_for_usage(self, usage: UsageUpdate) -> float:
        """Price an accumulated usage for the active binding (agentic only).

        FL-34-b: `subtotal_usd` **is** the total — `session_surcharge_usd` is a
        disclosure field describing part of it, so adding it double-charges the
        long-context surcharge.
        Image tokens are charged on every phase this prices, because every
        non-verifier stream factory sends the turn's attachments (see
        `phase_image_count`). The verifier is priced by
        `verifier_cost_for_usage` instead.
        """
        breakdown = compute_cost_breakdown(
            usage=usage,
            binding=self.binding,
            image_count=self.image_attachment_count,
        )
        return breakdown.subtotal_usd

    def verifier_cost_for_usage(self, usage: UsageUpdate) -> float:
        """Phase pricer for the fresh-context judge (V-011).

        The verifier sends ``attachments=None``; never inherit the turn's image
        attachment count into judge pricing.
        """
        breakdown = compute_cost_breakdown(
            usage=usage,
            binding=self.binding,
            image_count=0,
        )
        return breakdown.subtotal_usd

    def fallback_cost_for_usage(self, usage: UsageUpdate) -> float:
        """Price usage against the fallback binding (FE-009).

        `_agentic_fallback_make_stream` sends the turn's attachments too, so the
        fallback route is charged the image component exactly like the primary.
        """
        assert self.fallback_binding is not None
        breakdown = compute_cost_breakdown(
            usage=usage,
            binding=self.fallback_binding,
            image_count=self.image_attachment_count,
        )
        return breakdown.subtotal_usd

    def estimate_run_cost(self, sub_question_count: int) -> float:
        """Worst-case run-cost estimate for pre-spawn admission (agentic only).

        Called module-qualified so the budget methodology stays in one place
        (and stays test-overridable). Reads the working `binding` at call time so
        a fallback rebuild re-estimates against the fallback route.
        """
        return budget.estimate_run_cost(
            sub_question_count=sub_question_count,
            binding=self.binding,
            settings=self.settings,
            image_count=self.image_attachment_count,
        )

    def already_billed_floor_usd(self) -> float:
        """Spend a prior pause turn already charged, for the stop estimate only.

        Exact accounting reads this off the receipt's own
        `already_billed_cost_usd`; this reconstruction exists solely so an
        estimate cannot re-charge pre-pause dollars.
        """
        resume_seed = self.resume_seed
        if resume_seed is None:
            return 0.0
        if resume_seed.prior_receipt is not None:
            return resume_seed.prior_receipt.cumulative_cost_usd
        already = float(resume_seed.prior_run_cost_usd or 0.0)
        cont = resume_seed.agentic_continuation
        if cont is not None:
            already += float(getattr(cont, "paused_worker_cost_usd", 0.0) or 0.0)
        return already

    def estimated_agentic_cost_usd(self) -> float:
        """ESTIMATE-ONLY cumulative agentic spend. Never an exact authority.

        Reached only when a turn ended before the orchestrator could emit a
        receipt-bearing boundary `RunCost` — an abrupt stop or disconnect
        mid-run. It prices the settled phase facts the fold already holds: each
        scope's own `SubagentDone` cost, or a still in-flight scope's latest
        usage against the binding that served it.
        """
        estimated = 0.0
        for acc in self.state.scopes.values():
            if acc.cost_usd is not None:
                estimated += acc.cost_usd
                continue
            has_tokens = bool(
                acc.usage.input_tokens
                or acc.usage.output_tokens
                or acc.usage.reasoning_tokens
                or acc.usage.cached_input_tokens
            )
            if not has_tokens:
                continue
            if acc.substitution is not None and self.fallback_binding is not None:
                estimated += self.fallback_cost_for_usage(acc.usage)
            else:
                estimated += self.cost_for_usage(acc.usage)
        return estimated

    def boundary_money(self) -> tuple[CostBreakdown, float, float]:
        """(breakdown, cumulative, newly billable) for a persistable boundary.

        AC-02/AC-03: a banked `RunCost.receipt` is the SOLE exact authority for
        an agentic run, and it wins on every path. It is the orchestrator's own
        accounting for the boundary being persisted, which is why the old
        reconstruction — a total re-derived from whichever `SubagentDone` events
        happened to arrive, minus an already-billed part re-derived from one
        scalar seed — reported `$0.37` on the wire and `$0.00` on the row for a
        plan-approved resume. A receipt-less display tick banks nothing, so it
        can never reach this arithmetic.

        Without a receipt the money is explicitly an estimate: orchestrator
        phase costs are CUMULATIVE across a resume, so the estimate subtracts
        the floor an earlier pause turn already charged (AR-002). Non-agentic
        turns price their own accumulated usage and every dollar of it is new —
        there is no prior leg to have charged.
        """
        state = self.state
        breakdown = compute_cost_breakdown(
            usage=state.usage,
            binding=self.binding,
            image_count=self.image_attachment_count,
        )

        def _with_total(total: float) -> CostBreakdown:
            """Keep the token structure, show the run's own total (FL-34-b)."""
            return breakdown.model_copy(
                update={"subtotal_usd": total, "session_surcharge_usd": 0.0}
            )

        if state.receipt is not None:
            return (
                _with_total(state.receipt.cumulative_cost_usd),
                state.receipt.cumulative_cost_usd,
                state.receipt.newly_billable_cost_usd,
            )
        if not self.agentic_active:
            # FL-34-b: charge the subtotal alone (surcharge is disclosure).
            return breakdown, breakdown.subtotal_usd, breakdown.subtotal_usd
        if state.scopes:
            estimated = self.estimated_agentic_cost_usd()
            return (
                _with_total(estimated),
                estimated,
                max(0.0, estimated - self.already_billed_floor_usd()),
            )
        flat = breakdown.subtotal_usd
        return breakdown, flat, max(0.0, flat - self.already_billed_floor_usd())

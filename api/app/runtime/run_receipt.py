"""One owner for an agentic run's money and tokens (AC-02).

`CostLedger` is the request-local accumulator: it restores prior spend from a
checkpoint, observes provisional per-phase samples, settles exact per-phase
amounts, and answers three questions the rest of the turn used to answer for
itself — what the run has cost CUMULATIVELY, how much of that was ALREADY BILLED
on an earlier pause turn, and how much is NEWLY BILLABLE now. `RunReceipt` is the
immutable snapshot of those answers plus the per-phase breakdown, and it travels
to the handler on the existing `providers.protocol.RunCost.receipt` carrier.

This module must stay provider-independent: `providers.protocol.RunCost` imports
`RunReceipt`, so importing `app.providers.protocol` here would close a cycle.
Callers adapt at the seam instead — `UsageTotals.copy_from(event)` copies the
canonical token counts off any usage-shaped object.

Every decoder here is TOTAL: a persisted receipt is read out of a JSON column, so
nonsense (nulls, bools where numbers belong, non-finite or negative amounts,
unknown versions) resolves to `None` or a zero rather than raising inside a row
read.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields, is_dataclass, replace
from typing import Any, Literal

RunConfidence = Literal["exact", "estimate"]
# Which persistable boundary a receipt describes. `stop` is an explicitly
# estimated abrupt-stop snapshot and is never exact terminal authority.
ReceiptBoundary = Literal["final", "pause", "stop"]

CURRENT_RECEIPT_VERSION = 1
SUPPORTED_RECEIPT_VERSIONS: frozenset[int] = frozenset({1})

_TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cached_input_tokens",
)


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(word.capitalize() for word in rest)


def _count(value: object) -> int:
    """A token count: non-negative int. `True` is not one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    return max(0, int(value))


def _money(value: object) -> float:
    """A USD amount: finite, non-negative float. `True` is not one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    number = float(value)
    return number if math.isfinite(number) and number >= 0.0 else 0.0


def _text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) and value else default


def _to_wire(value: object) -> Any:
    """Recursive camelCase JSON form of this module's receipt dataclasses.

    One writer for all three shapes, so a field added to a dataclass cannot be
    silently dropped from what gets persisted by a hand-listed dict.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return {_camel(f.name): _to_wire(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, tuple):
        return [_to_wire(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class UsageTotals:
    """Provider-independent token counts, summable across phases."""

    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cached_input_tokens: int = 0

    @classmethod
    def copy_from(cls, source: object) -> UsageTotals:
        """Adapter seam: copy canonical counts off any usage-shaped object."""
        if isinstance(source, UsageTotals):
            return source
        if source is None:
            return cls()
        return cls(**{name: _count(getattr(source, name, 0)) for name in _TOKEN_FIELDS})

    def __add__(self, other: UsageTotals) -> UsageTotals:
        return UsageTotals(
            **{
                name: getattr(self, name) + getattr(other, name)
                for name in _TOKEN_FIELDS
            }
        )

    @property
    def is_empty(self) -> bool:
        return not any(getattr(self, name) for name in _TOKEN_FIELDS)

    @classmethod
    def from_wire(cls, raw: object) -> UsageTotals:
        if not isinstance(raw, dict):
            return cls()
        return cls(
            **{
                name: _count(raw.get(_camel(name), raw.get(name, 0)))
                for name in _TOKEN_FIELDS
            }
        )


@dataclass(frozen=True, slots=True)
class PhaseReceipt:
    """Exact (or provisional) accounting for one orchestration phase.

    `phase_id` is the subagent id the phase streamed under. `already_billed`
    marks a phase whose money a previous pause turn already charged, so it counts
    toward the run's cumulative total but not toward this continuation's newly
    billable amount.
    """

    phase_id: str
    role: str
    usage: UsageTotals = field(default_factory=UsageTotals)
    cost_usd: float = 0.0
    outcome: str = "succeeded"
    settled: bool = True
    already_billed: bool = False

    @classmethod
    def from_wire(cls, raw: object) -> PhaseReceipt | None:
        if not isinstance(raw, dict):
            return None
        phase_id = _text(raw.get("phaseId") or raw.get("phase_id"))
        if not phase_id:
            return None
        return cls(
            phase_id=phase_id,
            role=_text(raw.get("role"), "unknown"),
            usage=UsageTotals.from_wire(raw.get("usage")),
            cost_usd=_money(raw.get("costUsd", raw.get("cost_usd"))),
            outcome=_text(raw.get("outcome"), "succeeded"),
            settled=raw.get("settled", True) is not False,
            already_billed=raw.get("alreadyBilled", raw.get("already_billed")) is True,
        )


@dataclass(frozen=True, slots=True)
class RunReceipt:
    """Immutable accounting truth for one persistable run boundary.

    `cumulative_cost_usd` is the run's logical total — what the UI meter, the
    terminal attribution and the persisted attribution must all show.
    `newly_billable_cost_usd` alone reaches `Message.cost_usd` and the usage
    rollup. It is DERIVED, not stored, so `cumulative = already_billed +
    newly_billable` holds by construction rather than by convention.
    """

    cumulative_cost_usd: float = 0.0
    already_billed_cost_usd: float = 0.0
    cumulative_usage: UsageTotals = field(default_factory=UsageTotals)
    phases: tuple[PhaseReceipt, ...] = ()
    cap_usd: float = 0.0
    confidence: RunConfidence = "exact"
    boundary: ReceiptBoundary = "final"
    version: int = CURRENT_RECEIPT_VERSION

    @property
    def newly_billable_cost_usd(self) -> float:
        return max(0.0, self.cumulative_cost_usd - self.already_billed_cost_usd)

    @property
    def phase_cost_total_usd(self) -> float:
        """Sum of the per-phase breakdown. Trails `cumulative_cost_usd` only on a
        resume whose checkpoint recorded spend no surviving phase can account for."""
        return sum(phase.cost_usd for phase in self.phases)

    def to_wire(self) -> dict[str, Any]:
        wire = _to_wire(self)
        assert isinstance(wire, dict)
        # Derived, so `_to_wire` (which walks declared fields) cannot see it. It
        # is persisted anyway: a stored receipt should be readable on its own.
        wire["newlyBillableCostUsd"] = self.newly_billable_cost_usd
        return wire


def decode_run_receipt(raw: object) -> RunReceipt | None:
    """Read a persisted receipt. Never raises; unusable input reads as `None`.

    An unsupported version is refused rather than reinterpreted with this
    build's field meanings, and `None` means "no receipt" so the caller keeps its
    legacy seeds instead of crediting a resume with unverifiable spend.
    """
    if not isinstance(raw, dict):
        return None
    version = raw.get("version", CURRENT_RECEIPT_VERSION)
    if isinstance(version, bool) or version not in SUPPORTED_RECEIPT_VERSIONS:
        return None
    phases = tuple(
        phase
        for phase in (
            PhaseReceipt.from_wire(item) for item in (raw.get("phases") or ())
        )
        if phase is not None
    )
    cumulative = _money(raw.get("cumulativeCostUsd", raw.get("cumulative_cost_usd")))
    # Clamped: a stored already-billed amount above the run's own total would
    # otherwise read as a negative increment on the next boundary.
    already = min(
        cumulative,
        _money(raw.get("alreadyBilledCostUsd", raw.get("already_billed_cost_usd"))),
    )
    confidence = raw.get("confidence")
    boundary = raw.get("boundary")
    return RunReceipt(
        cumulative_cost_usd=cumulative,
        already_billed_cost_usd=already,
        cumulative_usage=UsageTotals.from_wire(raw.get("cumulativeUsage")),
        phases=phases,
        cap_usd=_money(raw.get("capUsd", raw.get("cap_usd"))),
        confidence=confidence if confidence in ("exact", "estimate") else "exact",
        boundary=boundary if boundary in ("final", "pause", "stop") else "final",
        version=int(version),
    )


class CostLedger:
    """Request-local owner of one run's cumulative / billed / billable money.

    Phases are keyed by `phase_id` and kept in first-observation order.
    `observe` records a provisional mid-flight sample; `settle` replaces it with
    the exact amount. The cumulative total can never fall below what a prior
    pause turn already billed, so a checkpoint that recorded spend the surviving
    phases cannot re-derive still holds its floor.
    """

    def __init__(
        self,
        *,
        already_billed_cost_usd: float = 0.0,
        already_billed_usage: UsageTotals | None = None,
    ) -> None:
        self._already_billed = _money(already_billed_cost_usd)
        self._already_billed_usage = already_billed_usage or UsageTotals()
        self._phases: dict[str, PhaseReceipt] = {}

    @classmethod
    def restore(cls, receipt: RunReceipt | None) -> CostLedger:
        """Resume entry point: a prior boundary receipt becomes this
        continuation's already-billed floor and its phase history."""
        if receipt is None:
            return cls()
        ledger = cls(
            already_billed_cost_usd=receipt.cumulative_cost_usd,
            already_billed_usage=receipt.cumulative_usage,
        )
        for phase in receipt.phases:
            ledger._phases[phase.phase_id] = replace(
                phase, settled=True, already_billed=True
            )
        return ledger

    # --- writes ---------------------------------------------------------------

    def observe(
        self,
        phase_id: str,
        *,
        role: str,
        usage: object = None,
        cost_usd: float = 0.0,
    ) -> None:
        """Record a provisional mid-flight sample. A settled phase is not
        downgraded — its exact amount already replaced the sample."""
        existing = self._phases.get(phase_id)
        if existing is not None and existing.settled:
            return
        self._phases[phase_id] = PhaseReceipt(
            phase_id=phase_id,
            role=role,
            usage=UsageTotals.copy_from(usage),
            cost_usd=_money(cost_usd),
            settled=False,
        )

    def settle(
        self,
        phase_id: str,
        *,
        role: str,
        usage: object = None,
        cost_usd: float = 0.0,
        outcome: str = "succeeded",
        already_billed: bool = False,
    ) -> PhaseReceipt:
        """Record the exact amount for a phase, replacing any provisional sample.
        Re-settling the same phase (a resumed worker) overwrites."""
        receipt = PhaseReceipt(
            phase_id=phase_id,
            role=role,
            usage=UsageTotals.copy_from(usage),
            cost_usd=_money(cost_usd),
            outcome=outcome,
            settled=True,
            already_billed=already_billed,
        )
        self._phases[phase_id] = receipt
        return receipt

    def hold_billed_floor(self, cost_usd: float) -> None:
        """Raise the already-billed floor from a legacy checkpoint amount that
        predates receipts. Never lowers it."""
        self._already_billed = max(self._already_billed, _money(cost_usd))

    # --- reads ----------------------------------------------------------------

    def phase(self, phase_id: str) -> PhaseReceipt | None:
        return self._phases.get(phase_id)

    def phases(self) -> tuple[PhaseReceipt, ...]:
        return tuple(self._phases.values())

    def cost_of(self, phase_id: str, default: float = 0.0) -> float:
        phase = self._phases.get(phase_id)
        return default if phase is None else phase.cost_usd

    def usage_of(self, phase_id: str) -> UsageTotals:
        phase = self._phases.get(phase_id)
        return UsageTotals() if phase is None else phase.usage

    @property
    def already_billed_cost_usd(self) -> float:
        return self._already_billed

    @property
    def settled_cost_usd(self) -> float:
        """Exactly settled spend only — what a mid-run display tick may show
        without quoting a provisional sibling sample as a fact."""
        return max(
            sum(p.cost_usd for p in self._phases.values() if p.settled),
            self._already_billed,
        )

    @property
    def cumulative_cost_usd(self) -> float:
        return max(
            sum(phase.cost_usd for phase in self._phases.values()),
            self._already_billed,
        )

    @property
    def cumulative_usage(self) -> UsageTotals:
        totals = UsageTotals()
        for phase in self._phases.values():
            totals = totals + phase.usage
        return totals if not totals.is_empty else self._already_billed_usage

    @property
    def newly_billable_cost_usd(self) -> float:
        return max(0.0, self.cumulative_cost_usd - self._already_billed)

    def receipt(
        self,
        *,
        cap_usd: float = 0.0,
        confidence: RunConfidence = "exact",
        boundary: ReceiptBoundary = "final",
    ) -> RunReceipt:
        """Snapshot the ledger as the boundary's immutable accounting truth."""
        return RunReceipt(
            cumulative_cost_usd=self.cumulative_cost_usd,
            already_billed_cost_usd=self._already_billed,
            cumulative_usage=self.cumulative_usage,
            phases=self.phases(),
            cap_usd=_money(cap_usd),
            confidence=confidence,
            boundary=boundary,
        )

"""Agentic HITL continuation state for worker tool pauses (BE-005).

When a deep-research worker pauses for tool approval, the orchestrator waits
for sibling workers to finish, then persists enough state so a later
``toolApproval`` resume continues **that** subagent — not a full re-plan.

Sibling policy (simpler correct design): **wait** for incomplete siblings to
finish before surfacing ``AwaitingApproval``. Completed worker results are kept;
the paused subagent is resumed in place. We do not cancel siblings.

**H-011 design choice:** aggregator / primary HITL continuation is *not*
implemented. ``ContinuationPhase`` is ``"worker"`` only. The aggregator always
runs with an empty registry tool allowlist so approval-gated tools cannot pause
there. Re-introduce ``aggregator`` / ``primary`` phases only with a real
checkpoint + resume path.

**H-012:** The continuation blob lives in ``Message.server_state`` (server-only), keyed
by tool-call id. Legacy rows may still embed ``_agenticContinuation`` on
``tool_call.input``; serializers strip that key (and claim/cost keys) before any private
or public API projection, and before ``execute_tool`` / schema validation.
"""

from __future__ import annotations

import dataclasses
import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import (
    AliasChoices,
    AliasGenerator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    field_serializer,
    field_validator,
)
from pydantic.alias_generators import to_camel

from app.agentic.aggregate import WorkerOutput
from app.agentic.clarify import (
    ClarificationRecord,
    parse_clarification_records,
    serialize_clarification_records,
)
from app.providers.protocol import UsageUpdate
from app.runtime.run_receipt import RunReceipt, decode_run_receipt
from app.schemas.common import SubagentOutcome
from app.search.protocol import SourceItem

# Reserved key on pending tool_call.input (legacy). Must not collide with any
# tool's advertised JSON Schema properties.
CONTINUATION_INPUT_KEY = "_agenticContinuation"

# Claim id stamped on tool_call parts during settle (not tool input).
APPROVAL_CLAIM_INPUT_KEY = "_approvalClaimId"

# Keys stripped from every outbound tool_call / tool_result projection (H-012).
# Includes plan-approval server fields (B4) so planner spend can ride on the
# pause tool input without leaking into private/public API projections.
RESERVED_CONTROL_KEYS: frozenset[str] = frozenset(
    {
        CONTINUATION_INPUT_KEY,
        APPROVAL_CLAIM_INPUT_KEY,
        "plannerCostUsd",
        "planner_cost_usd",
        "plannerUsage",
        "planner_usage",
        "actualCostUsd",
        "actual_cost_usd",
        "pausedWorkerCostUsd",
        "paused_worker_cost_usd",
        "pausedWorkerUsedFallback",
        "paused_worker_used_fallback",
        "priorRunCostUsd",
        "prior_run_cost_usd",
        "priorRunUsage",
        "prior_run_usage",
        "runReceipt",
        "run_receipt",
    }
)

# H-011: only worker checkpoints are real; aggregator/primary removed until
# a full resume path ships.
ContinuationPhase = Literal["worker"]

# server_state JSON shape: {"continuations": {toolCallId: <blob>}, ...ledger}
SERVER_STATE_CONTINUATIONS_KEY = "continuations"
# B4/B5: pause-turn run-cap ledger seeds (survive sanitize_message_parts_for_api).
SERVER_STATE_PLANNER_COST_KEY = "plannerCostUsd"
SERVER_STATE_PLANNER_USAGE_KEY = "plannerUsage"
SERVER_STATE_PRIOR_RUN_COST_KEY = "priorRunCostUsd"
SERVER_STATE_PRIOR_RUN_USAGE_KEY = "priorRunUsage"
# FL-28: orchestration mode of the paused run. Lives beside the ledger seeds
# rather than on the continuation blob because plan-approval / clarify / single
# pauses have no continuation at all, and a resume onto a different mode
# consumes the approval and discards the approved work.
SERVER_STATE_ORCHESTRATION_MODE_KEY = "orchestrationMode"
# AC-02: the pause boundary's `RunReceipt`. It sits beside the scalar seeds for
# the same reason the mode pin does (those pause shapes have no continuation blob
# at all) and SUPERSEDES them on resume: the seeds reconstruct one phase, the
# receipt is the exact total already billed.
SERVER_STATE_RUN_RECEIPT_KEY = "runReceipt"


@dataclass(frozen=True)
class CompletedWorkerState:
    """One finished sibling (or prior) worker snapshot for resume synthesis."""

    subagent_id: str
    sub_question: str
    answer: str
    usage: UsageUpdate
    cost_usd: float
    outcome: str = "succeeded"
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgenticContinuation:
    """Durable fan-out continuation for a mid-worker tool HITL pause."""

    phase: ContinuationPhase
    paused_subagent_id: str
    user_text: str
    plan: tuple[str, ...]
    completed_workers: tuple[CompletedWorkerState, ...]
    planner_usage: UsageUpdate
    planner_cost_usd: float
    budget_halted: bool = False
    failed_workers: int = 0
    actual_cost_usd: float = 0.0
    paused_worker_index: int | None = None
    paused_sub_question: str | None = None
    # Pre-tool worker text accumulated before the HITL pause (BE-005 / H-010).
    # Restored into the worker answer buffer for synthesis; NOT re-emitted as
    # AnswerDelta on resume (already delivered on the paused turn).
    partial_answer: str = ""
    # H-010: worker-local checkpoint fidelity.
    partial_reasoning: str = ""
    source_ids: tuple[str, ...] = ()
    # B12: merged global source catalog at pause time (remapped SourceItems) so
    # resume can re-emit aggregator Sources and continue allocating ids without
    # colliding with pre-pause globals.
    source_catalog: tuple[SourceItem, ...] = ()
    # Wire-shaped tool_call / tool_result dicts from before the pause.
    tool_transcript: tuple[dict[str, Any], ...] = ()
    # Cursor: number of answer chars already streamed to the client.
    emitted_answer_chars: int = 0
    # Structured clarify-before-plan answers (C-003).
    clarifications: tuple[ClarificationRecord, ...] = ()
    # H-002 / O-003: pin orchestration routing on resume.
    orchestration_mode: Literal["single", "deep_research"] | None = None
    tier_id: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    # Pre-pause usage for the paused worker (O-002 / H-009).
    paused_worker_usage: UsageUpdate | None = None
    paused_worker_cost_usd: float = 0.0
    # B6: pause was served on the fallback route — resume must pin + price there.
    paused_worker_used_fallback: bool = False
    version: int = 2


# --- Versioned continuation codec (AC-06) ------------------------------------
#
# One Pydantic codec reads every persisted checkpoint. It is TOTAL — nothing a JSON
# column can hand back raises; callers get a typed invalid result and the resume route
# refuses the turn before settling the approval — and CLOSED: only known versions, the
# one resumable phase, finite non-negative non-bool numbers, and known outcomes decode.
# Legacy tolerance lives only in the aliases and `to_state()`, so nothing here has a
# second, divergent reader.

CURRENT_CONTINUATION_VERSION = 2
SUPPORTED_CONTINUATION_VERSIONS: frozenset[int] = frozenset({1, 2})

# Every wire field reads camelCase first and snake_case second (older builds
# wrote snake), and always writes camelCase.
_WIRE_CONFIG = ConfigDict(
    populate_by_name=True,
    extra="ignore",
    alias_generator=AliasGenerator(
        validation_alias=lambda name: AliasChoices(to_camel(name), name),
        serialization_alias=to_camel,
    ),
)


def _none_to(default: object) -> BeforeValidator:
    """Older writers stored explicit nulls where the field now has a plain default."""
    return BeforeValidator(lambda value: default if value is None else value)


def _string_ids(value: object) -> object:
    """Source ids were written as ints (or null) by older builds; accept both."""
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value if item is not None)
    return () if value is None else value


def _known_mode(value: object) -> object:
    """A blob written before mode pinning — or naming a mode this build does not
    run — resolves through the caller's own mode policy instead."""
    return value if value in ("single", "deep_research") else None


def _reject_bool(value: object) -> object:
    """`int(True)` is 1 and `float(True)` is 1.0, so lax numeric coercion would read
    a checkpoint amount of ``true`` as one token or one cent. It is corruption."""
    if isinstance(value, bool):
        raise ValueError("expected a number, not a bool")
    return value


def _wire_version(value: object) -> object:
    """Pre-versioning blobs (and blobs written with an explicit null) are v1."""
    return 1 if value is None else _reject_bool(value)


# Closed numeric domains: counts and money are finite, never negative, and never a
# bool. Legacy null tolerance is expressed here, once, as part of the field type.
_NotBool = BeforeValidator(_reject_bool)
_Count = Annotated[int, Field(ge=0), _NotBool, _none_to(0)]
_Money = Annotated[float, Field(ge=0.0, allow_inf_nan=False), _NotBool, _none_to(0.0)]
_Index = Annotated[int, Field(ge=0), _NotBool] | None
_NullStr = Annotated[str, _none_to("")]
_NullBool = Annotated[bool, _none_to(False)]
_StrIds = Annotated[tuple[str, ...], BeforeValidator(_string_ids)]
_Version = Annotated[Literal[1, 2], BeforeValidator(_wire_version)]
_PinnedMode = Annotated[Literal["single", "deep_research"] | None, BeforeValidator(_known_mode)]


class _UsageWire(BaseModel):
    """Token counts as they appear in server_state."""

    model_config = _WIRE_CONFIG

    input_tokens: _Count = 0
    output_tokens: _Count = 0
    reasoning_tokens: _Count = 0
    cached_input_tokens: _Count = 0

    def to_usage(self) -> UsageUpdate:
        return UsageUpdate(**dict(self))


class _CompletedWorkerWire(BaseModel):
    """One finished sibling snapshot. A corrupt entry invalidates the whole blob:
    dropping it would silently delete that worker's answer and its cost from the
    resumed run, which is worse than refusing the resume."""

    model_config = _WIRE_CONFIG

    subagent_id: str = Field(min_length=1)
    sub_question: _NullStr
    answer: _NullStr = ""
    usage: _UsageWire = Field(default_factory=_UsageWire)
    cost_usd: _Money = 0.0
    outcome: SubagentOutcome = "succeeded"
    source_ids: _StrIds = ()

    def to_state(self) -> CompletedWorkerState:
        return CompletedWorkerState(**{**dict(self), "usage": self.usage.to_usage()})


class _ContinuationWire(BaseModel):
    """The one persisted shape of `AgenticContinuation`.

    `version` and `phase` are closed literals, so an unsupported checkpoint fails
    validation instead of being read with this build's field meanings."""

    model_config = _WIRE_CONFIG

    version: _Version = 1
    phase: ContinuationPhase
    paused_subagent_id: str = Field(min_length=1)
    user_text: _NullStr
    plan: tuple[str, ...]
    completed_workers: tuple[_CompletedWorkerWire, ...] = ()
    planner_usage: _UsageWire = Field(default_factory=_UsageWire)
    planner_cost_usd: _Money = 0.0
    budget_halted: _NullBool = False
    failed_workers: _Count = 0
    actual_cost_usd: _Money = 0.0
    paused_worker_index: _Index = None
    paused_sub_question: str | None = None
    partial_answer: _NullStr = ""
    partial_reasoning: _NullStr = ""
    source_ids: _StrIds = ()
    source_catalog: tuple[SourceItem, ...] = ()
    tool_transcript: tuple[dict[str, Any], ...] = ()
    emitted_answer_chars: _Count = 0
    clarifications: tuple[Any, ...] = ()
    orchestration_mode: _PinnedMode = None
    tier_id: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    paused_worker_usage: _UsageWire | None = None
    paused_worker_cost_usd: _Money = 0.0
    paused_worker_used_fallback: _NullBool = False

    @field_validator("plan", "completed_workers", "clarifications", mode="before")
    @classmethod
    def _null_sequence(cls, value: object) -> object:
        return () if value is None else value

    @field_serializer("source_catalog")
    def _dump_catalog(self, value: tuple[SourceItem, ...]) -> list[dict[str, Any]]:
        return [item.model_dump(exclude_none=True) for item in value]

    @classmethod
    def from_state(cls, state: AgenticContinuation) -> _ContinuationWire:
        """Write side. `asdict` gives snake_case, which the aliases accept."""
        payload: dict[str, Any] = dataclasses.asdict(state)
        # Clarification records keep their own camelCase writer so the stored
        # shape matches what `parse_clarification_records` prefers to read.
        payload["clarifications"] = serialize_clarification_records(state.clarifications)
        return cls.model_validate(payload)

    def to_state(self) -> AgenticContinuation:
        """Read side. Nested wire models become their domain types."""
        emitted = self.emitted_answer_chars
        if emitted <= 0 and self.partial_answer:
            # Legacy blobs had no cursor: the whole draft was already streamed.
            emitted = len(self.partial_answer)
        paused = self.paused_worker_usage
        return AgenticContinuation(
            **{
                **dict(self),
                "completed_workers": tuple(w.to_state() for w in self.completed_workers),
                "planner_usage": self.planner_usage.to_usage(),
                "paused_worker_usage": paused.to_usage() if paused is not None else None,
                "tool_transcript": tuple(dict(part) for part in self.tool_transcript),
                "clarifications": tuple(parse_clarification_records(list(self.clarifications))),
                "emitted_answer_chars": emitted,
            }
        )


@dataclass(frozen=True)
class ContinuationDecode:
    """Total decode result: absent (nothing stored), valid, or invalid.

    An invalid checkpoint must never read as "no checkpoint": that would let a resume
    bypass the continuation contract and settle the approval as a plain tool resume."""

    present: bool = False
    state: AgenticContinuation | None = None
    error: str | None = None

    @property
    def invalid(self) -> bool:
        return self.present and self.state is None


_ABSENT = ContinuationDecode()


def decode_continuation(raw: object, *, stored: bool = False) -> ContinuationDecode:
    """Decode a persisted continuation blob. Never raises.

    `stored=True` means the key really was there, so a null value is a corrupt
    checkpoint rather than an absent one. Collapsing "present but unreadable" into
    "absent" walks a resume straight past the invalid-checkpoint gate.
    """
    if raw is None and not stored:
        return _ABSENT
    if not isinstance(raw, dict):
        return ContinuationDecode(present=True, error="not_an_object")
    try:
        state = _ContinuationWire.model_validate(raw).to_state()
    except ValidationError as exc:
        return ContinuationDecode(present=True, error=_first_error(exc))
    except Exception:  # pragma: no cover - defensive totality guard
        return ContinuationDecode(present=True, error="undecodable")
    return ContinuationDecode(present=True, state=state)


def _first_error(exc: ValidationError) -> str:
    """Field path and failed rule of the first error — diagnostics only."""
    for detail in exc.errors():
        return f"{'.'.join(str(p) for p in detail['loc']) or 'root'}: {detail['type']}"
    return "invalid"  # pragma: no cover - a ValidationError always has one


def usage_to_wire(usage: UsageUpdate) -> dict[str, int]:
    """CamelCase usage dict for server_state / reserved tool-input fields."""
    return {to_camel(name): getattr(usage, name) for name in _UsageWire.model_fields}


def usage_from_wire(raw: object) -> UsageUpdate:
    """Parse a camelCase/snake_case usage dict. Never raises — a malformed, negative or
    bool count reads as empty usage rather than escaping a persisted-row read."""
    if not isinstance(raw, dict):
        return UsageUpdate()
    try:
        return _UsageWire.model_validate(raw).to_usage()
    except ValidationError:
        return UsageUpdate()


def _seed_cost(raw: object) -> float:
    """Read a persisted ledger amount. Never raises; nonsense reads as 0.0, so a resume
    cannot credit itself with negative, infinite or bool prior spend."""
    if raw is None or isinstance(raw, bool):
        return 0.0
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(value) or value < 0.0:
        return 0.0
    return value


def serialize_continuation(state: AgenticContinuation) -> dict[str, Any]:
    """CamelCase JSON-ready dict for server_state (not client tool input)."""
    return _ContinuationWire.from_state(state).model_dump(by_alias=True, mode="json")


def parse_continuation(raw: object) -> AgenticContinuation | None:
    """Parse a continuation blob; None when missing or malformed.

    Thin wrapper over `decode_continuation` for call sites that cannot act on the
    invalid-versus-absent distinction. Prefer `resolve_continuation_decode` anywhere a
    corrupt checkpoint must be refused rather than ignored. Legacy blobs with ``phase``
    in {aggregator, primary} are rejected — those phases were never resumable (H-011).
    """
    return decode_continuation(raw).state


def _cleaned_tool_input(tool_input: object) -> dict[str, Any]:
    """Executor-facing shallow copy of a tool input, reserved control keys removed."""
    if not isinstance(tool_input, dict):
        return {}
    return {k: v for k, v in tool_input.items() if k not in RESERVED_CONTROL_KEYS}


def _legacy_decode(tool_input: object) -> ContinuationDecode:
    """Decode the legacy checkpoint embedded on `tool_call.input` (H-012)."""
    if not isinstance(tool_input, dict) or CONTINUATION_INPUT_KEY not in tool_input:
        return _ABSENT
    return decode_continuation(tool_input[CONTINUATION_INPUT_KEY], stored=True)


def extract_continuation_from_tool_input(
    tool_input: object,
) -> tuple[dict[str, Any], AgenticContinuation | None]:
    """Split tool input into (executor_input, continuation) — legacy embedding."""
    return _cleaned_tool_input(tool_input), _legacy_decode(tool_input).state


def attach_continuation_to_tool_input(
    tool_input: dict[str, Any] | None,
    state: AgenticContinuation,
) -> dict[str, Any]:
    """Legacy helper: attach continuation onto tool input.

    Prefer ``put_continuation_in_server_state`` for new writes (H-012). Kept for
    tests that construct wire-shaped parts directly.
    """
    base = dict(tool_input or {})
    base[CONTINUATION_INPUT_KEY] = serialize_continuation(state)
    return base


def put_continuation_in_server_state(
    server_state: dict[str, Any] | None,
    tool_call_id: str,
    state: AgenticContinuation | dict[str, Any],
) -> dict[str, Any]:
    """Return a new server_state with the continuation stored under tool_call_id."""
    out = dict(server_state or {})
    conts = dict(out.get(SERVER_STATE_CONTINUATIONS_KEY) or {})
    conts[tool_call_id] = (
        serialize_continuation(state) if isinstance(state, AgenticContinuation) else dict(state)
    )
    out[SERVER_STATE_CONTINUATIONS_KEY] = conts
    return out


def decode_continuation_from_server_state(
    server_state: object,
    tool_call_id: str,
) -> ContinuationDecode:
    """Total decode of the checkpoint stored under `tool_call_id` (H-012).

    Absent means the row genuinely holds no checkpoint for this call. A malformed
    `continuations` container, or a key stored with a null, is corruption instead —
    the resume must refuse it, not proceed as an ordinary tool approval.
    """
    if server_state is None:
        return _ABSENT
    if not isinstance(server_state, dict):
        return ContinuationDecode(present=True, error="server_state: not_an_object")
    conts = server_state.get(SERVER_STATE_CONTINUATIONS_KEY)
    if conts is None:
        return _ABSENT
    if not isinstance(conts, dict):
        return ContinuationDecode(present=True, error="continuations: not_an_object")
    if tool_call_id not in conts:
        return _ABSENT
    return decode_continuation(conts[tool_call_id], stored=True)


def get_continuation_from_server_state(
    server_state: object,
    tool_call_id: str,
) -> AgenticContinuation | None:
    """Load a continuation from Message.server_state; None when absent or invalid."""
    return decode_continuation_from_server_state(server_state, tool_call_id).state


@dataclass(frozen=True)
class RunLedgerSeeds:
    """B4/B5 pause-turn ledger seeds stored beside continuations in server_state."""

    planner_cost_usd: float = 0.0
    planner_usage: UsageUpdate | None = None
    prior_run_cost_usd: float = 0.0
    prior_run_usage: UsageUpdate | None = None
    # FL-28: mode the paused run was orchestrated in, for every pause shape.
    orchestration_mode: Literal["single", "deep_research"] | None = None
    # AC-02: exact accounting for the pause boundary. Preferred over the scalar
    # seeds above; `None` for legacy rows written before receipts existed.
    run_receipt: RunReceipt | None = None


def _usage_seed_wire(
    usage: UsageUpdate | dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Wire form of a ledger usage seed; None when there is nothing to store."""
    if isinstance(usage, UsageUpdate):
        wire = usage_to_wire(usage)
        return wire if any(wire.values()) else None
    return dict(usage) if isinstance(usage, dict) else None


def put_run_ledger_in_server_state(
    server_state: dict[str, Any] | None,
    *,
    planner_cost_usd: float | None = None,
    planner_usage: UsageUpdate | dict[str, Any] | None = None,
    prior_run_cost_usd: float | None = None,
    prior_run_usage: UsageUpdate | dict[str, Any] | None = None,
    orchestration_mode: str | None = None,
    run_receipt: RunReceipt | None = None,
) -> dict[str, Any]:
    """Merge B4/B5 run-cap ledger seeds into Message.server_state (H-012).

    These keys must NOT live only on tool_call.input — sanitize-on-persist strips
    ``RESERVED_CONTROL_KEYS`` before the durable row is written.
    """
    out = dict(server_state or {})
    if orchestration_mode in ("single", "deep_research"):
        out[SERVER_STATE_ORCHESTRATION_MODE_KEY] = orchestration_mode
    if run_receipt is not None:
        out[SERVER_STATE_RUN_RECEIPT_KEY] = run_receipt.to_wire()
    for key, cost in (
        (SERVER_STATE_PLANNER_COST_KEY, planner_cost_usd),
        (SERVER_STATE_PRIOR_RUN_COST_KEY, prior_run_cost_usd),
    ):
        if cost is not None and float(cost) > 0.0:
            out[key] = float(cost)
    for key, usage in (
        (SERVER_STATE_PLANNER_USAGE_KEY, planner_usage),
        (SERVER_STATE_PRIOR_RUN_USAGE_KEY, prior_run_usage),
    ):
        wire = _usage_seed_wire(usage)
        if wire is not None:
            out[key] = wire
    return out


def _seed(state: dict[str, Any], camel: str, snake: str) -> object:
    """Read a ledger seed, preferring the camelCase key older builds wrote as snake."""
    value = state.get(camel)
    return state.get(snake) if value is None else value


def _seed_usage(raw: object) -> UsageUpdate | None:
    """Ledger usage seeds are absent (not empty) when nothing was stored."""
    return usage_from_wire(raw) if isinstance(raw, dict) else None


def get_run_ledger_from_server_state(server_state: object) -> RunLedgerSeeds:
    """Parse B4/B5 ledger seeds from Message.server_state. Never raises.

    Legacy snake_case keys are read as fallbacks. Costs go through `_seed_cost`,
    so a corrupt or negative seed reads as 0.0 instead of raising out of a
    persisted-row read (or crediting the resume with unverifiable spend).
    """
    if not isinstance(server_state, dict):
        return RunLedgerSeeds()
    mode = _seed(server_state, SERVER_STATE_ORCHESTRATION_MODE_KEY, "orchestration_mode")
    return RunLedgerSeeds(
        planner_cost_usd=_seed_cost(
            _seed(server_state, SERVER_STATE_PLANNER_COST_KEY, "planner_cost_usd")
        ),
        planner_usage=_seed_usage(
            _seed(server_state, SERVER_STATE_PLANNER_USAGE_KEY, "planner_usage")
        ),
        prior_run_cost_usd=_seed_cost(
            _seed(server_state, SERVER_STATE_PRIOR_RUN_COST_KEY, "prior_run_cost_usd")
        ),
        prior_run_usage=_seed_usage(
            _seed(server_state, SERVER_STATE_PRIOR_RUN_USAGE_KEY, "prior_run_usage")
        ),
        orchestration_mode=mode if mode in ("single", "deep_research") else None,
        run_receipt=decode_run_receipt(
            _seed(server_state, SERVER_STATE_RUN_RECEIPT_KEY, "run_receipt")
        ),
    )


def resolve_continuation_decode(
    *,
    server_state: object = None,
    tool_input: object = None,
    tool_call_id: str | None = None,
) -> tuple[dict[str, Any], ContinuationDecode]:
    """Resolve the checkpoint for a pending call, returning the total decode.

    server_state wins whenever it holds anything for this call — including an
    undecodable blob. Falling back to the legacy tool-input copy on a corrupt
    server checkpoint would resume from a stale, unvalidated snapshot.
    """
    if tool_call_id:
        stored = decode_continuation_from_server_state(server_state, tool_call_id)
        if stored.present:
            return _cleaned_tool_input(tool_input), stored
    return _cleaned_tool_input(tool_input), _legacy_decode(tool_input)


def resolve_continuation(
    *,
    server_state: object = None,
    tool_input: object = None,
    tool_call_id: str | None = None,
) -> tuple[dict[str, Any], AgenticContinuation | None]:
    """Prefer server_state, fall back to legacy tool-input embedding."""
    cleaned, decoded = resolve_continuation_decode(
        server_state=server_state, tool_input=tool_input, tool_call_id=tool_call_id
    )
    return cleaned, decoded.state


def strip_reserved_keys(value: object) -> object:
    """Recursively drop reserved control / internal cost keys (H-012)."""
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for key, child in value.items():
            if key in RESERVED_CONTROL_KEYS:
                continue
            out[key] = strip_reserved_keys(child)
        return out
    if isinstance(value, list):
        return [strip_reserved_keys(item) for item in value]
    return value


def sanitize_message_parts_for_api(
    parts: list[Any] | None,
) -> list[dict[str, Any]]:
    """Strip reserved keys from tool parts for private/public API responses."""
    if not parts:
        return []
    sanitized: list[dict[str, Any]] = []
    for part in parts:
        raw = deepcopy(part) if isinstance(part, dict) else part.model_dump(by_alias=True)
        if raw.get("type") in {"tool_call", "tool_result"}:
            # Recursive, so the claim id beside `input` goes with the nested keys.
            stripped = strip_reserved_keys(raw)
            assert isinstance(stripped, dict)
            raw = stripped
        sanitized.append(raw)
    return sanitized


def completed_to_worker_outputs(
    completed: tuple[CompletedWorkerState, ...] | list[CompletedWorkerState],
) -> list[WorkerOutput]:
    """Map completed snapshots into aggregator ``WorkerOutput`` rows."""
    return [
        WorkerOutput(
            subagent_id=w.subagent_id,
            sub_question=w.sub_question,
            answer=w.answer,
            source_ids=w.source_ids,
        )
        for w in completed
    ]

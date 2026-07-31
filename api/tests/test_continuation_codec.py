"""AC-06 closure: one total, versioned codec reads every persisted checkpoint.

The old reader was hand-written dictionary walking. It was not total — a
persisted `plannerCostUsd` of `"free"` reached `float(...)` and raised
`ValueError` straight out of the resume route (a 500 on a durable row) — and it
was not closed: `version=99` was read with this build's field meanings, `-inf`
and negative money seeded the run ledger, and any string at all was accepted as
a subagent outcome.

These tests pin the replacement:

- **Total.** A field-by-field hostile-value matrix over a valid checkpoint never
  raises; every rejection comes back as a typed `ContinuationDecode`.
- **Closed.** Unsupported versions and phases, wrong types, non-finite and
  negative numbers, booleans in numeric slots, and unknown outcomes all decode as
  invalid.
- **Present is never absent.** A malformed `continuations` container, a checkpoint
  key stored with a null, and an unreadable `server_state` all decode as invalid —
  never as "this row has no checkpoint" — while rows that genuinely carry none stay
  absent.
- **Round-tripping.** Every supported version survives
  serialize → decode → serialize, and legacy (v1) blobs read through the same
  single adapter.
- **Route.** A corrupt checkpoint returns a typed non-500 response and does not
  settle the approval, so the pause stays recoverable.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agentic.clarify import ClarificationRecord
from app.agentic.continuation import (
    CONTINUATION_INPUT_KEY,
    CURRENT_CONTINUATION_VERSION,
    SERVER_STATE_CONTINUATIONS_KEY,
    SUPPORTED_CONTINUATION_VERSIONS,
    AgenticContinuation,
    CompletedWorkerState,
    ContinuationDecode,
    decode_continuation,
    decode_continuation_from_server_state,
    get_run_ledger_from_server_state,
    parse_continuation,
    resolve_continuation_decode,
    serialize_continuation,
    usage_from_wire,
    usage_to_wire,
)
from app.config import get_settings
from app.db.models import Conversation, Message, User
from app.db.repositories import billing as billing_repo
from app.db.session import get_db
from app.providers.protocol import UsageUpdate
from app.routes import conversations as conversations_route
from app.search.protocol import SourceItem

# --- Fixture data -------------------------------------------------------------


def _full_state() -> AgenticContinuation:
    """A checkpoint with every optional field populated, for round-trip fidelity."""
    return AgenticContinuation(
        phase="worker",
        paused_subagent_id="worker-0",
        user_text="causes of inflation",
        plan=("causes of inflation", "effects on housing"),
        completed_workers=(
            CompletedWorkerState(
                subagent_id="worker-1",
                sub_question="effects on housing",
                answer="Housing costs rose.",
                usage=UsageUpdate(
                    input_tokens=11,
                    output_tokens=22,
                    reasoning_tokens=3,
                    cached_input_tokens=4,
                ),
                cost_usd=0.0125,
                outcome="succeeded",
                source_ids=("1", "2"),
            ),
        ),
        planner_usage=UsageUpdate(input_tokens=7, output_tokens=8),
        planner_cost_usd=0.002,
        budget_halted=True,
        failed_workers=1,
        actual_cost_usd=0.031,
        paused_worker_index=0,
        paused_sub_question="causes of inflation",
        partial_answer="drafting calendar pause",
        partial_reasoning="thinking about rates",
        source_ids=("3",),
        source_catalog=(
            SourceItem(id=1, title="CPI", url="https://example.com/cpi", domain="example.com"),
            SourceItem(id=2, title="Rents", url="https://example.com/rents"),
        ),
        tool_transcript=(
            {"type": "tool_call", "id": "worker-0::c1", "name": "web_search"},
            {"type": "tool_result", "id": "worker-0::c1", "output": {"ok": True}},
        ),
        emitted_answer_chars=23,
        clarifications=(
            ClarificationRecord(question_id="q0", question="Which region?", answer="US"),
        ),
        orchestration_mode="deep_research",
        tier_id="smart",
        provider_id="deepseek",
        model_id="deepseek-chat",
        paused_worker_usage=UsageUpdate(input_tokens=5, output_tokens=6),
        paused_worker_cost_usd=0.004,
        paused_worker_used_fallback=True,
        version=CURRENT_CONTINUATION_VERSION,
    )


def _valid_blob() -> dict[str, Any]:
    return serialize_continuation(_full_state())


# --- Totality -----------------------------------------------------------------

# Values a JSON column can genuinely hand back for a field that once held
# something else: nulls from an older writer, a wrong container, a string where a
# number belongs, and the numbers JSON permits but money must never be.
_HOSTILE_VALUES: tuple[Any, ...] = (
    None,
    True,
    -1,
    -1.5,
    0,
    "",
    "free",
    "999",
    float("inf"),
    float("-inf"),
    float("nan"),
    [],
    ["nope"],
    [None],
    [{"junk": 1}],
    {},
    {"junk": 1},
    1e309,
)


def test_decode_never_raises_on_any_single_field_corruption() -> None:
    """Total: every field x every hostile value decodes, or nothing at all does."""
    blob = _valid_blob()
    checked = 0
    for key in blob:
        for value in _HOSTILE_VALUES:
            corrupted = {**blob, key: value}
            decoded = decode_continuation(corrupted)
            assert isinstance(decoded, ContinuationDecode)
            assert decoded.present
            # Either it decoded, or it is invalid with a diagnostic — never both,
            # never an exception.
            assert (decoded.state is None) is decoded.invalid
            if decoded.invalid:
                assert decoded.error
            checked += 1
        # Dropping a field must not raise either.
        assert decode_continuation({k: v for k, v in blob.items() if k != key}).present
    assert checked == len(blob) * len(_HOSTILE_VALUES)
    assert checked > 400, "the matrix should cover the whole wire shape"


def test_decode_never_raises_on_corrupt_nested_worker_fields() -> None:
    """The nested sibling snapshots go through the same total decode."""
    blob = _valid_blob()
    worker = blob["completedWorkers"][0]
    for key in worker:
        for value in _HOSTILE_VALUES:
            corrupted = {**blob, "completedWorkers": [{**worker, key: value}]}
            decoded = decode_continuation(corrupted)
            assert decoded.present
            assert (decoded.state is None) is decoded.invalid


def test_decode_never_raises_on_wholesale_garbage() -> None:
    """Non-object rows, and objects whose every value is the wrong shape."""
    assert decode_continuation(None) == ContinuationDecode()
    for raw in ("", "null", 0, 1.5, True, [], [1, 2], (), object()):
        decoded = decode_continuation(raw)
        assert decoded.invalid
        assert decoded.error == "not_an_object"
    assert decode_continuation({}).invalid
    assert decode_continuation({k: None for k in _valid_blob()}).invalid


def test_decode_survives_a_json_round_trip_of_the_corrupt_row() -> None:
    """The blob really comes back from a JSON column, `Infinity` included."""
    blob = {**_valid_blob(), "actualCostUsd": float("-inf"), "version": 99}
    revived = json.loads(json.dumps(blob))
    assert math.isinf(revived["actualCostUsd"])
    assert decode_continuation(revived).invalid


# --- Closed domains -----------------------------------------------------------


@pytest.mark.parametrize("version", [0, 3, 99, -1, "2", 2.5, True, None])
def test_unsupported_versions_are_rejected(version: object) -> None:
    """A checkpoint this build does not know must not be read with its meanings.

    `None` is the one exception: pre-versioning blobs predate the field and are
    v1 by definition.
    """
    decoded = decode_continuation({**_valid_blob(), "version": version})
    if version is None:
        assert decoded.state is not None
        assert decoded.state.version == 1
    else:
        assert decoded.invalid


@pytest.mark.parametrize("version", sorted(SUPPORTED_CONTINUATION_VERSIONS))
def test_supported_versions_decode(version: int) -> None:
    decoded = decode_continuation({**_valid_blob(), "version": version})
    assert decoded.state is not None
    assert decoded.state.version == version


@pytest.mark.parametrize("phase", ["aggregator", "primary", "planner", "", None, 1])
def test_unsupported_phases_are_rejected(phase: object) -> None:
    """H-011: `worker` is the only phase with a real resume path."""
    assert decode_continuation({**_valid_blob(), "phase": phase}).invalid


@pytest.mark.parametrize(
    "field",
    [
        "plannerCostUsd",
        "actualCostUsd",
        "pausedWorkerCostUsd",
    ],
)
@pytest.mark.parametrize("amount", [-0.01, -1e-9, float("inf"), float("-inf"), float("nan")])
def test_non_finite_and_negative_money_is_rejected(field: str, amount: float) -> None:
    """A resume must never credit itself with impossible prior spend."""
    assert decode_continuation({**_valid_blob(), field: amount}).invalid


@pytest.mark.parametrize("field", ["failedWorkers", "emittedAnswerChars", "pausedWorkerIndex"])
@pytest.mark.parametrize("count", [-1, -100, 1.5, "many", [3]])
def test_negative_and_non_integral_counts_are_rejected(field: str, count: object) -> None:
    assert decode_continuation({**_valid_blob(), field: count}).invalid


@pytest.mark.parametrize(
    ("wire_field", "attribute", "expected"),
    [
        ("failedWorkers", "failed_workers", 3),
        ("emittedAnswerChars", "emitted_answer_chars", 3),
        ("plannerCostUsd", "planner_cost_usd", 3.0),
    ],
)
def test_numerals_written_as_strings_still_coerce(
    wire_field: str, attribute: str, expected: float
) -> None:
    """The old reader's `int(...)` / `float(...)` accepted these, so the codec does."""
    decoded = decode_continuation({**_valid_blob(), wire_field: "3"})
    assert decoded.state is not None
    assert getattr(decoded.state, attribute) == expected


@pytest.mark.parametrize("amount", [-0.01, float("inf"), float("nan")])
def test_worker_money_is_closed_too(amount: float) -> None:
    blob = _valid_blob()
    worker = {**blob["completedWorkers"][0], "costUsd": amount}
    assert decode_continuation({**blob, "completedWorkers": [worker]}).invalid


@pytest.mark.parametrize("outcome", ["exploded", "SUCCEEDED", "", None, 1, "succeeded "])
def test_unknown_worker_outcomes_are_rejected(outcome: object) -> None:
    """`outcome` drives FE badges and attribution — not a free-text field."""
    blob = _valid_blob()
    worker = {**blob["completedWorkers"][0], "outcome": outcome}
    assert decode_continuation({**blob, "completedWorkers": [worker]}).invalid


@pytest.mark.parametrize(
    "outcome", ["succeeded", "failed", "cancelled", "budget_cancelled", "stopped"]
)
def test_known_worker_outcomes_decode(outcome: str) -> None:
    blob = _valid_blob()
    worker = {**blob["completedWorkers"][0], "outcome": outcome}
    decoded = decode_continuation({**blob, "completedWorkers": [worker]})
    assert decoded.state is not None
    assert decoded.state.completed_workers[0].outcome == outcome


# --- Booleans are not numbers -------------------------------------------------
#
# `int(True)` is 1 and `float(True)` is 1.0, so lax Pydantic coercion read a stored
# `actualCostUsd: true` as one cent and `emittedAnswerChars: true` as a one-character
# cursor. A JSON bool in a numeric slot is corruption from a disagreeing writer, and
# the accepted finding requires type rejection, not silent reinterpretation.

_NUMERIC_WIRE_FIELDS: tuple[str, ...] = (
    "version",
    "plannerCostUsd",
    "actualCostUsd",
    "pausedWorkerCostUsd",
    "failedWorkers",
    "emittedAnswerChars",
    "pausedWorkerIndex",
)


@pytest.mark.parametrize("field", _NUMERIC_WIRE_FIELDS)
@pytest.mark.parametrize("value", [True, False])
def test_booleans_are_rejected_as_numeric_checkpoint_fields(field: str, value: bool) -> None:
    assert decode_continuation({**_valid_blob(), field: value}).invalid


@pytest.mark.parametrize("container", ["plannerUsage", "pausedWorkerUsage"])
@pytest.mark.parametrize(
    "token_field", ["inputTokens", "outputTokens", "reasoningTokens", "cachedInputTokens"]
)
def test_booleans_are_rejected_inside_nested_usage(container: str, token_field: str) -> None:
    """A bool token count used to decode as one token deep inside the blob."""
    blob = _valid_blob()
    corrupted = {**blob, container: {**blob[container], token_field: True}}
    assert decode_continuation(corrupted).invalid


@pytest.mark.parametrize("field", ["costUsd", "usage"])
def test_booleans_are_rejected_inside_a_completed_worker(field: str) -> None:
    blob = _valid_blob()
    worker = dict(blob["completedWorkers"][0])
    worker[field] = (
        True if field == "costUsd" else {**worker["usage"], "inputTokens": True}
    )
    assert decode_continuation({**blob, "completedWorkers": [worker]}).invalid


def test_a_bool_never_becomes_a_token_or_a_cent() -> None:
    """Every reader of a persisted amount refuses a bool, not just the wire model."""
    for field in ("plannerCostUsd", "actualCostUsd", "failedWorkers", "emittedAnswerChars"):
        assert decode_continuation({**_valid_blob(), field: True}).state is None
    assert usage_from_wire({"inputTokens": True, "outputTokens": 2}) == UsageUpdate()
    seeds = get_run_ledger_from_server_state(
        {"plannerCostUsd": True, "plannerUsage": {"inputTokens": True}}
    )
    assert seeds.planner_cost_usd == 0.0
    assert seeds.planner_usage == UsageUpdate()


def test_real_zeros_and_ints_still_decode_beside_the_bool_rejection() -> None:
    """Closing bools must not close JSON's habit of writing 0.0 as `0`."""
    decoded = decode_continuation(
        {**_valid_blob(), "actualCostUsd": 0, "failedWorkers": 0, "pausedWorkerIndex": 0}
    )
    assert decoded.state is not None
    assert decoded.state.actual_cost_usd == 0.0
    assert decoded.state.paused_worker_index == 0


def test_a_corrupt_sibling_invalidates_the_blob_rather_than_vanishing() -> None:
    """Dropping the entry would delete that worker's answer AND its cost."""
    blob = _valid_blob()
    good = blob["completedWorkers"][0]
    decoded = decode_continuation(
        {**blob, "completedWorkers": [good, {"subagentId": "worker-2", "costUsd": -5.0}]}
    )
    assert decoded.invalid
    assert "completedWorkers" in (decoded.error or "")


def test_a_corrupt_source_catalog_entry_invalidates_the_blob() -> None:
    """A partial catalog would let resume re-allocate colliding source ids."""
    blob = _valid_blob()
    assert decode_continuation({**blob, "sourceCatalog": [{"id": 1}]}).invalid


def test_unknown_extra_keys_are_ignored_not_rejected() -> None:
    """Forward compatibility: a newer writer's extra key must not break reads."""
    decoded = decode_continuation({**_valid_blob(), "somethingNewer": {"a": 1}})
    assert decoded.state == _full_state()


# --- Round trips and legacy reads --------------------------------------------


def test_current_version_round_trips_with_full_fidelity() -> None:
    state = _full_state()
    decoded = decode_continuation(serialize_continuation(state))
    assert decoded.state == state


@pytest.mark.parametrize("version", sorted(SUPPORTED_CONTINUATION_VERSIONS))
def test_every_supported_version_round_trips_through_json(version: int) -> None:
    """serialize -> JSON -> decode -> serialize is stable for each version."""
    blob = {**_valid_blob(), "version": version}
    first = decode_continuation(json.loads(json.dumps(blob))).state
    assert first is not None
    again = decode_continuation(json.loads(json.dumps(serialize_continuation(first)))).state
    assert again == first
    assert serialize_continuation(first) == serialize_continuation(again)


def test_serialized_blob_is_camel_case_and_json_native() -> None:
    blob = _valid_blob()
    assert "pausedSubagentId" in blob
    assert "paused_subagent_id" not in blob
    # No dataclasses / pydantic models survive into the JSON column.
    assert json.loads(json.dumps(blob)) == blob


_LEGACY_V1_BLOB: dict[str, Any] = {
    # No `version` key at all, snake_case everywhere, explicit nulls where the
    # field is now a plain string, int source ids, and no emitted-chars cursor.
    "phase": "worker",
    "paused_subagent_id": "worker-0",
    "user_text": "causes of inflation",
    "plan": ["causes of inflation", "effects on housing"],
    "completed_workers": [
        {
            "subagent_id": "worker-1",
            "sub_question": "effects on housing",
            "answer": None,
            "usage": {"input_tokens": 3, "output_tokens": None},
            "cost_usd": 0.001,
            "source_ids": [1, 2],
        }
    ],
    "planner_usage": {"input_tokens": 9},
    "planner_cost_usd": 0.002,
    "partial_answer": "half a draft",
    "partial_reasoning": None,
    "source_ids": [3],
    "orchestration_mode": "deep_research",
    "paused_worker_used_fallback": None,
}


def test_legacy_v1_blob_reads_through_the_one_adapter() -> None:
    """Every legacy tolerance lives in the codec — there is no second reader."""
    decoded = decode_continuation(_LEGACY_V1_BLOB)
    state = decoded.state
    assert state is not None
    assert state.version == 1
    assert state.paused_subagent_id == "worker-0"
    assert state.completed_workers[0].answer == ""
    assert state.completed_workers[0].usage == UsageUpdate(input_tokens=3)
    assert state.completed_workers[0].source_ids == ("1", "2")
    assert state.completed_workers[0].outcome == "succeeded"
    assert state.partial_reasoning == ""
    assert state.source_ids == ("3",)
    assert state.paused_worker_used_fallback is False
    # A v1 blob carried no cursor: the whole draft was already streamed.
    assert state.emitted_answer_chars == len("half a draft")
    # And it stays v1 on rewrite, so nothing claims a v2 guarantee it lacks.
    assert serialize_continuation(state)["version"] == 1
    assert decode_continuation(serialize_continuation(state)).state == state


def test_legacy_unknown_orchestration_mode_falls_back_to_caller_policy() -> None:
    """A mode this build does not run resolves through the route's own pin."""
    decoded = decode_continuation({**_valid_blob(), "orchestrationMode": "hyper_research"})
    assert decoded.state is not None
    assert decoded.state.orchestration_mode is None


def test_parse_continuation_is_the_state_only_view_of_the_same_decode() -> None:
    assert parse_continuation(_valid_blob()) == _full_state()
    assert parse_continuation({**_valid_blob(), "version": 99}) is None
    assert parse_continuation(None) is None


# --- Resolution: invalid is not absent ---------------------------------------


def test_server_state_decode_distinguishes_absent_from_invalid() -> None:
    assert decode_continuation_from_server_state(None, "c1") == ContinuationDecode()
    assert decode_continuation_from_server_state({}, "c1") == ContinuationDecode()
    absent = decode_continuation_from_server_state(
        {SERVER_STATE_CONTINUATIONS_KEY: {}}, "c1"
    )
    assert not absent.present
    stored = {SERVER_STATE_CONTINUATIONS_KEY: {"c1": {**_valid_blob(), "version": 99}}}
    invalid = decode_continuation_from_server_state(stored, "c1")
    assert invalid.invalid
    assert invalid.error


def test_a_malformed_continuations_container_is_invalid_not_absent() -> None:
    """`{"continuations": []}` is a corrupt row, not a row without a checkpoint.

    Reading it as absent walked the resume past the invalid-checkpoint gate and on
    to approval settlement.
    """
    for container in ([], "corrupt", 7, [{"c1": {}}]):
        decoded = decode_continuation_from_server_state(
            {SERVER_STATE_CONTINUATIONS_KEY: container}, "c1"
        )
        assert decoded.invalid, container
        assert "continuations" in (decoded.error or "")


def test_a_checkpoint_stored_as_null_is_invalid_not_absent() -> None:
    """A present key holding null is only indistinguishable from a missing key if
    the decode throws the distinction away."""
    present_null = decode_continuation_from_server_state(
        {SERVER_STATE_CONTINUATIONS_KEY: {"c1": None}}, "c1"
    )
    assert present_null.invalid
    assert present_null.error
    missing_key = decode_continuation_from_server_state(
        {SERVER_STATE_CONTINUATIONS_KEY: {"other": _valid_blob()}}, "c1"
    )
    assert not missing_key.present


def test_a_malformed_server_state_is_invalid_not_absent() -> None:
    """An unreadable server-only blob is not "no checkpoint" either."""
    for server_state in ([], "corrupt", 0, 1.5):
        assert decode_continuation_from_server_state(server_state, "c1").invalid, server_state


@pytest.mark.parametrize(
    "server_state",
    [
        None,
        {},
        {SERVER_STATE_CONTINUATIONS_KEY: None},
        {SERVER_STATE_CONTINUATIONS_KEY: {}},
        {SERVER_STATE_CONTINUATIONS_KEY: {"other": "blob"}},
    ],
)
def test_absent_stays_absent_for_rows_that_hold_no_checkpoint(server_state: object) -> None:
    """Closing the invalid-versus-absent hole must not make ordinary rows invalid —
    a single-mode or plan-approval pause legitimately carries no continuation."""
    assert decode_continuation_from_server_state(server_state, "c1") == ContinuationDecode()


@pytest.mark.parametrize(
    "server_state",
    [
        {SERVER_STATE_CONTINUATIONS_KEY: []},
        {SERVER_STATE_CONTINUATIONS_KEY: {"c1": None}},
        {SERVER_STATE_CONTINUATIONS_KEY: {"c1": "corrupt"}},
    ],
)
@pytest.mark.parametrize("with_legacy", [False, True])
def test_a_malformed_stored_checkpoint_neither_falls_back_nor_reads_as_absent(
    server_state: dict[str, Any], with_legacy: bool
) -> None:
    """Without a legacy blob the route used to see `present=False` and settle."""
    tool_input: dict[str, Any] = {"query": "kickoff"}
    if with_legacy:
        tool_input[CONTINUATION_INPUT_KEY] = _valid_blob()
    cleaned, decoded = resolve_continuation_decode(
        server_state=server_state, tool_input=tool_input, tool_call_id="c1"
    )
    assert cleaned == {"query": "kickoff"}
    assert decoded.invalid


def test_a_legacy_checkpoint_stored_as_null_is_invalid_too() -> None:
    """The legacy tool-input embedding gets the same present-versus-absent rule."""
    _, stored_null = resolve_continuation_decode(
        tool_input={"query": "kickoff", CONTINUATION_INPUT_KEY: None}, tool_call_id="c1"
    )
    assert stored_null.invalid
    _, no_key = resolve_continuation_decode(
        tool_input={"query": "kickoff"}, tool_call_id="c1"
    )
    assert not no_key.present


def test_decode_continuation_separates_a_stored_null_from_a_missing_one() -> None:
    assert decode_continuation(None) == ContinuationDecode()
    assert decode_continuation(None, stored=True).invalid


def test_a_corrupt_server_checkpoint_does_not_fall_back_to_legacy_tool_input() -> None:
    """Falling back would resume from a stale snapshot the server already replaced."""
    legacy_input = {"query": "kickoff", CONTINUATION_INPUT_KEY: _valid_blob()}
    server_state = {SERVER_STATE_CONTINUATIONS_KEY: {"c1": {**_valid_blob(), "version": 99}}}
    cleaned, decoded = resolve_continuation_decode(
        server_state=server_state, tool_input=legacy_input, tool_call_id="c1"
    )
    assert cleaned == {"query": "kickoff"}
    assert decoded.invalid


def test_legacy_tool_input_is_still_read_when_the_server_holds_nothing() -> None:
    cleaned, decoded = resolve_continuation_decode(
        server_state={SERVER_STATE_CONTINUATIONS_KEY: {}},
        tool_input={"query": "kickoff", CONTINUATION_INPUT_KEY: _LEGACY_V1_BLOB},
        tool_call_id="c1",
    )
    assert cleaned == {"query": "kickoff"}
    assert decoded.state is not None
    assert decoded.state.version == 1


# --- Ledger seeds and usage read the same way -------------------------------


@pytest.mark.parametrize("amount", [-1.0, float("inf"), float("nan"), "free", None, True, []])
def test_ledger_cost_seeds_never_raise_and_never_credit_nonsense(amount: object) -> None:
    seeds = get_run_ledger_from_server_state(
        {"plannerCostUsd": amount, "priorRunCostUsd": amount}
    )
    assert seeds.planner_cost_usd == 0.0
    assert seeds.prior_run_cost_usd == 0.0


def test_ledger_seeds_read_legacy_snake_case_keys() -> None:
    seeds = get_run_ledger_from_server_state(
        {
            "planner_cost_usd": 0.5,
            "planner_usage": {"input_tokens": 4},
            "prior_run_cost_usd": 0.25,
            "prior_run_usage": {"outputTokens": 6},
            "orchestration_mode": "single",
        }
    )
    assert seeds.planner_cost_usd == 0.5
    assert seeds.planner_usage == UsageUpdate(input_tokens=4)
    assert seeds.prior_run_cost_usd == 0.25
    assert seeds.prior_run_usage == UsageUpdate(output_tokens=6)
    assert seeds.orchestration_mode == "single"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "nope",
        {"inputTokens": -1},
        {"inputTokens": "many"},
        {"inputTokens": float("inf")},
        {"inputTokens": [1]},
    ],
)
def test_usage_from_wire_is_total(raw: object) -> None:
    assert usage_from_wire(raw) == UsageUpdate()


def test_usage_wire_round_trips() -> None:
    usage = UsageUpdate(
        input_tokens=1, output_tokens=2, reasoning_tokens=3, cached_input_tokens=4
    )
    wire = usage_to_wire(usage)
    assert wire == {
        "inputTokens": 1,
        "outputTokens": 2,
        "reasoningTokens": 3,
        "cachedInputTokens": 4,
    }
    assert usage_from_wire(wire) == usage
    assert usage_from_wire({"input_tokens": 1, "output_tokens": 2}) == UsageUpdate(
        input_tokens=1, output_tokens=2
    )


# --- Route: invalid checkpoint refuses BEFORE settlement ---------------------


@contextmanager
def _agentic_env() -> Iterator[None]:
    keys = {
        "TOOLS_ENABLED": "true",
        "AGENTIC_ENABLED": "true",
        "AGENTIC_PLAN_APPROVAL": "false",
    }
    prior = {key: os.environ.get(key) for key in keys}
    os.environ.update(keys)
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


@pytest.fixture
async def agentic_client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    from app.main import create_app
    from app.middleware.ratelimit import limiter
    from app.routes.conversations import _TEMP_IDS
    from app.streaming import replay_registry, stop_registry

    with _agentic_env():
        _TEMP_IDS.clear()
        stop_registry._STOP_REQUESTS.clear()
        replay_registry._BUFFERS.clear()
        storage = limiter._storage
        if hasattr(storage, "storage"):
            storage.storage.clear()
        if hasattr(storage, "expirations"):
            storage.expirations.clear()

        app_ = create_app()

        async def _get_db_override() -> AsyncIterator[AsyncSession]:
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app_.dependency_overrides[get_db] = _get_db_override
        transport = ASGITransport(app=app_)
        try:
            async with AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                yield client
        finally:
            _TEMP_IDS.clear()
            stop_registry._STOP_REQUESTS.clear()
            replay_registry._BUFFERS.clear()


_WORKER_HITL_PROMPT = "DEEP_RESEARCH: TOOL_APPROVE schedule kickoff | sibling housing effects"
_WORKER_CALL_ID = "worker-0::fake_worker_cal_0"


async def _bootstrap_pro_conversation(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> str:
    await client.get("/api/bootstrap")
    async with session_factory() as session:
        user_id = (await session.execute(select(User))).scalar_one().id
        await billing_repo.upsert_subscription_entitlement(
            session,
            user_id=UUID(str(user_id)),
            provider="fake",
            subscription_id=f"sub-{user_id}",
            status="active",
            customer_id=f"cus-{user_id}",
            current_period_end=datetime.now(UTC) + timedelta(days=30),
            event_created_at=datetime.now(UTC),
        )
        convo = Conversation(
            user_id=user_id, title="New chat", selected_tier_id="smart", pinned=False
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return str(convo.id)


async def _paused_row(
    session_factory: async_sessionmaker[AsyncSession], conv_id: str
) -> Message:
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(Message)
                    .where(Message.conversation_id == UUID(conv_id))
                    .where(Message.role == "assistant")
                    .order_by(Message.created_at.asc(), Message.id.asc())
                )
            )
            .scalars()
            .all()
        )
        return list(rows)[-1]


def _tool_call_part(row: Message, call_id: str) -> dict[str, Any]:
    parts = [p for p in (row.parts or []) if isinstance(p, dict)]
    return next(p for p in parts if p.get("type") == "tool_call" and p.get("id") == call_id)


_Corrupt = Callable[[dict[str, Any]], dict[str, Any]]


def _in_blob(**overrides: Any) -> _Corrupt:
    """Corrupt fields inside the stored checkpoint dictionary."""

    def _apply(state: dict[str, Any]) -> dict[str, Any]:
        conts = dict(state[SERVER_STATE_CONTINUATIONS_KEY])
        conts[_WORKER_CALL_ID] = {**conts[_WORKER_CALL_ID], **overrides}
        return {**state, SERVER_STATE_CONTINUATIONS_KEY: conts}

    return _apply


def _container(replacement: Any) -> _Corrupt:
    """Replace the whole `continuations` container, or the stored value under the key."""
    return lambda state: {**state, SERVER_STATE_CONTINUATIONS_KEY: replacement}


# Each corruption is one AC-06 rejection class, and all are JSON-native so they really
# survive a durable round trip through the `server_state` column.
_ROUTE_CORRUPTIONS: dict[str, _Corrupt] = {
    "unsupported_version": _in_blob(version=99),
    "non_numeric_cost": _in_blob(plannerCostUsd="free"),
    "bool_as_money": _in_blob(actualCostUsd=True),
    "bool_as_count": _in_blob(emittedAnswerChars=True),
    "unknown_outcome": _in_blob(
        completedWorkers=[
            {
                "subagentId": "worker-1",
                "subQuestion": "effects on housing",
                "answer": "ok",
                "outcome": "exploded",
            }
        ]
    ),
    # A checkpoint that is present but unreadable must not read as absent: that let
    # the resume past the gate and settle the approval on an unresumable turn.
    "checkpoint_stored_as_null": _container({_WORKER_CALL_ID: None}),
    "container_is_a_list": _container([]),
    "container_is_a_string": _container("corrupt"),
}


@pytest.mark.parametrize("corruption", sorted(_ROUTE_CORRUPTIONS))
async def test_invalid_checkpoint_refuses_the_resume_before_settling_the_approval(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    """AC-06: a corrupt checkpoint is a typed non-500 refusal, not a burnt approval.

    Settling first and discovering the unreadable checkpoint afterwards would
    consume the one approval the user can give and leave the turn unresumable.
    `plannerCostUsd: "free"` additionally used to reach `float(...)` and raise,
    turning a durable-row read into a 500.
    """
    conv_id = await _bootstrap_pro_conversation(agentic_client, session_factory)

    pause = await agentic_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "c0000000-0000-0000-0000-000000000001",
            "tierId": "smart",
            "text": _WORKER_HITL_PROMPT,
            "agenticMode": "deep_research",
        },
        timeout=20.0,
    )
    assert pause.status_code == 200, pause.text

    paused = await _paused_row(session_factory, conv_id)
    assert paused.status == "awaiting_approval"
    assert decode_continuation_from_server_state(
        paused.server_state, _WORKER_CALL_ID
    ).state is not None, "the pause must persist a decodable checkpoint first"

    # Corrupt the durable checkpoint the way an older writer (or a rolled-back
    # deploy) would leave it.
    async with session_factory() as session:
        row = await session.get(Message, paused.id)
        assert row is not None
        row.server_state = _ROUTE_CORRUPTIONS[corruption](dict(row.server_state or {}))
        await session.commit()

    settlements: list[str] = []

    async def _no_settle(*_args: Any, **kwargs: Any) -> None:
        settlements.append(str(kwargs.get("tool_call_id")))
        raise AssertionError("settlement ran before the checkpoint was validated")

    monkeypatch.setattr(
        conversations_route, "claim_and_settle_approval_outcome", _no_settle
    )
    monkeypatch.setattr(
        conversations_route, "settle_pseudo_tool_approval_outcome", _no_settle
    )

    resume = await agentic_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "c0000000-0000-0000-0000-000000000002",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": _WORKER_CALL_ID, "decision": "approve"},
        },
        timeout=20.0,
    )

    assert resume.status_code == 409, resume.text
    assert resume.status_code < 500
    envelope = resume.json()["error"]
    assert envelope["code"] == "AGENTIC_CHECKPOINT_INVALID"
    assert envelope["severity"] == "error"
    assert envelope["body"]
    assert settlements == [], "the approval was settled before validation"

    # The pause is untouched: still awaiting, still pending, no tool_result.
    after = await _paused_row(session_factory, conv_id)
    assert after.status == "awaiting_approval"
    call_part = _tool_call_part(after, _WORKER_CALL_ID)
    assert call_part["status"] == "awaiting_approval"
    assert call_part["approvalState"] == "pending"
    assert not [
        p
        for p in (after.parts or [])
        if isinstance(p, dict)
        and p.get("type") == "tool_result"
        and p.get("id") == _WORKER_CALL_ID
    ]
    # And no continuation turn was started.
    async with session_factory() as session:
        assistants = (
            (
                await session.execute(
                    select(Message)
                    .where(Message.conversation_id == UUID(conv_id))
                    .where(Message.role == "assistant")
                )
            )
            .scalars()
            .all()
        )
    assert len(list(assistants)) == 1


async def test_invalid_checkpoint_refuses_before_the_claimed_without_result_settle(
    agentic_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-06 ordering, on the branch the route settles itself.

    A pending approval defers settlement to the producer, so refusing the pending
    resume proves little about ordering on its own. A call that was claimed but
    left without a durable result settles inside `_prepare_resume_tool` (fail
    closed, no re-execute) — the checkpoint gate must run before that call.
    """
    conv_id = await _bootstrap_pro_conversation(agentic_client, session_factory)
    pause = await agentic_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "c0000000-0000-0000-0000-000000000003",
            "tierId": "smart",
            "text": _WORKER_HITL_PROMPT,
            "agenticMode": "deep_research",
        },
        timeout=20.0,
    )
    assert pause.status_code == 200, pause.text
    paused = await _paused_row(session_factory, conv_id)

    # Claimed-without-result + a checkpoint that no longer decodes.
    async with session_factory() as session:
        row = await session.get(Message, paused.id)
        assert row is not None
        parts = [dict(p) for p in (row.parts or []) if isinstance(p, dict)]
        for part in parts:
            if part.get("type") == "tool_call" and part.get("id") == _WORKER_CALL_ID:
                part["approvalState"] = "approved"
        row.parts = parts
        state = dict(row.server_state or {})
        conts = dict(state[SERVER_STATE_CONTINUATIONS_KEY])
        conts[_WORKER_CALL_ID] = {**conts[_WORKER_CALL_ID], "version": 99}
        state[SERVER_STATE_CONTINUATIONS_KEY] = conts
        row.server_state = state
        await session.commit()

    settlements: list[str] = []

    async def _spy_settle(*_args: Any, **kwargs: Any) -> None:
        settlements.append(str(kwargs.get("tool_call_id")))
        raise AssertionError("settlement ran before the checkpoint was validated")

    monkeypatch.setattr(
        conversations_route, "claim_and_settle_approval_outcome", _spy_settle
    )

    resume = await agentic_client.post(
        f"/api/conversations/{conv_id}/messages",
        json={
            "clientMessageId": "c0000000-0000-0000-0000-000000000004",
            "tierId": "smart",
            "text": "",
            "toolApproval": {"toolCallId": _WORKER_CALL_ID, "decision": "approve"},
        },
        timeout=20.0,
    )
    assert resume.status_code == 409, resume.text
    assert resume.json()["error"]["code"] == "AGENTIC_CHECKPOINT_INVALID"
    assert settlements == [], "the claimed-without-result settle ran first"

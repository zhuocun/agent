"""AC-09: one `WorkerRunner` drives both a fresh worker and a resumed one.

Before this packet a deep-research worker had TWO lifecycle engines — a fresh one
under `orchestrator._run_worker._consume`, a resumed one under
`_resume_worker_continuation._drain` — each carrying its own copy of event
tagging, citation rewriting, transcript capture, retryable fallback, usage
folding, pricing on the route that served, and terminal classification. They had
already drifted apart, so the closure condition here is a CONFORMANCE MATRIX:
the same synthetic provider stream is driven once per seed and both runs must
agree on the normalized events, the source and transcript state, the fallback
route, the usage and cost, and the typed outcome.

Where the two seeds legitimately differ, they differ only in what the seed
restores, and each difference is pinned by its own test:

- a resumed seed carries pre-pause prose, citations, transcript, usage and cost
  forward, and does NOT re-emit the prose the paused turn already delivered;
- an empty answer fails a fresh worker (FL-05) but not a resumed one, whose
  finding already reached the user;
- a resumed seed pinned to the fallback skips the primary route entirely (B6).
"""

from __future__ import annotations

import ast
import asyncio
import textwrap
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.agentic.budget import BudgetGate
from app.agentic.sources import SourceNamespace
from app.agentic.worker import (
    FreshWorkerSeed,
    ResumedWorkerSeed,
    WorkerCancelled,
    WorkerCompleted,
    WorkerFailed,
    WorkerOutcome,
    WorkerPaused,
    WorkerRoutes,
    WorkerRunner,
    WorkerSeed,
)
from app.config import Settings
from app.errors import AppError, ErrorEnvelope
from app.providers.protocol import (
    AnswerDelta,
    AwaitingApproval,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    Sources,
    SubagentStarted,
    ToolCall,
    ToolResult,
    UsageUpdate,
)
from app.runtime.context import ServedRoute
from app.runtime.run_receipt import CostLedger
from app.search.protocol import SourceItem

# $0.01 per input token on the primary, $0.02 on the fallback, so a priced total
# also proves WHICH binding priced it.
PRIMARY_RATE = 0.01
FALLBACK_RATE = 0.02

BOUND = ServedRoute(tier_id="smart", provider_id="deepseek", model_id="v4-pro")


def _settings(**kwargs: object) -> Settings:
    base: dict[str, object] = {
        # `provider_backend` carries no alias, so it populates by FIELD name; the
        # agentic / tools knobs are aliased and populate by their uppercase env
        # name. Mixing them up is silently ignored under `extra="ignore"`.
        "provider_backend": "fake",
        "AGENTIC_ENABLED": True,
        "TOOLS_ENABLED": True,
        "AGENTIC_RUN_BUDGET_USD": 10.0,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def _price(rate: float) -> Callable[[UsageUpdate], float]:
    def _cost(usage: UsageUpdate) -> float:
        return usage.input_tokens * rate

    return _cost


EventScript = Callable[[], list[ProviderEvent]]


def _factory(script: EventScript, *, raises: BaseException | None = None) -> Any:
    """A `StreamFactory` replaying one canned event list per agent-loop attempt."""

    def _make_stream_for(_prompt: str, **_kwargs: object) -> Any:
        def _make(
            _feedback: list[ToolResult], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                for event in script():
                    yield event
                if raises is not None:
                    raise raises

            return _gen()

        return _make

    return _make_stream_for


def _routes(
    primary: Any,
    *,
    fallback: Any | None = None,
    route: ServedRoute | None = BOUND,
) -> WorkerRoutes:
    return WorkerRoutes(
        make_stream_for=primary,
        cost_for_usage=_price(PRIMARY_RATE),
        primary=route,
        fallback_make_stream_for=fallback,
        fallback_cost_for_usage=_price(FALLBACK_RATE) if fallback else None,
        fallback_provider_id="anthropic" if fallback else None,
        fallback_model_id="claude-x" if fallback else None,
        fallback_display_label="Claude X" if fallback else None,
    )


async def _drive(
    seed: WorkerSeed,
    routes: WorkerRoutes,
    *,
    settings: Settings | None = None,
    ledger: CostLedger | None = None,
    sources: SourceNamespace | None = None,
    budget_gate: BudgetGate | None = None,
) -> tuple[list[ProviderEvent], WorkerOutcome, CostLedger]:
    """Exhaust one runner and return its events, its outcome and its ledger."""
    run_ledger = ledger if ledger is not None else CostLedger()
    runner = WorkerRunner(
        settings=settings or _settings(),
        routes=routes,
        sources=sources if sources is not None else SourceNamespace(),
        ledger=run_ledger,
        budget_gate=budget_gate,
    )
    events = [event async for event in runner.run(seed)]
    outcome = runner.outcome
    assert outcome is not None
    return events, outcome, run_ledger


# --- the shared script both seeds are driven with ------------------------------


def _shared_script() -> list[ProviderEvent]:
    """One worker turn that exercises every concern the runner owns.

    `web_search` is provider-internal rather than a registry tool, so its call and
    result relay through the agent loop instead of being intercepted by the
    approval gate — which is what a worker's tool traffic looks like in practice
    (the registry allowlist a worker gets is gated, and that path is the pause
    test below).
    """
    return [
        ReasoningDelta(text="thinking"),
        Sources(items=[SourceItem(id="1", title="T", url="https://e.example")]),
        AnswerDelta(text="finding [1]"),
        ToolCall(id="c1", name="web_search", label="Search", input={"q": "a"}),
        ToolResult(tool_call_id="c1", name="web_search", summary="ok"),
        Complete(usage=UsageUpdate(input_tokens=6, output_tokens=3)),
    ]


def _fresh(**kwargs: object) -> FreshWorkerSeed:
    base: dict[str, Any] = {
        "index": 0,
        "subagent_id": "worker-0",
        "label": "Worker 1",
        "sub_question": "alpha",
        "prompt": "answer alpha",
    }
    base.update(kwargs)
    return FreshWorkerSeed(**base)


def _resumed(**kwargs: object) -> ResumedWorkerSeed:
    base: dict[str, Any] = {
        "index": 0,
        "subagent_id": "worker-0",
        "label": "Worker 1",
        "sub_question": "alpha",
        "prompt": "answer alpha",
    }
    base.update(kwargs)
    return ResumedWorkerSeed(**base)


SEEDS: dict[str, Callable[..., WorkerSeed]] = {"fresh": _fresh, "resumed": _resumed}


def _normalize(events: list[ProviderEvent]) -> list[tuple[str, Any]]:
    """The comparable shape of a worker's stream: type, subagent tag, payload."""
    rows: list[tuple[str, Any]] = []
    for event in events:
        sid = getattr(event, "subagent_id", None)
        kind = type(event).__name__
        if isinstance(event, AnswerDelta | ReasoningDelta):
            rows.append((kind, (sid, event.text)))
        elif isinstance(event, Sources):
            rows.append((kind, (sid, tuple(str(i.id) for i in event.items))))
        elif isinstance(event, ToolCall):
            rows.append((kind, (sid, event.id, event.name)))
        elif isinstance(event, ToolResult):
            rows.append((kind, (sid, event.tool_call_id, event.name)))
        elif isinstance(event, Complete):
            rows.append((kind, (sid, event.usage, event.substitution)))
        else:
            rows.append((kind, sid))
    return rows


@pytest.mark.asyncio
@pytest.mark.parametrize("seed_name", sorted(SEEDS))
async def test_conformance_both_seeds_normalize_the_same_stream(seed_name: str) -> None:
    """The matrix: one script, either seed, equivalent normalized events."""
    events, outcome, ledger = await _drive(
        SEEDS[seed_name](), _routes(_factory(_shared_script))
    )

    assert _normalize(events) == [
        ("SubagentStarted", "worker-0"),
        ("ReasoningDelta", ("worker-0", "thinking")),
        ("Sources", ("worker-0", ("1",))),
        ("AnswerDelta", ("worker-0", "finding [1]")),
        ("ToolCall", ("worker-0", "worker-0::c1", "web_search")),
        ("ToolResult", ("worker-0", "worker-0::c1", "web_search")),
        ("Complete", ("worker-0", UsageUpdate(input_tokens=6, output_tokens=3), None)),
    ]
    assert isinstance(outcome, WorkerCompleted)
    result = outcome.result
    assert result.answer == "finding [1]"
    assert result.reasoning == "thinking"
    assert result.source_ids == ("1",)
    # Transcript capture: one row per tool event, ids namespaced per subagent.
    assert [part["type"] for part in result.tool_transcript] == [
        "tool_call",
        "tool_result",
    ]
    assert result.tool_transcript[0]["id"] == "worker-0::c1"
    assert result.tool_transcript[1]["toolCallId"] == "worker-0::c1"
    # Usage / cost / served route settle identically for either seed.
    assert result.session_usage == UsageUpdate(input_tokens=6, output_tokens=3)
    assert result.session_cost_usd == pytest.approx(0.06)
    assert result.used_fallback is False
    assert result.route == BOUND
    # The terminal rides on the outcome, not the stream, and matches the ledger.
    assert outcome.done_event.outcome == "succeeded"
    assert outcome.done_event.cost_usd == pytest.approx(0.06)
    phase = ledger.phase("worker-0")
    assert phase is not None
    assert phase.role == "worker" and phase.outcome == "succeeded"
    assert phase.cost_usd == pytest.approx(0.06)


@pytest.mark.asyncio
@pytest.mark.parametrize("seed_name", sorted(SEEDS))
async def test_conformance_both_seeds_take_the_same_fallback_route(
    seed_name: str,
) -> None:
    """One retryable failure before any visible progress, either seed: the
    fallback serves, prices, and stamps the relayed terminal (FL-22 / BE-023)."""
    boom = AppError(
        ErrorEnvelope(
            code="PROVIDER_UPSTREAM", severity="error", title="down", body="down"
        ),
        status_code=503,
    )
    events, outcome, _ = await _drive(
        SEEDS[seed_name](),
        _routes(
            _factory(lambda: [], raises=boom),
            fallback=_factory(
                lambda: [
                    AnswerDelta(text="from fallback"),
                    Complete(usage=UsageUpdate(input_tokens=5)),
                ]
            ),
        ),
    )

    assert isinstance(outcome, WorkerCompleted)
    result = outcome.result
    assert result.used_fallback is True
    assert result.substitution == "provider_fallback"
    assert result.substituted_provider == "anthropic"
    assert result.substituted_model == "claude-x"
    assert result.substituted_display_label == "Claude X"
    # Priced on the FALLBACK rate, and the served route says so.
    assert result.session_cost_usd == pytest.approx(0.10)
    assert result.route == ServedRoute(
        tier_id="smart",
        provider_id="anthropic",
        model_id="claude-x",
        substitution="provider_fallback",
    )
    # FL-22: the relayed Complete carries the served route, not a bare primary.
    (relayed,) = [e for e in events if isinstance(e, Complete)]
    assert relayed.substitution == "provider_fallback"
    assert relayed.substituted_provider == "anthropic"
    assert outcome.done_event.substituted_model == "claude-x"


@pytest.mark.asyncio
@pytest.mark.parametrize("seed_name", sorted(SEEDS))
async def test_conformance_both_seeds_refuse_fallback_after_visible_progress(
    seed_name: str,
) -> None:
    """B16 / SAF-008: a retry after client-visible progress would concatenate two
    attempts into one answer, so either seed fails instead of retrying."""
    boom = AppError(
        ErrorEnvelope(code="PROVIDER_UPSTREAM", severity="error", title="x", body="x"),
        status_code=503,
    )
    fallback_calls: list[str] = []

    def _tracked(_prompt: str, **_kwargs: object) -> Any:
        fallback_calls.append(_prompt)
        return _factory(lambda: [Complete(usage=UsageUpdate())])(_prompt)

    _events, outcome, _ = await _drive(
        SEEDS[seed_name](),
        _routes(
            _factory(lambda: [AnswerDelta(text="partial")], raises=boom),
            fallback=_tracked,
        ),
    )

    assert fallback_calls == []
    assert isinstance(outcome, WorkerFailed)
    # The partial prose is still on the books, and so is its outcome.
    assert outcome.result.answer == "partial"
    assert outcome.done_event.outcome == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("seed_name", sorted(SEEDS))
async def test_conformance_both_seeds_produce_the_same_pause_facts(
    seed_name: str,
) -> None:
    """A tool-approval gate yields a typed `WorkerPaused` for either seed: FACTS
    only, deliberately non-terminal, with the pause's `AwaitingApproval` left to
    the phase owner (the only layer that can serialize a continuation)."""

    def _script() -> list[ProviderEvent]:
        return [
            AnswerDelta(text="before gate"),
            ToolCall(
                id="c9",
                name="calendar_create_event",
                label="Cal",
                status="awaiting_approval",
                approval_state="pending",
            ),
            AwaitingApproval(tool_call_id="c9"),
        ]

    events, outcome, ledger = await _drive(
        SEEDS[seed_name](), _routes(_factory(_script))
    )

    assert isinstance(outcome, WorkerPaused)
    assert outcome.tool_call_id == "worker-0::c9"
    assert outcome.tool_name == "calendar_create_event"
    assert outcome.tool_label == "Cal"
    # B15 / BE-005: no terminal, so the FE row stays open for the resume.
    assert outcome.done_event is None
    assert not [e for e in events if isinstance(e, AwaitingApproval)]
    # The phase owner settles a pause, not the runner: only it knows whether this
    # pause won the run's one continuation.
    assert ledger.phase("worker-0") is None
    assert outcome.result.answer == "before gate"
    assert outcome.result.tool_transcript[0]["id"] == "worker-0::c9"


@pytest.mark.asyncio
@pytest.mark.parametrize("seed_name", sorted(SEEDS))
async def test_conformance_both_seeds_bill_a_cancelled_worker(
    seed_name: str,
) -> None:
    """FE-002 / SAF-005: a cancelled row still owes the wire a terminal and its
    snapshot spend still reaches the roll-up — for either seed."""

    ledger = CostLedger()
    runner = WorkerRunner(
        settings=_settings(),
        routes=_routes(
            _factory(
                lambda: [
                    AnswerDelta(text="partial"),
                    Complete(usage=UsageUpdate(input_tokens=4)),
                ]
            )
        ),
        sources=SourceNamespace(),
        ledger=ledger,
    )
    stream = runner.run(SEEDS[seed_name]())
    # Stop mid-relay: throw the cancel INTO the suspended generator, which is what
    # `aclosing` / task cancellation does to the orchestrator's relay.
    await stream.asend(None)
    with pytest.raises(asyncio.CancelledError):
        await stream.athrow(asyncio.CancelledError())

    outcome = runner.outcome
    assert isinstance(outcome, WorkerCancelled)
    assert outcome.outcome == "stopped"
    assert outcome.done_event is not None
    assert outcome.done_event.outcome == "stopped"
    phase = ledger.phase("worker-0")
    assert phase is not None and phase.outcome == "stopped"


# --- where the seeds legitimately differ --------------------------------------


@pytest.mark.asyncio
async def test_resumed_seed_carries_pre_pause_state_without_re_emitting_it() -> None:
    """H-010: the pause turn's prose, citations, transcript, usage and cost come
    back on the seed. The prose is restored for synthesis but NOT re-emitted — it
    already reached the user on the paused turn."""
    settled = ToolResult(
        tool_call_id="worker-0::c1",
        name="calendar_create_event",
        status="succeeded",
        approval_state="approved",
        summary="ok",
    )
    seed = _resumed(
        prior_answer="pre ",
        prior_reasoning="pre-thought ",
        prior_source_ids=("1",),
        prior_tool_transcript=(
            {"type": "tool_result", "toolCallId": "worker-0::c1", "name": "cal"},
        ),
        prior_tool_results=(settled,),
        prior_usage=UsageUpdate(input_tokens=10, output_tokens=5),
        prior_cost_usd=0.10,
        prior_emitted_answer_chars=4,
    )
    events, outcome, _ = await _drive(
        seed,
        _routes(
            _factory(
                lambda: [
                    AnswerDelta(text="post"),
                    Complete(usage=UsageUpdate(input_tokens=4, output_tokens=2)),
                ]
            )
        ),
    )

    assert [e.text for e in events if isinstance(e, AnswerDelta)] == ["post"]
    assert isinstance(outcome, WorkerCompleted)
    result = outcome.result
    assert result.answer == "pre post"
    assert result.reasoning == "pre-thought "
    assert result.source_ids == ("1",)
    assert result.tool_transcript[0]["toolCallId"] == "worker-0::c1"
    # B2: pre-pause spend is CUMULATIVE with this session's, never replaced by it.
    assert result.session_usage == UsageUpdate(input_tokens=4, output_tokens=2)
    assert result.usage == UsageUpdate(input_tokens=14, output_tokens=7)
    assert result.cost_usd == pytest.approx(0.10 + 0.04)
    assert result.emitted_answer_chars == len("pre post")


@pytest.mark.asyncio
async def test_empty_prose_fails_a_fresh_worker_but_not_a_resumed_one() -> None:
    """FL-05: a fresh worker that wrote nothing produced no finding. A resumed one
    already delivered its finding, so an empty increment is not a failure."""
    def script() -> list[ProviderEvent]:
        return [Complete(usage=UsageUpdate(input_tokens=1))]

    _e, fresh_outcome, _l = await _drive(_fresh(), _routes(_factory(script)))
    assert isinstance(fresh_outcome, WorkerFailed)
    assert fresh_outcome.done_event.outcome == "failed"
    # Partial spend is billed even on a failure (SAF-005).
    assert fresh_outcome.done_event.cost_usd == pytest.approx(0.01)

    _e2, resumed_outcome, _l2 = await _drive(
        _resumed(prior_answer="already said this"), _routes(_factory(script))
    )
    assert isinstance(resumed_outcome, WorkerCompleted)
    assert resumed_outcome.result.answer == "already said this"


@pytest.mark.asyncio
async def test_resumed_seed_pinned_to_fallback_skips_the_primary(
) -> None:
    """B6: a resume must not silently switch bindings mid-worker, so a pause that
    was served by the fallback never touches the primary again."""
    primary_calls: list[str] = []

    def _primary(prompt: str, **_kwargs: object) -> Any:
        primary_calls.append(prompt)
        return _factory(lambda: [AnswerDelta(text="primary")])(prompt)

    _events, outcome, _ = await _drive(
        _resumed(pinned_to_fallback=True, prior_answer="pre "),
        _routes(
            _primary,
            fallback=_factory(
                lambda: [
                    AnswerDelta(text="fallback"),
                    Complete(usage=UsageUpdate(input_tokens=3)),
                ]
            ),
        ),
    )

    assert primary_calls == []
    assert isinstance(outcome, WorkerCompleted)
    assert outcome.result.used_fallback is True
    # Priced on the fallback rate, as the pause turn was.
    assert outcome.result.session_cost_usd == pytest.approx(0.06)
    assert outcome.result.substitution == "provider_fallback"


@pytest.mark.asyncio
async def test_resume_budget_gate_halts_the_worker_on_its_own_stream() -> None:
    """B3: a resume has no sibling fan-out and no consumer to cancel it, so the
    cap is enforced on this worker's own stream against the RUN's baseline."""
    _events, outcome, _ = await _drive(
        _resumed(prior_answer="pre "),
        _routes(
            _factory(
                lambda: [
                    AnswerDelta(text="post"),
                    Complete(usage=UsageUpdate(input_tokens=50)),
                ]
            )
        ),
        settings=_settings(AGENTIC_RUN_BUDGET_USD=1.0),
        budget_gate=BudgetGate(baseline_usd=0.9, cap_usd=1.0),
    )

    assert isinstance(outcome, WorkerCompleted)
    assert outcome.outcome == "budget_cancelled"
    assert outcome.result.budget_halted is True
    assert outcome.done_event.outcome == "budget_cancelled"


@pytest.mark.asyncio
async def test_a_fresh_fan_out_worker_carries_no_gate_of_its_own() -> None:
    """The fresh fan-out's cap breach is enforced by the consumer cancelling
    workers, so a worker with no gate streams to the end and reports succeeded."""
    _events, outcome, _ = await _drive(
        _fresh(),
        _routes(
            _factory(
                lambda: [
                    AnswerDelta(text="lots"),
                    Complete(usage=UsageUpdate(input_tokens=5000)),
                ]
            )
        ),
        settings=_settings(AGENTIC_RUN_BUDGET_USD=0.01),
    )

    assert isinstance(outcome, WorkerCompleted)
    assert outcome.outcome == "succeeded"
    assert outcome.result.budget_halted is False


@pytest.mark.asyncio
async def test_runner_without_a_primary_route_settles_no_route() -> None:
    """A direct unit call passes no bound route; the runner must not invent one."""
    _events, outcome, _ = await _drive(
        _fresh(),
        _routes(_factory(_shared_script), route=None),
    )
    assert isinstance(outcome, WorkerCompleted)
    assert outcome.result.route is None


@pytest.mark.asyncio
async def test_citation_marker_split_across_deltas_is_held_then_flushed() -> None:
    """B12: an incomplete trailing marker is held until it completes, so a marker
    split across deltas still remaps — and whatever is STILL held at end of
    stream has to reach both the wire and the recorded answer."""
    # Starting the namespace above 1 makes the remap visible: the worker's local
    # `[1]` has to come out as the global its own `Sources` event was given.
    events, outcome, _ = await _drive(
        _fresh(),
        _routes(
            _factory(
                lambda: [
                    Sources(items=[SourceItem(id="1", title="T", url="https://e.x")]),
                    AnswerDelta(text="see ["),
                    AnswerDelta(text="1] and a dangling ["),
                    Complete(usage=UsageUpdate(input_tokens=1)),
                ]
            )
        ),
        sources=SourceNamespace(start=5),
    )

    assert isinstance(outcome, WorkerCompleted)
    assert [s.id for e in events if isinstance(e, Sources) for s in e.items] == [5]
    wire = "".join(e.text for e in events if isinstance(e, AnswerDelta))
    # The split `[1]` survived as ONE remapped marker, not two raw fragments.
    assert wire == "see [5] and a dangling ["
    # Nothing the worker wrote is missing from what synthesis will read.
    assert wire == outcome.result.answer


@pytest.mark.asyncio
async def test_two_workers_cannot_collide_on_a_provider_call_id() -> None:
    """H-004: independent provider sessions reuse call ids, so a shared id must
    not let one worker approve or replace another's gated call."""
    sources = SourceNamespace()
    ledger = CostLedger()
    seen: list[str] = []
    for index, sid in enumerate(("worker-0", "worker-1")):
        events, _outcome, _l = await _drive(
            _fresh(index=index, subagent_id=sid),
            _routes(
                _factory(
                    lambda: [
                        AnswerDelta(text="x"),
                        ToolCall(id="shared", name="calendar_create_event"),
                        ToolResult(tool_call_id="shared", name="calendar_create_event"),
                        Complete(usage=UsageUpdate(input_tokens=1)),
                    ]
                )
            ),
            ledger=ledger,
            sources=sources,
        )
        seen += [e.id for e in events if isinstance(e, ToolCall)]

    assert seen == ["worker-0::shared", "worker-1::shared"]


@pytest.mark.asyncio
async def test_started_precedes_every_tagged_content_event() -> None:
    """Ordering invariant: `SubagentStarted` opens the row before any tagged
    content, and the terminal is not in the stream at all."""
    events, outcome, _ = await _drive(_fresh(), _routes(_factory(_shared_script)))
    assert isinstance(events[0], SubagentStarted)
    assert not [e for e in events if type(e).__name__ == "SubagentDone"]
    assert isinstance(outcome, WorkerCompleted)
    assert outcome.done_event.subagent_id == "worker-0"


# --- span settlement for both seeds (AC-10) -----------------------------------


@pytest.fixture
def span_exporter() -> Iterator[InMemorySpanExporter]:
    """Collect spans created from here on, whatever registered a provider first."""
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)
    try:
        yield exporter
    finally:
        processor.shutdown()


def _agent_spans(exporter: InMemorySpanExporter) -> list[dict[str, Any]]:
    return [
        dict(span.attributes or {})
        for span in exporter.get_finished_spans()
        if span.name == "invoke_agent"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("seed_name", sorted(SEEDS))
async def test_worker_span_settles_with_route_usage_cost_and_outcome(
    seed_name: str, span_exporter: InMemorySpanExporter
) -> None:
    """AC-10: the worker phase span closes with what actually served it, the
    tokens behind the money, the exact cost, and how the phase ended."""
    await _drive(SEEDS[seed_name](), _routes(_factory(_shared_script)))

    (attrs,) = _agent_spans(span_exporter)
    assert attrs["agentic.role"] == "worker"
    assert attrs["agentic.subagent_id"] == "worker-0"
    assert attrs["agentic.served_tier_id"] == "smart"
    assert attrs["gen_ai.provider.name"] == "deepseek"
    assert attrs["gen_ai.response.model"] == "v4-pro"
    assert attrs["gen_ai.usage.input_tokens"] == 6
    assert attrs["gen_ai.usage.output_tokens"] == 3
    assert attrs["agentic.cost_usd"] == pytest.approx(0.06)
    assert attrs["agentic.outcome"] == "succeeded"
    assert "agentic.route.substitution" not in attrs
    assert not [key for key in attrs if "content" in key or "text" in key]


@pytest.mark.asyncio
async def test_worker_span_records_the_fallback_as_the_served_route(
    span_exporter: InMemorySpanExporter,
) -> None:
    """A substituted phase closes with ONE route — the one that served."""
    boom = AppError(
        ErrorEnvelope(
            code="RATE_LIMITED", severity="error", title="slow down", body="slow down"
        ),
        status_code=429,
    )
    await _drive(
        _fresh(),
        _routes(
            _factory(lambda: [], raises=boom),
            fallback=_factory(
                lambda: [
                    AnswerDelta(text="ok"),
                    Complete(usage=UsageUpdate(input_tokens=5)),
                ]
            ),
        ),
    )

    (attrs,) = _agent_spans(span_exporter)
    assert attrs["gen_ai.provider.name"] == "anthropic"
    assert attrs["gen_ai.response.model"] == "claude-x"
    assert attrs["agentic.served_tier_id"] == "smart"
    assert attrs["agentic.route.substitution"] == "rate_limited"
    assert attrs["agentic.cost_usd"] == pytest.approx(0.10)
    assert attrs["agentic.outcome"] == "succeeded"


@pytest.mark.asyncio
async def test_worker_span_records_a_failure_and_a_pause(
    span_exporter: InMemorySpanExporter,
) -> None:
    """A phase span must not vanish from the trace because the phase went wrong:
    a failure and a pause both close with their own outcome."""
    await _drive(
        _fresh(), _routes(_factory(lambda: [Complete(usage=UsageUpdate())]))
    )
    await _drive(
        _fresh(subagent_id="worker-1"),
        _routes(
            _factory(
                lambda: [
                    AnswerDelta(text="x"),
                    ToolCall(id="c1", name="calendar_create_event"),
                    AwaitingApproval(tool_call_id="c1"),
                ]
            )
        ),
    )

    failed, paused = _agent_spans(span_exporter)
    assert failed["agentic.outcome"] == "failed"
    assert paused["agentic.outcome"] == "paused"
    assert paused["agentic.served_tier_id"] == "smart"


@pytest.mark.asyncio
async def test_worker_span_records_a_budget_halt(
    span_exporter: InMemorySpanExporter,
) -> None:
    """A budget-cancelled phase is distinguishable in the trace from a Stop."""
    await _drive(
        _resumed(prior_answer="pre "),
        _routes(
            _factory(
                lambda: [
                    AnswerDelta(text="post"),
                    Complete(usage=UsageUpdate(input_tokens=50)),
                ]
            )
        ),
        settings=_settings(AGENTIC_RUN_BUDGET_USD=1.0),
        budget_gate=BudgetGate(baseline_usd=0.9, cap_usd=1.0),
    )

    (attrs,) = _agent_spans(span_exporter)
    assert attrs["agentic.outcome"] == "budget_cancelled"


# --- static closure: the parallel engines are gone ----------------------------


def _call_owners(module_source: str, callee: str) -> set[str]:
    """Names of the functions that call ``callee``, attributed to the INNERMOST one.

    Substring slicing cannot answer this question. `orchestrator.py` mentions
    `_resume_worker_continuation` twice — its `def` and its call from
    `_run_deep_research` — so splitting on the name yields the text between the two
    mentions or the text after the call, never the function body. A nested `def`
    (the fan-out's `_run_worker`) is not addressable by slicing at all. The AST
    knows exactly which function a call sits in, so ask it.
    """
    owners: set[str] = set()

    def visit(node: ast.AST, enclosing: str | None) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
                continue
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == callee
                and enclosing is not None
            ):
                owners.add(enclosing)
            visit(child, enclosing)

    visit(ast.parse(module_source), None)
    return owners


def test_the_old_worker_engines_no_longer_exist() -> None:
    """AC-09 closure by static search: two worker lifecycle engines became one, so
    the fresh `_consume`, the resume `_drain`, `_WorkerPause` and the duplicated
    fallback / settlement arms must not be findable in the orchestrator."""
    agentic = Path(__file__).resolve().parents[1] / "app" / "agentic"
    source = (agentic / "orchestrator.py").read_text()
    for gone in (
        "_WorkerPause",
        "_WorkerSubstituted",
        "async def _consume",
        "async def _drain",
        "_primary_make",
        "_stamp_fallback_route",
        "_cumulative_usage",
    ):
        assert gone not in source, gone
    # One runner, driven from exactly the two places a worker can start.
    assert source.count("WorkerRunner(") == 2
    # The orchestrator's remaining agent loops are the three NON-worker phases.
    # Pinning the exact set is what makes this a regression test: a worker engine
    # reintroduced anywhere — inside `_resume_worker_continuation`, inside the
    # fan-out's nested `_run_worker`, or in a new helper — adds a name here.
    assert _call_owners(source, "run_agent_loop") == {
        "_collect_answer",
        "_finalize_synthesis_streamed",
        "run_single",
    }
    # And the runner did not re-import the old names: ONE agent loop lives in the
    # worker module, reached by one relay, whichever seed drives it.
    runner_source = (agentic / "worker.py").read_text()
    assert _call_owners(runner_source, "run_agent_loop") == {"_relay"}
    assert runner_source.count("async def _relay(") == 1


def test_the_static_engine_search_is_scoped_to_function_bodies() -> None:
    """The assertion above is only worth its name if its scoping actually works.

    The previous version sliced the module on `"_resume_worker_continuation"` and
    read index 2. The name appears twice — the `def` and the call from
    `_run_deep_research` — so index 2 is the text AFTER the call, and the resume
    body sits in index 1. The assertion passed while looking at a region that
    could not contain the thing it was searching for.
    """
    smuggled_into_resume = textwrap.dedent(
        """
        async def _resume_worker_continuation(seed):
            async for event in run_agent_loop(make_stream=seed.stream):
                yield event


        async def _run_deep_research(x):
            async for event in _resume_worker_continuation(x):
                yield event
        """
    )
    # The AST names the regression.
    assert _call_owners(smuggled_into_resume, "run_agent_loop") == {
        "_resume_worker_continuation"
    }
    # The old scoping does not see it, which is exactly the blind spot.
    tail_after_the_call = smuggled_into_resume.split("_resume_worker_continuation")[2]
    assert "run_agent_loop(" not in tail_after_the_call

    # A nested engine is attributed to the innermost function, so hiding one inside
    # the fan-out scheduler still changes the pinned set.
    smuggled_into_fanout = textwrap.dedent(
        """
        async def _run_deep_research(x):
            async def _run_worker(seed):
                async for event in run_agent_loop(make_stream=seed.stream):
                    yield event

            await _run_worker(x)
        """
    )
    assert _call_owners(smuggled_into_fanout, "run_agent_loop") == {"_run_worker"}

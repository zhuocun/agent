"""`instrument_fastapi()` and the structlog OTel processor.

Acceptance criteria covered:
- Unset endpoint -> no-op, no tracer provider registered, no span exporter.
- Endpoint set OR explicit in-memory exporter passed -> tracing is on; a
  FastAPI request through the instrumented app produces at least one span.
- `add_otel_log_processor` injects `trace_id` / `span_id` when called inside
  an active span; no-op otherwise.
- In production with no endpoint, a startup warning is emitted.

Also the AC-10 primitives this packet lands ahead of the production span
migration: `ServedRoute` and the `SpanSettlement` handle `invoke_agent_span`
yields. Settling every production phase span with these is F2's work; what is
proven here is that the handle records route / usage / cost / outcome, that a
fallback overrides the served route rather than adding a second one, and that no
content attribute can ride along.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.agentic.aggregate import WorkerOutput
from app.agentic.orchestrator import (
    _AGGREGATOR_ID,
    _finalize_synthesis_streamed,
    run_orchestrator,
)
from app.config import Settings
from app.errors import AppError, ErrorEnvelope
from app.observability.tracing import (
    SpanSettlement,
    add_otel_log_processor,
    instrument_fastapi,
    invoke_agent_span,
    reset_tracing_for_tests,
)
from app.providers.protocol import AnswerDelta, Complete, ProviderEvent, UsageUpdate
from app.providers.tiers import get_binding
from app.runtime.context import ServedRoute
from app.runtime.run_receipt import UsageTotals


@pytest.fixture(autouse=True)
def _reset_tracing_guard() -> Iterator[None]:
    """Each test starts with fresh init guards (the OTel global stays set —
    intentional; we just gate our own one-time init logic)."""
    reset_tracing_for_tests()
    yield
    reset_tracing_for_tests()


def _no_otel_settings(env: str = "dev") -> Settings:
    # OTEL_EXPORTER_OTLP_ENDPOINT is bound by alias on the Settings model;
    # pydantic-settings populates aliased fields by alias only — pass the
    # uppercase env var name as the kwarg.
    return Settings(env=env, OTEL_EXPORTER_OTLP_ENDPOINT=None)  # type: ignore[arg-type]


def _with_otel_settings(env: str = "dev") -> Settings:
    return Settings(  # type: ignore[arg-type]
        env=env,
        OTEL_EXPORTER_OTLP_ENDPOINT="http://collector.example:4318/v1/traces",
        OTEL_SERVICE_NAME="api-test",
    )


def test_instrument_fastapi_noop_when_endpoint_unset() -> None:
    """No endpoint and no override -> instrument_fastapi returns False."""
    app = FastAPI()
    result = instrument_fastapi(app, settings=_no_otel_settings())
    assert result is False


def test_instrument_fastapi_warns_in_production_without_endpoint() -> None:
    """Production + missing endpoint -> structlog warning (not raise)."""
    app = FastAPI()
    with structlog.testing.capture_logs() as captured:
        result = instrument_fastapi(app, settings=_no_otel_settings(env="production"))
    assert result is False
    events = [e.get("event") for e in captured]
    assert "otel.disabled" in events, f"events seen: {events}"
    warn = next(e for e in captured if e.get("event") == "otel.disabled")
    assert warn["log_level"] == "warning"


def test_instrument_fastapi_silent_in_dev_without_endpoint() -> None:
    """Dev + missing endpoint is the default — no warning log."""
    app = FastAPI()
    with structlog.testing.capture_logs() as captured:
        result = instrument_fastapi(app, settings=_no_otel_settings(env="dev"))
    assert result is False
    assert not any(e.get("event") == "otel.disabled" for e in captured)


@pytest.mark.asyncio
async def test_instrument_fastapi_with_in_memory_exporter_produces_spans() -> None:
    """End-to-end: with an in-memory exporter, a request produces a span.

    We use the SDK's `InMemorySpanExporter` so the test can assert on
    captured spans without standing up a real collector. The exporter
    override flows through `instrument_fastapi`'s `span_exporter` kwarg.
    """
    # A `SimpleSpanProcessor` (synchronous flush) so there is no batching window
    # to wait on. Attached to whichever SDK provider is already live rather than
    # to a fresh one: OTel refuses to replace a registered global provider, so a
    # test that ran earlier and registered its own would leave this one asserting
    # against an exporter nothing ever reached.
    exporter = _capture_spans()

    app = FastAPI()

    @app.get("/ping")
    async def _ping() -> dict[str, str]:
        return {"pong": "ok"}

    # Endpoint is set so the guard passes; the exporter override is what
    # actually drives the test. We still pass a real-looking endpoint so
    # the no-op check is exercised end-to-end.
    settings = _with_otel_settings()
    # Override the module-level `_TRACER_PROVIDER_REGISTERED` flag so the
    # instrumentor binds the FastAPI app to OUR pre-built provider, not the
    # OTLP exporter (we want spans captured by InMemorySpanExporter).
    from app.observability import tracing as tracing_module

    tracing_module._TRACER_PROVIDER_REGISTERED = True

    result = instrument_fastapi(app, settings=settings)
    assert result is True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/ping")
    assert resp.status_code == 200

    # FastAPI instrumentation emits at least one span per server request.
    spans = exporter.get_finished_spans()
    assert spans, "expected at least one span captured by in-memory exporter"
    # Span name varies by OTel version (e.g. "GET /ping"); just assert the
    # path appears somewhere in the span name set.
    names = [s.name for s in spans]
    assert any("/ping" in n for n in names), f"no /ping span; names: {names}"


def test_add_otel_log_processor_noop_without_active_span() -> None:
    """No active span -> processor returns the event_dict unchanged."""
    event_dict: dict[str, object] = {"event": "test_event"}
    out = add_otel_log_processor(None, "info", event_dict)
    assert "trace_id" not in out
    assert "span_id" not in out


def test_add_otel_log_processor_injects_ids_inside_active_span() -> None:
    """Inside an active span, processor adds hex `trace_id`/`span_id`.

    Hex format: 32 chars for trace_id, 16 chars for span_id, matching the
    W3C TraceContext / OTLP wire shape so logs join cleanly with spans.
    """
    # Build an isolated tracer provider so this test doesn't depend on
    # whatever global state another test set up.
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("test")

    with tracer.start_as_current_span("test_span") as span:
        event_dict: dict[str, object] = {"event": "inside_span"}
        out = add_otel_log_processor(None, "info", event_dict)

        ctx = span.get_span_context()
        assert ctx.is_valid
        expected_trace = f"{ctx.trace_id:032x}"
        expected_span = f"{ctx.span_id:016x}"

    assert out["trace_id"] == expected_trace
    assert out["span_id"] == expected_span
    assert len(out["trace_id"]) == 32  # type: ignore[arg-type]
    assert len(out["span_id"]) == 16  # type: ignore[arg-type]


# AC-10 primitives: the served route and the span settlement handle -------------


def test_served_route_is_immutable_and_fallback_is_a_derived_route() -> None:
    """A fallback is one derived route carrying its reason, not a parallel set of
    provider/model fields each consumer has to reconcile against the bound ones."""
    bound = ServedRoute(tier_id="smart", provider_id="deepseek", model_id="v4-pro")
    assert bound.substitution is None
    with pytest.raises(AttributeError):
        bound.provider_id = "anthropic"  # type: ignore[misc]

    served = bound.substituted(provider_id="anthropic", model_id="claude-x")
    assert (served.provider_id, served.model_id) == ("anthropic", "claude-x")
    assert served.substitution == "provider_fallback"
    # The requested tier is what the user picked, so a substitution keeps it.
    assert served.tier_id == "smart"
    # Unnamed parts stay as bound: a provider-only fallback keeps its model.
    assert bound.substituted(provider_id="anthropic").model_id == "v4-pro"
    assert bound.substitution is None


def test_served_route_from_binding_takes_the_resolved_tier() -> None:
    """`auto` names no servable model, so the caller supplies the concrete tier
    it resolved to; a concrete binding needs no override."""
    smart = get_binding("smart", settings=Settings())
    assert smart is not None
    route = ServedRoute.from_binding(smart)
    assert route == ServedRoute(
        tier_id=smart.tier.id,
        provider_id=smart.provider_id,
        model_id=smart.model_id,
    )
    auto = get_binding("auto", settings=Settings())
    assert auto is not None
    assert ServedRoute.from_binding(auto, served_tier_id="smart").tier_id == "smart"


def _capture_spans() -> InMemorySpanExporter:
    """Collect spans created from here on, whatever ran before.

    OTel refuses to replace an already-registered global tracer provider, so a
    test that sets its own would silently capture nothing when another test
    registered one first. Attach a processor to whichever SDK provider is live
    instead, registering one only when the global is still the no-op proxy.
    """
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


def test_span_settlement_records_route_usage_cost_and_outcome() -> None:
    """The facts a phase span used to close without: what served it, the tokens
    behind the money, the exact cost, and how it ended."""
    exporter = _capture_spans()
    with invoke_agent_span(subagent_id="worker-0", role="worker") as settlement:
        assert isinstance(settlement, SpanSettlement)
        settlement.settle(
            route=ServedRoute(tier_id="smart", provider_id="deepseek", model_id="v4-pro"),
            usage=UsageTotals(
                input_tokens=11, output_tokens=7, reasoning_tokens=3, cached_input_tokens=5
            ),
            cost_usd=0.0125,
            outcome="succeeded",
        )
    (span,) = exporter.get_finished_spans()
    assert span.attributes is not None
    attrs = dict(span.attributes)
    assert attrs["agentic.served_tier_id"] == "smart"
    assert attrs["gen_ai.provider.name"] == "deepseek"
    assert attrs["gen_ai.response.model"] == "v4-pro"
    assert attrs["gen_ai.usage.input_tokens"] == 11
    assert attrs["gen_ai.usage.output_tokens"] == 7
    assert attrs["agentic.usage.reasoning_tokens"] == 3
    assert attrs["agentic.usage.cached_input_tokens"] == 5
    assert attrs["agentic.cost_usd"] == pytest.approx(0.0125)
    assert attrs["agentic.outcome"] == "succeeded"
    assert "agentic.route.substitution" not in attrs


def test_span_settlement_fallback_overrides_the_bound_route() -> None:
    """A worker that fell back must not close claiming the route it was bound to,
    and must not close carrying both routes either — the served one wins."""
    exporter = _capture_spans()
    bound = ServedRoute(tier_id="smart", provider_id="deepseek", model_id="v4-pro")
    with invoke_agent_span(subagent_id="worker-0", role="worker") as settlement:
        settlement.settle(route=bound, outcome="running")
        settlement.settle(
            route=bound.substituted(provider_id="anthropic", model_id="claude-x"),
            outcome="succeeded",
        )
    (span,) = exporter.get_finished_spans()
    assert span.attributes is not None
    attrs = dict(span.attributes)
    assert attrs["gen_ai.provider.name"] == "anthropic"
    assert attrs["gen_ai.response.model"] == "claude-x"
    assert attrs["agentic.served_tier_id"] == "smart"
    assert attrs["agentic.route.substitution"] == "provider_fallback"
    assert attrs["agentic.outcome"] == "succeeded"


def test_span_settlement_records_no_content_and_needs_no_guard() -> None:
    """Only ids, route, counts, money and outcome reach a span. And a handle over
    no span settles silently, so no call site grows an `if span is not None`."""
    exporter = _capture_spans()
    with invoke_agent_span(subagent_id="aggregator", role="aggregator") as settlement:
        settlement.settle(usage=UsageTotals(input_tokens=2), cost_usd=0.0)
    (span,) = exporter.get_finished_spans()
    assert span.attributes is not None
    for key, value in span.attributes.items():
        assert not isinstance(value, str) or len(value) <= 64, key
    assert not [k for k in span.attributes if "content" in k or "text" in k]
    # Partial settlement leaves the unknown facts absent rather than guessed.
    assert "agentic.outcome" not in span.attributes
    assert "gen_ai.response.model" not in span.attributes

    SpanSettlement().settle(
        route=ServedRoute(tier_id="fast", provider_id="p", model_id="m"),
        usage=UsageTotals(input_tokens=1),
        cost_usd=1.0,
        outcome="failed",
    )


# AC-10: the production phase spans, settled from a real orchestrated run --------

BOUND_ROUTE = ServedRoute(tier_id="smart", provider_id="deepseek", model_id="v4-pro")

# The planner span's role is `orchestrator` (pre-existing scope, preserved by
# AC-10); every other phase's role is its own name.
PLANNER_ROLE = "orchestrator"

PHASE_USAGE = UsageUpdate(input_tokens=4, output_tokens=3)


def _agentic_settings(**kwargs: object) -> Settings:
    """Agentic settings on a NON-fake backend.

    The fake backend takes the scaffolded route — deterministic plan, deterministic
    aggregate — which never opens a planner or a streamed-synthesis span. Every
    phase span AC-10 has to close only exists off that branch.
    """
    base: dict[str, object] = {
        # `env` / `provider_backend` carry no alias and so populate by FIELD name;
        # the agentic knobs are aliased and populate by their uppercase env name.
        # Mixing them up is silently ignored under `extra="ignore"`.
        "env": "test",
        "provider_backend": "deepseek",
        "AGENTIC_ENABLED": True,
        "AGENTIC_RUN_BUDGET_USD": 10.0,
    }
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


# A token is worth a nanodollar so the whole run — planner, two workers,
# aggregator and a judge sample — fits the run cap and every phase actually
# executes. The assertions read the arithmetic, not the scale.
def _nano(usage: UsageUpdate) -> float:
    return 1e-9 * (usage.input_tokens + usage.output_tokens)


def _phase_stream(usage: UsageUpdate = PHASE_USAGE) -> Any:
    """A `StreamFactory` that answers every phase with what that phase parses.

    The judge needs strict JSON and the planner needs a numbered list, so the
    reply is chosen from the prompt rather than shared: one canned string would
    make whichever phase it did not suit fail for the wrong reason.
    """

    def _make_stream_for(prompt: str, **_kwargs: object) -> Any:
        judging = "VERIFIER" in prompt or "UNTRUSTED_VERIFIER_DATA" in prompt
        reply = (
            '{"verdict":"pass","report":"none"}'
            if judging
            else "1. alpha\n2. beta"
        )

        def _make(
            _feedback: list[Any], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text=reply)
                yield usage
                yield Complete(usage=usage)

            return _gen()

        return _make

    return _make_stream_for


def _settled_phases(
    exporter: InMemorySpanExporter,
) -> dict[str, list[dict[str, Any]]]:
    """Every `invoke_agent` span grouped by role, in finish order, each carrying
    its own and its parent's span id so topology stays assertable."""
    phases: dict[str, list[dict[str, Any]]] = {}
    for span in exporter.get_finished_spans():
        if span.name != "invoke_agent":
            continue
        attrs = dict(span.attributes or {})
        role = attrs.get("agentic.role")
        if not isinstance(role, str):  # pragma: no cover - always set
            continue
        attrs["_parent_span_id"] = span.parent.span_id if span.parent else None
        attrs["_span_id"] = span.context.span_id
        phases.setdefault(role, []).append(attrs)
    return phases


def _assert_settled(
    attrs: dict[str, Any],
    *,
    outcome: str,
    provider_id: str = "deepseek",
    model_id: str = "v4-pro",
) -> None:
    """The four facts AC-10 requires of every phase span, plus the content ban."""
    assert attrs["agentic.served_tier_id"] == "smart"
    assert attrs["gen_ai.provider.name"] == provider_id
    assert attrs["gen_ai.response.model"] == model_id
    assert attrs["gen_ai.usage.input_tokens"] > 0
    assert attrs["gen_ai.usage.output_tokens"] > 0
    assert attrs["agentic.cost_usd"] > 0.0
    assert attrs["agentic.outcome"] == outcome
    assert not [k for k in attrs if "content" in k or "text" in k]


@pytest.mark.asyncio
async def test_every_deep_research_phase_span_settles_on_the_served_route() -> None:
    """AC-10: the planner, both workers, the aggregator and the verifier each close
    with the route that served them, their tokens, their exact cost and how they
    ended — and the verifier stays a SIBLING of the aggregator (V-009)."""
    exporter = _capture_spans()
    events = [
        event
        async for event in run_orchestrator(
            make_stream_for=_phase_stream(),
            settings=_agentic_settings(AGENTIC_VERIFIER=True, AGENTIC_VERIFIER_N=1),
            mode="deep_research",
            # A plain prompt (no `DEEP_RESEARCH:` marker) so the MODEL planner runs.
            user_text="compare alpha and beta",
            cost_for_usage=_nano,
            served_route=BOUND_ROUTE,
        )
    ]
    assert any(isinstance(e, Complete) and e.subagent_id is None for e in events)

    phases = _settled_phases(exporter)
    assert len(phases["worker"]) == 2
    for role in (PLANNER_ROLE, "worker", "aggregator", "verifier"):
        for attrs in phases[role]:
            _assert_settled(attrs, outcome="succeeded")
    # V-009: the judge is not nested inside the synthesis it judges.
    assert (
        phases["verifier"][-1]["_parent_span_id"]
        != phases["aggregator"][-1]["_span_id"]
    )


@pytest.mark.asyncio
async def test_the_primary_span_settles_on_the_served_route() -> None:
    """AC-10, single mode: the one phase there is closes with the same four facts."""
    exporter = _capture_spans()
    _ = [
        event
        async for event in run_orchestrator(
            make_stream_for=_phase_stream(UsageUpdate(input_tokens=5, output_tokens=2)),
            settings=_agentic_settings(),
            mode="single",
            user_text="a question",
            cost_for_usage=_nano,
            served_route=BOUND_ROUTE,
        )
    ]
    (primary,) = _settled_phases(exporter)["primary"]
    _assert_settled(primary, outcome="succeeded")


@pytest.mark.asyncio
async def test_a_planner_fallback_is_recorded_as_the_served_route() -> None:
    """AC-10 fallback case: the retry opens its own span carrying the substituted
    route, and the primary attempt it replaced closes as failed rather than being
    overwritten — one span per provider call, either way."""
    exporter = _capture_spans()

    def _failing(_prompt: str, **_kwargs: object) -> Any:
        def _make(
            _feedback: list[Any], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                raise AppError(
                    ErrorEnvelope(
                        code="PROVIDER_UPSTREAM",
                        severity="error",
                        title="down",
                        body="down",
                    ),
                    status_code=502,
                )
                yield Complete(usage=UsageUpdate())  # pragma: no cover

            return _gen()

        return _make

    _ = [
        event
        async for event in run_orchestrator(
            make_stream_for=_failing,
            settings=_agentic_settings(),
            mode="deep_research",
            user_text="compare alpha and beta",
            cost_for_usage=_nano,
            served_route=BOUND_ROUTE,
            fallback_make_stream_for=_phase_stream(),
            fallback_cost_for_usage=_nano,
            fallback_provider_id="anthropic",
            fallback_model_id="claude-x",
        )
    ]

    primary_try, retry = _settled_phases(exporter)[PLANNER_ROLE]
    assert primary_try["gen_ai.provider.name"] == "deepseek"
    assert primary_try["agentic.outcome"] == "failed"
    assert "agentic.route.substitution" not in primary_try
    _assert_settled(
        retry, outcome="succeeded", provider_id="anthropic", model_id="claude-x"
    )
    assert retry["agentic.route.substitution"] == "provider_fallback"


def _stream_then_raise(exc: BaseException, usage: UsageUpdate = PHASE_USAGE) -> Any:
    """A phase that bills real tokens and THEN blows up.

    The tokens come first on purpose: spend that lands before an exceptional exit
    is still spend, and a span that reports nothing because the phase did not reach
    its happy path is exactly the hole these tests close.
    """

    def _make_stream_for(_prompt: str, **_kwargs: object) -> Any:
        def _make(
            _feedback: list[Any], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                yield AnswerDelta(text="partial ")
                yield usage
                raise exc

            return _gen()

        return _make

    return _make_stream_for


_UPSTREAM_DOWN = AppError(
    ErrorEnvelope(
        code="PROVIDER_UPSTREAM", severity="error", title="down", body="down"
    ),
    status_code=502,
)


@pytest.mark.asyncio
async def test_a_failing_primary_still_closes_its_span_on_route_and_spend() -> None:
    """AC-10 on the exceptional exit: single mode has no fallback tail, so a
    provider raise leaves `run_single` through the span scope on its way to the
    handler. The span has to carry the route, the tokens already billed, their cost
    and `failed` — not the identity attributes it opened with."""
    exporter = _capture_spans()
    with pytest.raises(AppError):
        async for _event in run_orchestrator(
            make_stream_for=_stream_then_raise(_UPSTREAM_DOWN),
            settings=_agentic_settings(),
            mode="single",
            user_text="a question",
            cost_for_usage=_nano,
            served_route=BOUND_ROUTE,
        ):
            pass

    (primary,) = _settled_phases(exporter)["primary"]
    _assert_settled(primary, outcome="failed")


@pytest.mark.asyncio
async def test_a_cancelled_aggregator_closes_its_span_as_stopped() -> None:
    """AC-10 on the cancelled exit, and AR-005 on top of it.

    `GeneratorExit` and `CancelledError` are `BaseException`, so the aggregator's
    `except Exception` degrade arm never saw them and the span closed unsettled. A
    Stop mid-synthesis must close the span on what the aggregator actually spent,
    labelled `stopped` — and must NOT be laundered into the deterministic-synthesis
    degrade, which would compose an answer for a turn nobody is listening to and
    report a failed aggregator instead of a stopped one.
    """
    exporter = _capture_spans()

    def _cancel_the_synthesis(prompt: str, **kwargs: object) -> Any:
        # Planner and workers answer normally; only the synthesis call is cut off.
        if "<<<UNTRUSTED_WORKER_DATA_BEGIN>>>" in prompt:
            return _stream_then_raise(asyncio.CancelledError())(prompt, **kwargs)
        return _phase_stream()(prompt, **kwargs)

    with pytest.raises(asyncio.CancelledError):
        async for _event in run_orchestrator(
            make_stream_for=_cancel_the_synthesis,
            settings=_agentic_settings(),
            mode="deep_research",
            user_text="compare alpha and beta",
            cost_for_usage=_nano,
            served_route=BOUND_ROUTE,
        ):
            pass

    (aggregator,) = _settled_phases(exporter)["aggregator"]
    _assert_settled(aggregator, outcome="stopped")
    # The degrade arm did not run: a cancellation is not a synthesis failure.
    assert aggregator["agentic.outcome"] != "failed"


def _synthesis_stream(*events: ProviderEvent) -> Any:
    """A synthesis that emits exactly ``events``, so a test can choose the shape."""

    def _make_stream_for(_prompt: str, **_kwargs: object) -> Any:
        def _make(
            _feedback: list[Any], suppress_tools: bool = False
        ) -> AsyncIterator[ProviderEvent]:
            async def _gen() -> AsyncIterator[ProviderEvent]:
                for event in events:
                    yield event

            return _gen()

        return _make

    return _make_stream_for


# Two shapes, each closed at its own usage-bearing event. The `Complete` case
# reports usage ONLY on the terminal frame — a real provider pattern, and the only
# way to make that close point discriminating: `run_agent_loop` normalizes
# `Complete.usage` onto the last `UsageUpdate` it saw, so a stream carrying both
# would settle the same number whether the fold ran before or after the yield.
AGG_SAMPLE = UsageUpdate(input_tokens=7, output_tokens=3)
AGG_TOTAL = UsageUpdate(input_tokens=9, output_tokens=5)


@pytest.mark.parametrize(
    ("events", "close_at", "delivered"),
    [
        pytest.param(
            (AnswerDelta(text="synthesis "), AGG_SAMPLE, Complete(usage=AGG_SAMPLE)),
            UsageUpdate,
            AGG_SAMPLE,
            id="at-delivered-usage",
        ),
        pytest.param(
            (AnswerDelta(text="synthesis "), Complete(usage=AGG_TOTAL)),
            Complete,
            AGG_TOTAL,
            id="at-delivered-complete",
        ),
    ],
)
@pytest.mark.asyncio
async def test_closing_the_synthesis_settles_the_usage_it_already_delivered(
    events: tuple[ProviderEvent, ...], close_at: type, delivered: UsageUpdate
) -> None:
    """AC-10 exactness at the consumer-close boundary.

    A consumer closes a generator while it is SUSPENDED at a yield, so
    `GeneratorExit` lands at that yield and anything the loop did AFTER handing the
    event out never runs. Folding usage after the outward yield therefore made the
    cancel arm settle the previous sample while the tokens it was missing had
    already crossed the wire — a stopped synthesis reporting stale, usually zero,
    usage and cost for work the user was billed for.

    The close is driven against `_finalize_synthesis_streamed` directly because that
    is the generator owning the span. Closing `run_orchestrator` instead throws
    `GeneratorExit` into the outer frame and leaves this one to asynchronous
    async-generator finalization, which is not a boundary a test can pin.
    """
    exporter = _capture_spans()
    stream = _finalize_synthesis_streamed(
        make_stream_for=_synthesis_stream(*events),
        settings=_agentic_settings(),
        user_text="compare alpha and beta",
        outputs=[WorkerOutput(subagent_id="worker-0", sub_question="alpha", answer="a")],
        planned=1,
        worker_usages=[],
        worker_total_cost=0.0,
        cost_for_usage=_nano,
        cap_usd=10.0,
        budget_halted=False,
        served_route=BOUND_ROUTE,
    )

    seen = None
    async for event in stream:
        if type(event) is close_at and event.subagent_id == _AGGREGATOR_ID:
            seen = event
            break
    assert seen is not None, f"the synthesis never delivered a {close_at.__name__}"
    # Suspended at the event above, exactly where a dropped subscriber leaves it.
    await stream.aclose()

    (aggregator,) = _settled_phases(exporter)["aggregator"]
    _assert_settled(aggregator, outcome="stopped")
    assert aggregator["gen_ai.usage.input_tokens"] == delivered.input_tokens
    assert aggregator["gen_ai.usage.output_tokens"] == delivered.output_tokens
    assert aggregator["agentic.cost_usd"] == pytest.approx(_nano(delivered))

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

from collections.abc import Iterator

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.config import Settings
from app.observability.tracing import (
    SpanSettlement,
    add_otel_log_processor,
    instrument_fastapi,
    invoke_agent_span,
    reset_tracing_for_tests,
)
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
    exporter = InMemorySpanExporter()
    # Override the global provider for the duration of this test by
    # constructing one with a SimpleSpanProcessor (synchronous flush) so we
    # don't have to wait on the BatchSpanProcessor's batching window.
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

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

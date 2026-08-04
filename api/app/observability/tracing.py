"""OpenTelemetry tracing for FastAPI + SQLAlchemy.

`instrument_fastapi(app)` is called from `create_app()` AFTER the FastAPI
instance exists. If `OTEL_EXPORTER_OTLP_ENDPOINT` is unset, this function
returns immediately — no tracer provider is registered, no instrumentation
is wired, no background batcher is started. Production logs a warning at
boot when the endpoint is unset; we never raise.

When the endpoint IS set:

1. Build a `TracerProvider` with a `service.name` resource attribute.
2. Attach an OTLP/HTTP span exporter (pure Python; no native gRPC compile).
3. Register the provider globally so spans from any instrumented library
   funnel into the same exporter.
4. Instrument the FastAPI app (server spans per request) and the
   SQLAlchemy engine (DB spans). Both use the global tracer provider.

The exporter is HTTP/protobuf because it's pure-Python and runs in any
environment we'd care about (Fly's container, local dev). gRPC would buy
us nothing here and would force a native build step in the Dockerfile.

Test mode: `instrument_fastapi(..., span_exporter=...)` accepts an explicit
span exporter override so tests can swap in an `InMemorySpanExporter` and
assert on captured spans without standing up a collector.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog
from structlog.typing import EventDict, WrappedLogger

from app.config import Settings, get_settings
from app.runtime.loop_state import StopReason, counted_event_for, outcome_for

if TYPE_CHECKING:
    from fastapi import FastAPI
    from opentelemetry.sdk.trace.export import SpanExporter

    from app.runtime.context import ServedRoute
    from app.runtime.run_receipt import UsageTotals

_log = structlog.get_logger("observability.tracing")

# Module-level guards so repeated `create_app()` calls during tests don't
# re-register the global tracer provider or re-instrument the same engine
# (the OTel instrumentors warn loudly when re-instrumenting). FastAPI app
# instrumentation is keyed by the app instance, so multiple apps can be
# instrumented in one process without contention.
_TRACER_PROVIDER_REGISTERED = False
_SQLALCHEMY_INSTRUMENTED = False


def instrument_fastapi(
    app: FastAPI,
    *,
    settings: Settings | None = None,
    span_exporter: SpanExporter | None = None,
) -> bool:
    """Wire OTel tracing onto a FastAPI app. Return True iff tracing is on.

    No-op (returns False) when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset AND
    no explicit `span_exporter` is provided. Tests pass `span_exporter` to
    force tracing on with an in-memory exporter regardless of env.

    Production logs a warning at boot when the endpoint is unset so the
    absence is visible in the deploy log; we never raise.
    """
    if settings is None:
        settings = get_settings()

    endpoint = (settings.otel_exporter_otlp_endpoint or "").strip()
    if not endpoint and span_exporter is None:
        if settings.env == "production":
            _log.warning(
                "otel.disabled",
                reason="OTEL_EXPORTER_OTLP_ENDPOINT unset; traces will not ship",
            )
        return False

    # All OTel imports are lazy so apps that never call this function don't
    # pay the (small) import cost.
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    global _TRACER_PROVIDER_REGISTERED, _SQLALCHEMY_INSTRUMENTED

    if not _TRACER_PROVIDER_REGISTERED:
        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)

        exporter: SpanExporter
        if span_exporter is not None:
            exporter = span_exporter
        else:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=endpoint)

        provider.add_span_processor(BatchSpanProcessor(exporter))
        # `set_tracer_provider` is idempotent at the OTel level — it logs a
        # warning if a provider was already set — but our `_TRACER_PROVIDER_
        # REGISTERED` guard above keeps the noise out of test runs.
        trace.set_tracer_provider(provider)
        _TRACER_PROVIDER_REGISTERED = True
        _log.info(
            "otel.tracer_provider.registered",
            service_name=settings.otel_service_name,
            endpoint=endpoint or "(in-memory)",
        )

    # FastAPI app instrumentation: per-app, idempotent (the instrumentor
    # tracks instrumented apps internally).
    FastAPIInstrumentor.instrument_app(app)

    # SQLAlchemy: process-wide via the global engine. Guarded so repeated
    # app builds don't re-instrument the same engine.
    if not _SQLALCHEMY_INSTRUMENTED:
        # Imported here (not at top) because `app.db.session` constructs the
        # engine lazily and we don't want to force engine construction at
        # module import time.
        from app.db.session import get_engine

        async_engine = get_engine()
        # `instrument()` accepts the underlying sync `Engine`; the async
        # wrapper exposes it via `.sync_engine`. The instrumentor wraps the
        # Engine's event hooks, so async sessions emit DB spans too.
        SQLAlchemyInstrumentor().instrument(engine=async_engine.sync_engine)
        _SQLALCHEMY_INSTRUMENTED = True
        _log.info("otel.sqlalchemy.instrumented")

    return True


def add_otel_log_processor(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """structlog processor: inject `trace_id`/`span_id` from the active span.

    structlog processor signature is `(logger, method_name, event_dict)`;
    the first two are unused here. No-op when no span is active or the OTel
    API isn't loaded — the function looks for a current span on every log
    call but only adds keys when the span context is valid (non-zero trace
    id, per the OTel "no-op tracer" convention).

    Hex-encoded so values stay grep-able in JSON log streams and match the
    OTLP wire format. (16 hex chars for span id, 32 for trace id.)
    """
    try:
        # Import here so the processor is safe to chain even in test runs
        # that haven't initialized OTel — the import is cheap after the
        # first call (Python caches it).
        from opentelemetry import trace
    except ImportError:  # pragma: no cover - defensive
        return event_dict

    span = trace.get_current_span()
    ctx = span.get_span_context()
    # The OTel "no-op" tracer returns an INVALID context (trace_id == 0).
    # Skip in that case so quiet logs stay quiet.
    if not ctx.is_valid:
        return event_dict

    # Format per the W3C TraceContext spec / OTLP wire shape.
    event_dict["trace_id"] = f"{ctx.trace_id:032x}"
    event_dict["span_id"] = f"{ctx.span_id:016x}"
    return event_dict


# Tracer name for the agentic span tree. A single named tracer so a run's
# `invoke_workflow` / `invoke_agent` / `execute_tool` spans group under one
# instrumentation scope.
_AGENTIC_TRACER = "app.agentic"

# Which revision of OpenTelemetry's semantic conventions the attribute names on
# these spans target. The GenAI conventions are Development status
# (`docs/research/2026-08-03/agent-architecture-state-of-the-art.md` §12.3: "pin
# a schema revision and expect migration"), so the pin rides on the workflow root
# as an attribute: a consumer reading a trace can tell which revision produced
# the names it is reading, and moving to a newer revision is a deliberate edit
# here — with its test — rather than a silent change of what a name means.
GENAI_SEMCONV_REVISION = "1.41.1"
GENAI_SEMCONV_SCHEMA_URL = f"https://opentelemetry.io/schemas/{GENAI_SEMCONV_REVISION}"


def _record_stop_reason(span: Any, stop_reason: StopReason) -> None:
    """Write the stop vocabulary onto one span, in one place.

    A reason never lands without the unit it counted and the outcome it resolves
    to (§3.1: "every bound must name its counted event"), so no trace consumer
    has to re-derive either mapping from a bare label.
    """
    span.set_attribute("agentic.stop_reason", stop_reason)
    span.set_attribute("agentic.counted_event", counted_event_for(stop_reason))
    span.set_attribute("agentic.run_outcome", outcome_for(stop_reason))


@dataclass(frozen=True, slots=True)
class SpanHandle:
    """One span — or nothing at all — plus the question every caller asks of it.

    Every handle in this module tolerates `span is None` (the shape when
    OpenTelemetry isn't importable) so no call site guards a settle call, and
    every one of them needs to know whether recording is on. What a handle
    RECORDS differs by what the span is: a phase closes with a route and a spend
    (`SpanSettlement`), a run root closes with a fan-out and a stop reason
    (`WorkflowSettlement`). Those are different vocabularies, so they are
    siblings here rather than one inheriting the other's method.
    """

    span: Any | None = None

    @property
    def records(self) -> bool:
        """Whether anything settled here will be kept.

        False over no span and over a non-recording one, so a caller can skip
        work whose only consumer is the trace — the OTel-off path must not pay
        for tallies nothing will read.
        """
        span = self.span
        return span is not None and bool(span.is_recording())


@dataclass(frozen=True, slots=True)
class SpanSettlement(SpanHandle):
    """Handle for closing one phase span with the facts it ended with.

    A phase span opens knowing only an id, a role and the route the caller
    INTENDED; what a trace needs is what actually served, what it spent, and how
    it ended, none of which is known until the end. `settle()` is where those
    land, and it is deliberately re-callable: a fallback settles the same handle
    again with the route that really served, overriding rather than adding a
    competing set of attributes. Token counts and money are recorded; message,
    prompt and tool content never are.
    """

    def settle(
        self,
        *,
        route: ServedRoute | None = None,
        usage: UsageTotals | None = None,
        cost_usd: float | None = None,
        outcome: str | None = None,
        stop_reason: StopReason | None = None,
    ) -> None:
        """Record any subset of the phase's final route / usage / cost / outcome.

        `stop_reason` is for a phase that ends on its OWN reason — a bound trip,
        a cap kill, a human gate, a provider error — and brings its counted event
        and mapped outcome with it. Phases with no reason of their own (the
        planner, the aggregator, a judge sample) leave it unset rather than
        inheriting the run's.
        """
        span = self.span
        if span is None:
            return
        if route is not None:
            span.set_attribute("agentic.served_tier_id", route.tier_id)
            span.set_attribute("gen_ai.provider.name", route.provider_id)
            span.set_attribute("gen_ai.response.model", route.model_id)
            if route.substitution is not None:
                span.set_attribute("agentic.route.substitution", route.substitution)
        if usage is not None:
            span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
            span.set_attribute("agentic.usage.reasoning_tokens", usage.reasoning_tokens)
            span.set_attribute(
                "agentic.usage.cached_input_tokens", usage.cached_input_tokens
            )
        if cost_usd is not None:
            span.set_attribute("agentic.cost_usd", float(cost_usd))
        if outcome is not None:
            span.set_attribute("agentic.outcome", outcome)
        if stop_reason is not None:
            _record_stop_reason(span, stop_reason)


@dataclass(frozen=True, slots=True)
class WorkflowSettlement(SpanHandle):
    """Handle for closing the RUN ROOT with what the whole run ended up being.

    `settle_run` records the RUN's facts (a phase's belong on a phase span, which
    is `SpanSettlement`'s job) under a re-callable contract. A run learns its plan
    width before it learns its reservation and its spend, so the root is settled
    as each fact arrives and every call records only the subset it was handed — an
    unknown stays absent rather than being guessed at.

    The one fact that is NOT freely re-callable is the stop reason: the run has
    exactly one, and the exit paths that know it are not the last code to touch
    the handle. So the handle remembers whether a reason was ever settled, which
    is what lets an unwinding generator supply `user_stopped` as a floor
    (`settle_interrupted`) without overwriting the real reason a phase already
    recorded.
    """

    # A frozen handle can still remember: the list is only appended to, never
    # rebound, and it exists so a fallback reason cannot outrank a real one.
    _reasons: list[StopReason] = field(default_factory=list)

    @property
    def stop_reason_settled(self) -> bool:
        """Whether any exit has already claimed why this run ended."""
        return bool(self._reasons)

    def settle_interrupted(self) -> None:
        """Record `user_stopped` iff no exit has claimed a reason yet.

        A Stop or a dropped subscriber unwinds the run's generator from the
        OUTSIDE: `GeneratorExit` lands on whichever frame is suspended at a yield
        and the phases below it stay suspended, so no phase ever reaches its own
        cancel arm. Without a floor here the run class an operator most wants to
        separate from a clean finish — `interrupted` — could never appear on a
        root at all. It is a floor and not an override: a run that already tripped,
        breached its cap or parked a gate keeps that reason even though the
        consumer walked away afterwards.
        """
        if self.stop_reason_settled:
            return
        self.settle_run(stop_reason="user_stopped")

    def settle_run(
        self,
        *,
        mode: str | None = None,
        workers_planned: int | None = None,
        workers_completed: int | None = None,
        depth: int | None = None,
        retries: int | None = None,
        stop_reason: StopReason | None = None,
        budget_reserved_usd: float | None = None,
        budget_cap_usd: float | None = None,
        budget_actual_usd: float | None = None,
        usage: UsageTotals | None = None,
    ) -> None:
        """Record any subset of the run's identity, shape, stop and money.

        - `workers_planned` / `workers_completed` are the run's fan-out WIDTH:
          how many sub-questions the plan asked for against how many workers
          actually produced an answer. Reporting only one of them cannot
          distinguish a narrow plan from a wide plan that mostly died.
        - `depth` is the orchestration depth REACHED, on the same scale as
          `AGENTIC_MAX_DEPTH`: 0 for a run with no sub-agents beneath it, 1 for
          the shipped flat worker fan-out. It is observed, not configured, so a
          recursive topology would show up here rather than in a setting.
        - `budget_reserved_usd` against `budget_actual_usd` is the admit-time
          worst-case estimate against what the settled ledger really cost, both
          held against `budget_cap_usd` (the per-run cap composed with the
          caller's headroom). Reserved-only says what was feared; actual-only
          says what was spent; the pair is what shows whether the reservation
          model is calibrated.
        - `usage` carries the token CLASSES separately (input / output /
          reasoning / cached input) because they price differently.

        Content never reaches here: this method takes ids, labels, counts and
        money, and there is no parameter through which a prompt, an answer, a
        plan or a citation could ride.
        """
        if stop_reason is not None:
            # Latched before the span guard so the "was a reason ever claimed"
            # question has the same answer with tracing on and off.
            self._reasons.append(stop_reason)
        span = self.span
        if span is None:
            return
        if mode is not None:
            span.set_attribute("agentic.orchestration_mode", mode)
        if workers_planned is not None:
            span.set_attribute("agentic.workers_planned", int(workers_planned))
        if workers_completed is not None:
            span.set_attribute("agentic.workers_completed", int(workers_completed))
        if depth is not None:
            span.set_attribute("agentic.depth", int(depth))
        if retries is not None:
            span.set_attribute("agentic.retries", int(retries))
        if stop_reason is not None:
            _record_stop_reason(span, stop_reason)
        if budget_reserved_usd is not None:
            span.set_attribute("agentic.budget.reserved_usd", float(budget_reserved_usd))
        if budget_cap_usd is not None:
            span.set_attribute("agentic.budget.cap_usd", float(budget_cap_usd))
        if budget_actual_usd is not None:
            span.set_attribute("agentic.budget.actual_usd", float(budget_actual_usd))
        if usage is not None:
            span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)
            span.set_attribute("agentic.usage.reasoning_tokens", usage.reasoning_tokens)
            span.set_attribute(
                "agentic.usage.cached_input_tokens", usage.cached_input_tokens
            )


@contextlib.contextmanager
def invoke_workflow_span(*, mode: str) -> Iterator[WorkflowSettlement]:
    """Manual OTel span for ONE agentic run — the root of the run's span tree.

    Doc §12.3 asks for the tree `invoke_workflow` -> `invoke_agent` ->
    `execute_tool`. This is that root: opened once per run, it is the parent every
    phase span nests under, so a trace consumer reads one run as one subtree
    instead of a flat list of phases it has to re-group by trace id.

    The root is deliberately NOT made current. A run is an async generator, so its
    scope is held open across `yield`s — and an async generator borrows the
    CONSUMER's context, while the event loop finalizes an abandoned one from a
    different context. `start_as_current_span` there attaches an OTel context token
    in one context and detaches it in another, which raises inside
    `opentelemetry.context.detach` and logs `Failed to detach context` at ERROR on
    every stopped or disconnected turn — with no tracer provider registered at
    all, because even the no-op tracer attaches. So parentage travels by hand: the
    yielded handle carries the span, and `invoke_agent_span(parent=...)` reads it.
    The cost of that choice is that code running between phases has no current
    span, so its logs correlate to the enclosing request span rather than to this
    root; the phase spans stay current within themselves, which is where tool
    spans and per-phase log correlation come from.

    The run's identity is its trace id — no separate id is minted here, because an
    id joined to nothing else is noise in every query that would use it.

    Yields the run's `WorkflowSettlement`, which the caller closes with the
    run's fan-out, depth, retries, stop reason and money.
    """
    try:
        from opentelemetry import trace
    except ImportError:  # pragma: no cover - defensive
        yield WorkflowSettlement()
        return
    tracer = trace.get_tracer(_AGENTIC_TRACER)
    span = tracer.start_span("invoke_workflow")
    settlement = WorkflowSettlement(span)
    if settlement.records:
        span.set_attribute("agentic.semconv.revision", GENAI_SEMCONV_REVISION)
        span.set_attribute("agentic.semconv.schema_url", GENAI_SEMCONV_SCHEMA_URL)
        settlement.settle_run(mode=mode)
    try:
        yield settlement
    except Exception as exc:
        # What `start_as_current_span` would have done, kept by hand so a raising
        # run still has an errored root. `Exception`, not `BaseException`: a Stop
        # or a dropped consumer is not a failure (AR-005), and it is the run's
        # stop reason that says so.
        if settlement.records:
            span.record_exception(exc)
            span.set_status(
                trace.Status(trace.StatusCode.ERROR, f"{type(exc).__name__}: {exc}")
            )
        raise
    finally:
        span.end()


@contextlib.contextmanager
def invoke_agent_span(
    *,
    subagent_id: str,
    role: str,
    label: str | None = None,
    run_id: str | None = None,
    model_id: str | None = None,
    provider_id: str | None = None,
    cost_usd: float | None = None,
    outcome: str | None = None,
    sample_index: int | None = None,
    parent: SpanHandle | None = None,
) -> Iterator[SpanSettlement]:
    """Manual OTel span for one orchestrator subagent (agentic mode, M3).

    One `invoke_agent` span per subagent (primary / worker / aggregator),
    nested under the run's `invoke_workflow` root. Carries ids + role/label and
    optional route/cost/outcome attributes — NEVER message content (matching the
    structured-log discipline). A no-op when OpenTelemetry isn't importable, and
    a non-recording span (negligible cost) when no tracer provider is
    configured, so the flag-off / OTel-off paths are unaffected.

    `parent` is the run root's handle. The root cannot be made current (see
    `invoke_workflow_span`), so a phase that wants to nest under it says so, and a
    phase given no parent nests wherever the current context points — which is how
    the direct unit calls in the tests still work. This span IS made current, so
    the `execute_tool` spans beneath it and the logs written inside it still find
    it implicitly.

    `sample_index` is for a phase that runs the SAME subagent id more than once
    in one run — the N-sample verifier judge with N > 1. Without it those spans are
    indistinguishable, so a consumer cannot tell three samples of one judge from
    one judge traced three times. The index and a suffixed `agentic.sample_id`
    are added; `agentic.subagent_id` deliberately keeps the id the wire and the
    ledger use, so joining a span back to its phase still works. A phase that runs
    once passes nothing: an index over a single sample distinguishes it from
    nothing.

    Yields the phase's `SpanSettlement` so the caller can close it with what
    actually served, spent and happened.
    """
    try:
        from opentelemetry import trace
    except ImportError:  # pragma: no cover - defensive
        yield SpanSettlement()
        return
    tracer = trace.get_tracer(_AGENTIC_TRACER)
    parent_span = None if parent is None else parent.span
    # A parent with an invalid context (the no-op tracer's span) carries no
    # parentage to inherit, so fall back to the current context rather than
    # pinning this span to nothing and re-rooting it.
    parent_context = (
        trace.set_span_in_context(parent_span)
        if parent_span is not None and parent_span.get_span_context().is_valid
        else None
    )
    with tracer.start_as_current_span("invoke_agent", context=parent_context) as span:
        span.set_attribute("agentic.subagent_id", subagent_id)
        span.set_attribute("agentic.role", role)
        if sample_index is not None:
            span.set_attribute("agentic.sample_index", int(sample_index))
            span.set_attribute("agentic.sample_id", f"{subagent_id}#{sample_index}")
        if label is not None:
            span.set_attribute("agentic.label", label)
        if run_id is not None:
            span.set_attribute("agentic.run_id", run_id)
        if model_id is not None:
            span.set_attribute("gen_ai.request.model", model_id)
        if provider_id is not None:
            span.set_attribute("gen_ai.provider.name", provider_id)
        if cost_usd is not None:
            span.set_attribute("agentic.cost_usd", float(cost_usd))
        if outcome is not None:
            span.set_attribute("agentic.outcome", outcome)
        yield SpanSettlement(span)


@contextlib.contextmanager
def execute_tool_span(
    *,
    tool_name: str,
    subagent_id: str | None = None,
) -> Iterator[Any]:
    """Manual OTel span for one tool execution (agentic mode, M3).

    Nested under the owning subagent's `invoke_agent` span. Carries the tool
    name + optional subagent id only — never tool input/output content. Same
    no-op / non-recording semantics as `invoke_agent_span`.
    """
    try:
        from opentelemetry import trace
    except ImportError:  # pragma: no cover - defensive
        yield None
        return
    tracer = trace.get_tracer(_AGENTIC_TRACER)
    with tracer.start_as_current_span("execute_tool") as span:
        span.set_attribute("tool.name", tool_name)
        if subagent_id is not None:
            span.set_attribute("agentic.subagent_id", subagent_id)
        yield span


def reset_tracing_for_tests() -> None:
    """Test-only hook: clear init guards so each test starts fresh.

    Note: the global OTel tracer provider is NOT torn down here — OTel
    intentionally lacks an `unset_tracer_provider` API. Tests that need a
    fresh provider should swap in their own via dependency injection
    (`instrument_fastapi(..., span_exporter=...)`).
    """
    global _TRACER_PROVIDER_REGISTERED, _SQLALCHEMY_INSTRUMENTED
    _TRACER_PROVIDER_REGISTERED = False
    _SQLALCHEMY_INSTRUMENTED = False

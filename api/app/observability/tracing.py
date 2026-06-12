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
from typing import TYPE_CHECKING, Any

import structlog
from structlog.typing import EventDict, WrappedLogger

from app.config import Settings, get_settings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from opentelemetry.sdk.trace.export import SpanExporter

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
# `invoke_agent` / `execute_tool` spans group under one instrumentation scope.
_AGENTIC_TRACER = "app.agentic"


@contextlib.contextmanager
def invoke_agent_span(
    *,
    subagent_id: str,
    role: str,
    label: str | None = None,
) -> Iterator[Any]:
    """Manual OTel span for one orchestrator subagent (agentic mode, M3).

    One `invoke_agent` span per subagent (primary / worker / aggregator),
    nested under the turn's auto-instrumented request span. Carries ids +
    role/label only — NEVER message content (matching the structured-log
    discipline). A no-op when OpenTelemetry isn't importable, and a non-recording
    span (negligible cost) when no tracer provider is configured, so the
    flag-off / OTel-off paths are unaffected.
    """
    try:
        from opentelemetry import trace
    except ImportError:  # pragma: no cover - defensive
        yield None
        return
    tracer = trace.get_tracer(_AGENTIC_TRACER)
    with tracer.start_as_current_span("invoke_agent") as span:
        span.set_attribute("agentic.subagent_id", subagent_id)
        span.set_attribute("agentic.role", role)
        if label is not None:
            span.set_attribute("agentic.label", label)
        yield span


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

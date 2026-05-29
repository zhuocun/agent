"""Observability seam: OTel tracing + Sentry error reporting.

Both subsystems are env-driven and no-op when unset (see `tracing.py` and
`errors.py`). `app/main.py` calls into `init_sentry()` and
`instrument_fastapi()` once per app build; both are idempotent enough that
test apps built repeatedly do not crash the test process.

Why split into two modules:
- `errors.py` (Sentry) initializes at import time of an app and stays out of
  the request hot path. It's purely an exception-shipper.
- `tracing.py` (OTel) owns the tracer provider, the OTLP exporter, and the
  FastAPI / SQLAlchemy instrumentation. Tests can monkeypatch in an
  `InMemorySpanExporter` to assert spans without standing up a collector.
"""

from __future__ import annotations

from app.observability.errors import init_sentry
from app.observability.tracing import (
    add_otel_log_processor,
    instrument_fastapi,
    reset_tracing_for_tests,
)

__all__ = [
    "add_otel_log_processor",
    "init_sentry",
    "instrument_fastapi",
    "reset_tracing_for_tests",
]

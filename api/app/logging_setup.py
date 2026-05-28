"""structlog configuration.

Single entrypoint `configure_logging()`. JSON output, ISO timestamps, level
keys appended to every event. Called at app startup; safe to call multiple
times — `structlog.configure(...)` replaces the global config in place.

Processor chain:
- `merge_contextvars` pulls in `request_id`, `user_id`, etc. bound by the
  request-ID middleware and the auth dependency.
- `add_log_level` adds the `level` key.
- `TimeStamper(fmt="iso")` adds ISO-8601 `timestamp`.
- `format_exc_info` renders exc_info into a string.
- `JSONRenderer` is the final output stage.

Caching note (M4): we deliberately do NOT cache loggers on first use. The
test harness uses `structlog.testing.capture_logs()` to swap the processor
chain in-flight; with caching enabled, module-level `get_logger(...)` calls
hold onto the original config and tests can't observe the events. The
performance cost of building a `BoundLogger` per call is negligible in our
request-rate regime; opt back in if we ever see CPU pressure here.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: int = logging.INFO) -> None:
    """Configure structlog to emit JSON to stderr."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=level,
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=False,
    )

"""Sentry-style error reporting init.

`init_sentry()` is called once from `create_app()`, BEFORE any middleware is
registered. If `SENTRY_DSN` is unset or blank, the function returns immediately
and Sentry stays uninitialized — no background uploader, no exception capture
hook installed. Production warns at boot (logged via structlog) when the DSN
is unset so an operator can spot misconfigurations in the deploy log, but the
service still boots — Sentry is optional.

Traces sample rate is pinned to 0.0 because OTel handles tracing. Sentry's
job here is exception capture only, so we keep its tracing machinery off to
avoid double-instrumenting requests.
"""

from __future__ import annotations

import structlog

from app.config import Settings, get_settings

_log = structlog.get_logger("observability.sentry")

# Module-level flag so we don't reinitialize on repeated `create_app()` calls
# (the test suite builds many apps per process). Sentry's own `init()` is
# idempotent enough to call twice, but the cleaner contract is "init once".
_INITIALIZED = False


def init_sentry(settings: Settings | None = None) -> bool:
    """Initialize Sentry from env. Return True iff init actually ran.

    No-op (returns False) when `SENTRY_DSN` is unset/blank. In production
    we emit a startup warning when Sentry is off so the absence shows up in
    the deploy log; we never raise — observability is optional.

    Returns True only on the first call within a process where DSN is set;
    subsequent calls are no-ops (returns False) so test apps don't reset
    the SDK on each build.
    """
    global _INITIALIZED
    if settings is None:
        settings = get_settings()

    dsn = (settings.sentry_dsn or "").strip()
    if not dsn:
        if settings.env == "production":
            _log.warning(
                "sentry.disabled",
                reason="SENTRY_DSN unset; error reporting will not ship to Sentry",
            )
        return False

    if _INITIALIZED:
        return False

    # Imported lazily so a deployment that ships without sentry-sdk in the
    # virtualenv (unlikely, but) still has a clear ImportError at boot rather
    # than a confusing crash mid-request.
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.env,
        # OTel owns tracing; Sentry is just an exception shipper. Pinning the
        # sample rate to 0 keeps Sentry from double-instrumenting requests.
        traces_sample_rate=0.0,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
        ],
    )
    _INITIALIZED = True
    _log.info("sentry.initialized", env=settings.env)
    return True


def reset_sentry_for_tests() -> None:
    """Test-only hook to reset the init guard so each test starts fresh."""
    global _INITIALIZED
    _INITIALIZED = False

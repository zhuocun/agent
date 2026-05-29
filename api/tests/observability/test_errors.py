"""`init_sentry()` env-driven init behavior.

Acceptance criteria covered:
- Unset/blank DSN -> no-op, no exception, no observable side effect.
- Set DSN -> sentry_sdk.init is invoked exactly once with the env-derived
  config; repeat calls within the same process are no-ops (guarded).
- In production with no DSN, a startup warning is logged via structlog so
  the absence shows up in deploy logs.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import structlog

from app.config import Settings
from app.observability.errors import init_sentry, reset_sentry_for_tests


@pytest.fixture(autouse=True)
def _reset_sentry_guard() -> Iterator[None]:
    """Make sure each test starts with a fresh init guard."""
    reset_sentry_for_tests()
    yield
    reset_sentry_for_tests()


def _no_dsn_settings(env: str = "dev") -> Settings:
    """Settings with no Sentry DSN — covers the dev/prod no-op path.

    `SENTRY_DSN` is bound to the `sentry_dsn` field by alias; pydantic-settings
    populates fields by alias only when an alias is declared, so tests must
    pass the alias name explicitly.
    """
    return Settings(env=env, SENTRY_DSN=None)  # type: ignore[arg-type]


def _with_dsn_settings(env: str = "dev") -> Settings:
    """Settings with a fake DSN — Sentry should attempt init."""
    return Settings(  # type: ignore[arg-type]
        env=env,
        SENTRY_DSN="https://public@sentry.example/1",
    )


def test_init_sentry_noop_when_dsn_unset() -> None:
    """No DSN -> init_sentry returns False and never calls sentry_sdk.init."""
    settings = _no_dsn_settings()
    assert init_sentry(settings) is False


def test_init_sentry_noop_when_dsn_blank() -> None:
    """Whitespace-only DSN is treated the same as unset (no-op)."""
    settings = Settings(env="dev", SENTRY_DSN="   ")  # type: ignore[arg-type]
    assert init_sentry(settings) is False


def test_init_sentry_warns_in_production_without_dsn() -> None:
    """In production, missing DSN -> WARNING log so ops can spot it."""
    settings = _no_dsn_settings(env="production")
    with structlog.testing.capture_logs() as captured:
        result = init_sentry(settings)
    assert result is False
    events = [e.get("event") for e in captured]
    assert "sentry.disabled" in events, f"events seen: {events}"
    warn = next(e for e in captured if e.get("event") == "sentry.disabled")
    assert warn["log_level"] == "warning"


def test_init_sentry_silent_in_dev_without_dsn() -> None:
    """In dev, missing DSN is the default — no warning log."""
    settings = _no_dsn_settings(env="dev")
    with structlog.testing.capture_logs() as captured:
        result = init_sentry(settings)
    assert result is False
    assert not any(e.get("event") == "sentry.disabled" for e in captured)


def test_init_sentry_invokes_sdk_when_dsn_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a DSN, sentry_sdk.init is called exactly once with the env config."""
    settings = _with_dsn_settings(env="dev")
    calls: list[dict[str, Any]] = []

    def fake_init(**kwargs: Any) -> None:
        calls.append(kwargs)

    import sentry_sdk

    monkeypatch.setattr(sentry_sdk, "init", fake_init)
    result = init_sentry(settings)
    assert result is True
    assert len(calls) == 1
    assert calls[0]["dsn"] == "https://public@sentry.example/1"
    assert calls[0]["environment"] == "dev"
    # OTel owns tracing — Sentry's sample rate must be pinned to 0.
    assert calls[0]["traces_sample_rate"] == 0.0
    # FastApiIntegration must be wired so per-endpoint transactions land.
    integrations = calls[0]["integrations"]
    assert any(type(i).__name__ == "FastApiIntegration" for i in integrations)


def test_init_sentry_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeat calls within one process do not re-invoke sentry_sdk.init.

    The test suite builds many FastAPI apps; we don't want each one to
    reinitialize the SDK and stomp on the prior config.
    """
    settings = _with_dsn_settings()
    calls: list[dict[str, Any]] = []
    import sentry_sdk

    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: calls.append(kwargs))
    assert init_sentry(settings) is True
    # Second call: DSN still set, but guard kicks in -> False, no extra init.
    assert init_sentry(settings) is False
    assert len(calls) == 1

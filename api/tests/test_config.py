"""`Settings.assert_prod_safe()` coverage.

Focused on the production-only guardrails: the fake provider backend must not
be reachable in production (see PROVIDER_BACKEND check), but it stays a no-op
under dev / test so the in-process fake remains the default for the rest of
the suite.
"""

from __future__ import annotations

import re

import pytest

from app.config import Settings

# A fresh, non-sentinel 32-byte KEK (base64). The dev sentinel is intentionally
# rejected by `assert_prod_safe()`, so prod-construction tests must override it.
_VALID_KEK_B64 = "TL7rol4lIk2SLzXcfahi78iUOxpFOSxrUpqlA5fmnec="


def _prod_settings(**overrides: object) -> Settings:
    """Build a prod-shaped `Settings` with all the other prod guardrails
    satisfied, so the specific assertion under test is the only one that can
    fire. Overrides win over the prod defaults.
    """
    base: dict[str, object] = {
        "env": "production",
        "session_secret": "prod-session-secret-fixed-and-long-enough",
        # `byok_encryption_kek` and `cors_allowed_origins_raw` carry aliases on
        # the model, so pydantic-settings populates them by alias only — pass
        # them by alias when constructing.
        "BYOK_ENCRYPTION_KEK": _VALID_KEK_B64,
        "cookie_secure": True,
        "cookie_samesite": "none",
        "CORS_ALLOWED_ORIGINS": "https://example.com",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_assert_prod_safe_rejects_fake_provider_in_production() -> None:
    """`PROVIDER_BACKEND=fake` in production must raise with the canonical message."""
    bad = _prod_settings(provider_backend="fake")
    with pytest.raises(
        RuntimeError,
        match=re.escape("PROVIDER_BACKEND must not be 'fake' in production."),
    ):
        bad.assert_prod_safe()


def test_assert_prod_safe_accepts_anthropic_provider_in_production() -> None:
    """Non-fake provider with all other prod guardrails satisfied → no raise."""
    good = _prod_settings(provider_backend="anthropic", anthropic_api_key="real-key")
    good.assert_prod_safe()  # must not raise


def test_assert_prod_safe_no_op_for_fake_in_development() -> None:
    """The fake backend stays valid in dev — assert_prod_safe is a no-op there."""
    dev = Settings(provider_backend="fake", env="dev")
    dev.assert_prod_safe()  # must not raise


def test_assert_prod_safe_rejects_wildcard_cors_in_production() -> None:
    """A credentialed `*` origin must be refused in production."""
    bad = _prod_settings(
        provider_backend="anthropic",
        anthropic_api_key="real-key",
        CORS_ALLOWED_ORIGINS="*",
    )
    with pytest.raises(RuntimeError, match=re.escape("must not contain '*'")):
        bad.assert_prod_safe()


def test_assert_prod_safe_rejects_wildcard_cors_among_others() -> None:
    """A `*` mixed in with real origins is still rejected."""
    bad = _prod_settings(
        provider_backend="anthropic",
        anthropic_api_key="real-key",
        CORS_ALLOWED_ORIGINS="https://example.com,*",
    )
    with pytest.raises(RuntimeError, match=re.escape("must not contain '*'")):
        bad.assert_prod_safe()


def test_assert_prod_safe_rejects_empty_session_secret() -> None:
    """An empty SESSION_SECRET must be refused in production."""
    bad = _prod_settings(
        provider_backend="anthropic",
        anthropic_api_key="real-key",
        session_secret="",
    )
    with pytest.raises(RuntimeError, match=re.escape("SESSION_SECRET")):
        bad.assert_prod_safe()


def test_assert_prod_safe_rejects_short_session_secret() -> None:
    """A <32-char SESSION_SECRET must be refused in production."""
    bad = _prod_settings(
        provider_backend="anthropic",
        anthropic_api_key="real-key",
        session_secret="too-short",
    )
    with pytest.raises(
        RuntimeError, match=re.escape("at least 32 characters")
    ):
        bad.assert_prod_safe()


def test_assert_prod_safe_rejects_anthropic_without_key() -> None:
    """PROVIDER_BACKEND=anthropic with no key must fail fast at boot."""
    bad = _prod_settings(provider_backend="anthropic", anthropic_api_key=None)
    with pytest.raises(
        RuntimeError, match=re.escape("ANTHROPIC_API_KEY required")
    ):
        bad.assert_prod_safe()


def test_assert_prod_safe_accepts_well_formed_prod_env() -> None:
    """A fully-formed prod env (secure cookies, samesite=none, long secret,
    valid KEK, non-wildcard origin, anthropic backend + key) must not raise."""
    good = _prod_settings(
        provider_backend="anthropic",
        anthropic_api_key="real-key",
    )
    good.assert_prod_safe()  # must not raise

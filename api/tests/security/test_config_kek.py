"""`assert_prod_safe()` guardrails for the versioned-KEK registry.

These extend `tests/test_config.py` with the rotation-specific cases. We
build `Settings` instances directly with explicit overrides rather than
going through env vars + `get_settings()` so each test stays isolated
from the rest of the suite's `BYOK_*` defaults.
"""

from __future__ import annotations

import base64
import os
import re

import pytest

from app.config import Settings

# A fresh, non-sentinel 32-byte KEK. Reused across tests because each test
# either varies a different field or builds its own KEK explicitly.
_VALID_KEK_B64 = "TL7rol4lIk2SLzXcfahi78iUOxpFOSxrUpqlA5fmnec="


def _make_kek_b64() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


def test_assert_prod_safe_passes_with_legacy_only_in_dev() -> None:
    """No registry + current_version=0 must be a no-op in dev."""
    s = Settings(env="dev")  # all other defaults
    s.assert_prod_safe()  # must not raise


def test_assert_prod_safe_accepts_v1_with_matching_registry() -> None:
    """Registry contains the current version -> the guardrail is satisfied."""
    k1 = _make_kek_b64()
    s = Settings(
        env="dev",
        BYOK_KEK_VERSIONS=f"1:{k1}",  # type: ignore[arg-type]
        BYOK_CURRENT_KEK_VERSION=1,  # type: ignore[arg-type]
    )
    s.assert_prod_safe()  # must not raise


def test_assert_prod_safe_rejects_v1_with_empty_registry() -> None:
    """`current_version=1` but no entries -> boot must fail loudly."""
    s = Settings(
        env="dev",
        BYOK_KEK_VERSIONS="",  # type: ignore[arg-type]
        BYOK_CURRENT_KEK_VERSION=1,  # type: ignore[arg-type]
    )
    with pytest.raises(
        RuntimeError, match=re.escape("BYOK_CURRENT_KEK_VERSION=1")
    ):
        s.assert_prod_safe()


def test_assert_prod_safe_rejects_v2_when_only_v1_registered() -> None:
    """A `current_version` that misses the registry raises with the version
    number in the message so the operator can see exactly what's missing."""
    k1 = _make_kek_b64()
    s = Settings(
        env="dev",
        BYOK_KEK_VERSIONS=f"1:{k1}",  # type: ignore[arg-type]
        BYOK_CURRENT_KEK_VERSION=2,  # type: ignore[arg-type]
    )
    with pytest.raises(
        RuntimeError, match=re.escape("BYOK_CURRENT_KEK_VERSION=2")
    ):
        s.assert_prod_safe()


def test_assert_prod_safe_rejects_malformed_registry_entry() -> None:
    """Garbage in `BYOK_KEK_VERSIONS` must surface during boot."""
    s = Settings(
        env="dev",
        BYOK_KEK_VERSIONS="not-a-pair",  # type: ignore[arg-type]
        BYOK_CURRENT_KEK_VERSION=0,  # type: ignore[arg-type]
    )
    with pytest.raises(RuntimeError, match=re.escape("version:base64key")):
        s.assert_prod_safe()


def test_assert_prod_safe_rejects_negative_current_version() -> None:
    """`-1` is nonsense; refuse it loudly even outside production."""
    s = Settings(
        env="dev",
        BYOK_CURRENT_KEK_VERSION=-1,  # type: ignore[arg-type]
    )
    with pytest.raises(RuntimeError, match=">= 0"):
        s.assert_prod_safe()


def test_assert_prod_safe_accepts_registry_with_v0_active() -> None:
    """A populated registry with `current_version=0` is valid: writes still
    use the legacy format, but the operator has staged a future KEK to
    rotate to."""
    k1 = _make_kek_b64()
    s = Settings(
        env="dev",
        BYOK_KEK_VERSIONS=f"1:{k1}",  # type: ignore[arg-type]
        BYOK_CURRENT_KEK_VERSION=0,  # type: ignore[arg-type]
    )
    s.assert_prod_safe()  # must not raise


def test_assert_prod_safe_prod_env_with_rotation_active() -> None:
    """End-to-end: production env, prod-safe legacy KEK, v1 rotation active,
    matching registry entry -> no raise."""
    s = Settings(
        env="production",
        session_secret="prod-session-secret-fixed-and-long-enough",
        BYOK_ENCRYPTION_KEK=_VALID_KEK_B64,  # type: ignore[arg-type]
        cookie_secure=True,
        cookie_samesite="none",
        CORS_ALLOWED_ORIGINS="https://example.com",  # type: ignore[arg-type]
        provider_backend="anthropic",
        anthropic_api_key="real-key",
        BYOK_KEK_VERSIONS=f"1:{_make_kek_b64()}",  # type: ignore[arg-type]
        BYOK_CURRENT_KEK_VERSION=1,  # type: ignore[arg-type]
    )
    s.assert_prod_safe()  # must not raise

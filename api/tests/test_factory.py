"""`build_provider()` backend selection tests.

The factory maps `PROVIDER_BACKEND` -> a concrete `Provider`:
  - `fake`      -> `FakeProvider` (default; no key needed)
  - `deepseek`  -> `OpenAIProvider` (canonical/main; OpenAI-compatible; requires
                   `DEEPSEEK_API_KEY` or `OPENAI_API_KEY` fallback)
  - `anthropic` -> `AnthropicProvider` (requires `ANTHROPIC_API_KEY`)
  - `openai`    -> `OpenAIProvider` (requires `OPENAI_API_KEY`)
A selected real backend with its key missing raises `AppError(MISCONFIGURED, 500)`
so ops can grep for it rather than getting a bare FATAL 500.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.errors import AppError
from app.providers.anthropic import AnthropicProvider
from app.providers.factory import build_provider
from app.providers.fake import FakeProvider
from app.providers.openai import OpenAIProvider


def test_build_provider_openai_returns_openai_provider() -> None:
    """openai backend + key -> OpenAIProvider."""
    p = build_provider(Settings(provider_backend="openai", openai_api_key="x"))
    assert isinstance(p, OpenAIProvider)


def test_build_provider_openai_threads_base_url() -> None:
    """The configured base_url is threaded into the OpenAI client/provider."""
    p = build_provider(
        Settings(
            provider_backend="openai",
            openai_api_key="x",
            openai_base_url="https://proxy.example/v1",
        )
    )
    assert isinstance(p, OpenAIProvider)
    # Private but load-bearing: BYOK clients reuse this base_url.
    assert p._base_url == "https://proxy.example/v1"


def test_build_provider_openai_missing_key_raises_misconfigured() -> None:
    """openai backend without OPENAI_API_KEY -> AppError(MISCONFIGURED, 500)."""
    with pytest.raises(AppError) as exc_info:
        build_provider(Settings(provider_backend="openai", openai_api_key=None))
    err = exc_info.value
    assert err.status_code == 500
    assert err.envelope.code == "MISCONFIGURED"
    assert err.envelope.severity == "fatal"
    assert "OPENAI_API_KEY" in err.envelope.body


def test_build_provider_deepseek_uses_openai_client_with_default_base_url() -> None:
    """deepseek backend + key -> OpenAIProvider pointed at api.deepseek.com.

    DeepSeek is OpenAI-compatible; the canonical backend reuses OpenAIProvider
    with the built-in default base_url — no env gymnastics required.
    """
    p = build_provider(Settings(provider_backend="deepseek", deepseek_api_key="ds"))
    assert isinstance(p, OpenAIProvider)
    assert p._base_url == "https://api.deepseek.com"


def test_build_provider_deepseek_falls_back_to_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """deepseek backend resolves the key from OPENAI_API_KEY when DEEPSEEK_API_KEY
    is unset (both are OpenAI-compatible keys)."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    p = build_provider(Settings(provider_backend="deepseek", openai_api_key="oa"))
    assert isinstance(p, OpenAIProvider)


def test_build_provider_deepseek_override_does_not_use_openai_platform_key() -> None:
    """Explicit DeepSeek routing from an OpenAI deployment needs a DeepSeek key."""
    with pytest.raises(AppError) as exc_info:
        build_provider(
            Settings(provider_backend="openai", openai_api_key="oa"),
            provider_id="deepseek",
        )
    err = exc_info.value
    assert err.status_code == 500
    assert err.envelope.code == "MISCONFIGURED"
    assert "DEEPSEEK_API_KEY" in err.envelope.body


def test_build_provider_openai_override_does_not_use_legacy_deepseek_fallback_key() -> None:
    """A DeepSeek legacy fallback key in OPENAI_API_KEY is not an OpenAI key."""
    with pytest.raises(AppError) as exc_info:
        build_provider(
            Settings(provider_backend="deepseek", openai_api_key="legacy-deepseek"),
            provider_id="openai",
        )
    err = exc_info.value
    assert err.status_code == 500
    assert err.envelope.code == "MISCONFIGURED"
    assert "OPENAI_API_KEY" in err.envelope.body


def test_build_provider_deepseek_missing_key_raises_misconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """deepseek backend without any key -> AppError(MISCONFIGURED, 500).

    Clear ambient provider keys so the test holds regardless of the developer's
    environment (pydantic-settings reads env vars even when None is passed).
    """
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(AppError) as exc_info:
        build_provider(Settings(provider_backend="deepseek"))
    err = exc_info.value
    assert err.status_code == 500
    assert err.envelope.code == "MISCONFIGURED"
    assert "DEEPSEEK_API_KEY" in err.envelope.body


def test_build_provider_anthropic_returns_anthropic_provider() -> None:
    """anthropic backend + key -> AnthropicProvider."""
    p = build_provider(Settings(provider_backend="anthropic", anthropic_api_key="sk"))
    assert isinstance(p, AnthropicProvider)


def test_build_provider_provider_id_override_does_not_mutate_settings() -> None:
    """Per-request provider selection builds the override without global mutation."""
    s = Settings(provider_backend="fake", openai_api_key="x")
    p = build_provider(s, provider_id="openai")
    assert isinstance(p, OpenAIProvider)
    assert s.provider_backend == "fake"


def test_build_provider_uses_request_api_key_for_override() -> None:
    """A BYOK key can satisfy provider construction for a per-request route."""
    p = build_provider(
        Settings(provider_backend="fake", openai_api_key=None),
        provider_id="openai",
        api_key="sk-user-byok",
    )
    assert isinstance(p, OpenAIProvider)


def test_build_provider_gemini_pending_route_fails_closed() -> None:
    """Gemini is registered for roadmap visibility but has no adapter yet."""
    with pytest.raises(AppError) as exc_info:
        build_provider(Settings(provider_backend="gemini"))
    err = exc_info.value
    assert err.status_code == 500
    assert err.envelope.code == "MISCONFIGURED"
    assert "PROVIDER_BACKEND='gemini'" in err.envelope.body
    assert "no available adapter" in err.envelope.body


def test_build_provider_fake_production_override_fails_closed() -> None:
    """A crafted per-request fake override cannot bypass the prod guard."""
    with pytest.raises(AppError) as exc_info:
        build_provider(
            Settings(provider_backend="deepseek", deepseek_api_key="ds", env="production"),
            provider_id="fake",
        )
    err = exc_info.value
    assert err.status_code == 500
    assert err.envelope.code == "MISCONFIGURED"
    assert "not allowed in production" in err.envelope.body


def test_build_provider_default_is_fake() -> None:
    """The default/fake backend -> FakeProvider (no key required)."""
    p = build_provider(Settings(provider_backend="fake"))
    assert isinstance(p, FakeProvider)

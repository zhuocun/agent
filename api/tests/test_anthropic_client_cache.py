"""Per-user `AsyncAnthropic` LRU cache tests.

`app/providers/anthropic.py` exposes `_build_client(api_key, base_url)` wrapped
in `@lru_cache(maxsize=256)` so each BYOK key (and the platform key) is bound
to a long-lived `AsyncAnthropic` instance with its own httpx connection pool.

Tests cover:
- Same `(api_key, base_url)` → same instance (cache hit).
- Different `api_key` → different instance (cache miss).
- Different `base_url` → different instance (cache miss).
- `reset_anthropic_client_cache()` actually clears.
- `AnthropicProvider._client_for(api_key)` resolves through the same cache:
  same api_key on two requests returns the same client.
"""

from __future__ import annotations

from app.providers.anthropic import (
    AnthropicProvider,
    _build_client,
    reset_anthropic_client_cache,
)


def test_build_client_returns_same_instance_for_same_key() -> None:
    reset_anthropic_client_cache()
    a = _build_client("sk-test-aaaa", None)
    b = _build_client("sk-test-aaaa", None)
    assert a is b


def test_build_client_returns_different_instance_for_different_key() -> None:
    reset_anthropic_client_cache()
    a = _build_client("sk-test-aaaa", None)
    b = _build_client("sk-test-bbbb", None)
    assert a is not b


def test_build_client_keys_on_base_url() -> None:
    """A different `base_url` is a different cache key."""
    reset_anthropic_client_cache()
    a = _build_client("sk-test-aaaa", None)
    b = _build_client("sk-test-aaaa", "https://example.com/v1")
    assert a is not b
    # Same (key, base_url) again returns the same instance.
    c = _build_client("sk-test-aaaa", "https://example.com/v1")
    assert b is c


def test_reset_anthropic_client_cache_drops_existing_instances() -> None:
    reset_anthropic_client_cache()
    first = _build_client("sk-test-reset", None)
    reset_anthropic_client_cache()
    second = _build_client("sk-test-reset", None)
    # After cache_clear, the next call constructs a fresh instance.
    assert first is not second


def test_provider_client_for_reuses_default_client_across_requests() -> None:
    """`_client_for(None)` returns the cached default-key client; same on reuse."""
    reset_anthropic_client_cache()
    provider = AnthropicProvider(api_key="sk-platform")
    a = provider._client_for(None)
    b = provider._client_for(None)
    assert a is b


def test_provider_client_for_byok_reuses_per_key_client() -> None:
    """BYOK requests with the same api_key reuse the same cached client."""
    reset_anthropic_client_cache()
    provider = AnthropicProvider(api_key="sk-platform")
    a = provider._client_for("sk-byok-user-1")
    b = provider._client_for("sk-byok-user-1")
    assert a is b
    # And a different BYOK key gets its own instance.
    c = provider._client_for("sk-byok-user-2")
    assert c is not a

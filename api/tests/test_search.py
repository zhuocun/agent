"""Tests for the web-search backend package (`app.search`).

Covers:
- `FakeSearchProvider` determinism + shape (3 stable SourceItems per query).
- `get_search_provider` selection across `search_backend` values.
- `search_enabled` truth table (the wire/route layer imports it from here).
- `TavilySearchProvider` HTTP mapping via respx: SourceItem fields, domain
  parsing, snippet truncation, and graceful error on non-200 / transport fail.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import Settings
from app.search.factory import get_search_provider, search_enabled
from app.search.fake import FakeSearchProvider
from app.search.protocol import SourceItem
from app.search.tavily import (
    TavilySearchError,
    TavilySearchProvider,
    reset_tavily_client_cache,
)

# NB: no module-level `pytest.mark.asyncio` — this module mixes sync (factory)
# and async (provider) tests, and `asyncio_mode = "auto"` (pyproject) collects
# the coroutine tests automatically. Marking sync tests asyncio just warns.

_TAVILY_URL = "https://api.tavily.com/search"


# --- FakeSearchProvider -------------------------------------------------------


async def test_fake_search_is_deterministic_and_three_items() -> None:
    """Same query -> identical 3-item list; ids are 1..3."""
    provider = FakeSearchProvider()
    first = await provider.search("what is rust")
    second = await provider.search("what is rust")

    assert len(first) == 3
    assert [it.id for it in first] == [1, 2, 3]
    # Deterministic: identical across calls.
    assert [it.model_dump() for it in first] == [it.model_dump() for it in second]
    # Every item is a well-formed SourceItem with required fields populated.
    for it in first:
        assert isinstance(it, SourceItem)
        assert it.title
        assert it.url.startswith("https://")
        assert it.domain


async def test_fake_search_distinct_queries_distinct_sources() -> None:
    """Different queries -> different (but stable) urls."""
    a = await FakeSearchProvider().search("alpha")
    b = await FakeSearchProvider().search("beta")
    assert [it.url for it in a] != [it.url for it in b]


# --- factory: get_search_provider + search_enabled ----------------------------


def test_factory_none_backend_returns_none() -> None:
    # `search_backend` / `tavily_api_key` carry env-name aliases, so construct
    # by alias (SEARCH_BACKEND / TAVILY_API_KEY) — same convention as the KEK.
    s = Settings(SEARCH_BACKEND="none")  # type: ignore[call-arg]
    assert get_search_provider(s) is None
    assert search_enabled(s) is False


def test_factory_fake_backend_returns_fake_provider() -> None:
    s = Settings(SEARCH_BACKEND="fake")  # type: ignore[call-arg]
    provider = get_search_provider(s)
    assert isinstance(provider, FakeSearchProvider)
    assert search_enabled(s) is True


def test_factory_tavily_with_key_returns_tavily_provider() -> None:
    s = Settings(SEARCH_BACKEND="tavily", TAVILY_API_KEY="tvly-secret")  # type: ignore[call-arg]
    provider = get_search_provider(s)
    assert isinstance(provider, TavilySearchProvider)
    assert search_enabled(s) is True


def test_factory_tavily_without_key_degrades_to_none() -> None:
    """tavily selected but no key -> no provider (misconfig disables search)."""
    s = Settings(SEARCH_BACKEND="tavily", TAVILY_API_KEY=None)  # type: ignore[call-arg]
    assert get_search_provider(s) is None
    assert search_enabled(s) is False


# --- TavilySearchProvider HTTP mapping ----------------------------------------


def _tavily_response(results: list[dict[str, object]]) -> httpx.Response:
    return httpx.Response(200, json={"results": results})


@respx.mock
async def test_tavily_maps_results_to_source_items() -> None:
    """Each Tavily result -> SourceItem with 1-based id, title, url, domain."""
    reset_tavily_client_cache()
    route = respx.post(_TAVILY_URL).mock(
        return_value=_tavily_response(
            [
                {
                    "title": "Rust programming language",
                    "url": "https://www.rust-lang.org/learn",
                    "content": "Rust is a systems programming language.",
                },
                {
                    "title": "The Rust Book",
                    "url": "https://doc.rust-lang.org/book/",
                    "content": "An introductory book about Rust.",
                },
            ]
        )
    )

    provider = TavilySearchProvider(api_key="tvly-secret")
    items = await provider.search("rust language", max_results=2)

    assert route.called
    # The api_key rides the request body, never a header.
    sent = route.calls.last.request
    import json as _json

    body = _json.loads(sent.content)
    assert body["api_key"] == "tvly-secret"
    assert body["query"] == "rust language"
    assert body["max_results"] == 2
    assert body["search_depth"] == "basic"
    assert body["include_answer"] is False

    assert [it.id for it in items] == [1, 2]
    assert items[0].title == "Rust programming language"
    assert items[0].url == "https://www.rust-lang.org/learn"
    assert items[0].domain == "www.rust-lang.org"
    assert items[0].snippet == "Rust is a systems programming language."
    assert items[1].domain == "doc.rust-lang.org"


@respx.mock
async def test_tavily_drops_non_http_urls_and_renumbers_ids() -> None:
    """Results with a non-http(s) scheme (javascript:, data:, protocol-relative)
    are dropped entirely; surviving items keep contiguous 1-based ids so cited
    references can't point at a dropped source."""
    reset_tavily_client_cache()
    respx.post(_TAVILY_URL).mock(
        return_value=_tavily_response(
            [
                {"title": "Safe", "url": "https://a.example.com/x", "content": "ok"},
                {"title": "XSS", "url": "javascript:alert(1)", "content": "bad"},
                {"title": "Data", "url": "data:text/html,<b>", "content": "bad"},
                {"title": "Schemeless", "url": "//evil.example.com", "content": "bad"},
                {"title": "Safe2", "url": "http://b.example.com/y", "content": "ok2"},
            ]
        )
    )

    items = await TavilySearchProvider(api_key="k").search("q", max_results=5)

    # Only the two http(s) results survive, renumbered 1..2 (no gaps).
    assert [it.id for it in items] == [1, 2]
    assert [it.url for it in items] == [
        "https://a.example.com/x",
        "http://b.example.com/y",
    ]


@respx.mock
async def test_tavily_truncates_long_snippet() -> None:
    """A >300-char `content` is truncated to ~300 chars with an ellipsis."""
    reset_tavily_client_cache()
    long_content = "x" * 500
    respx.post(_TAVILY_URL).mock(
        return_value=_tavily_response(
            [{"title": "T", "url": "https://example.com/a", "content": long_content}]
        )
    )

    items = await TavilySearchProvider(api_key="k").search("q")
    snippet = items[0].snippet
    assert snippet is not None
    # 300 chars + the appended ellipsis.
    assert len(snippet) == 301
    assert snippet.endswith("…")
    assert snippet[:300] == "x" * 300


@respx.mock
async def test_tavily_missing_content_yields_none_snippet() -> None:
    """A result without `content` -> snippet is None (not empty string)."""
    reset_tavily_client_cache()
    respx.post(_TAVILY_URL).mock(
        return_value=_tavily_response([{"title": "T", "url": "https://example.com/a"}])
    )
    items = await TavilySearchProvider(api_key="k").search("q")
    assert items[0].snippet is None
    assert items[0].domain == "example.com"


@respx.mock
async def test_tavily_non_200_raises_clear_error() -> None:
    """A non-200 response raises TavilySearchError (caller degrades gracefully)."""
    reset_tavily_client_cache()
    respx.post(_TAVILY_URL).mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(TavilySearchError):
        await TavilySearchProvider(api_key="k").search("q")


@respx.mock
async def test_tavily_transport_error_raises_clear_error() -> None:
    """A transport failure raises TavilySearchError, not a bare httpx error."""
    reset_tavily_client_cache()
    respx.post(_TAVILY_URL).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(TavilySearchError):
        await TavilySearchProvider(api_key="k").search("q")

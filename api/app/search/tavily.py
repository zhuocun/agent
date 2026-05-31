"""Tavily web-search backend.

Real client over Tavily's `/search` endpoint via `httpx.AsyncClient`. Maps each
result to a `SourceItem` (1-based id, title, url, `content`→`snippet` truncated
to ~300 chars, `domain` parsed from the url). Non-200 responses and transport
errors raise `TavilySearchError` so the caller can degrade gracefully (drop the
tool result rather than failing the whole turn).

Client reuse follows the same `@lru_cache` convention as the provider adapters
(`app.providers.anthropic._build_client`): an `httpx.AsyncClient`'s connection
pool is expensive to churn, so one client per `(api_key, timeout)` is cached and
reused across searches.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

import httpx

from app.search.protocol import SourceItem

_TAVILY_URL = "https://api.tavily.com/search"
_SNIPPET_MAX_CHARS = 300
# Tavily is a synchronous third-party round-trip; bound it so a slow upstream
# can't stall a streaming turn indefinitely.
_DEFAULT_TIMEOUT_S = 15.0


class TavilySearchError(RuntimeError):
    """Raised on a non-200 Tavily response or a transport failure.

    Carries a clean message; the caller logs the cause and degrades gracefully
    (the web-search turn proceeds without sources rather than erroring out).
    """


@lru_cache(maxsize=64)
def _build_client(timeout: float) -> httpx.AsyncClient:
    """Per-timeout cached `httpx.AsyncClient`.

    The API key rides the request body (not a header), so it is NOT part of the
    cache key — one pooled client serves every key. Cache size 64 is ample for
    the one or two distinct timeouts in practice; LRU eviction bounds memory.
    Tests can call `_build_client.cache_clear()` to reset.
    """
    return httpx.AsyncClient(timeout=timeout)


def reset_tavily_client_cache() -> None:
    """Clear the cached httpx client. Useful in tests."""
    _build_client.cache_clear()


def _domain_of(url: str) -> str | None:
    """Parse the host out of a URL; None when it can't be determined."""
    try:
        host = urlparse(url).netloc
    except ValueError:
        return None
    return host or None


def _truncate(text: str, limit: int = _SNIPPET_MAX_CHARS) -> str:
    """Truncate a snippet to ~`limit` chars, appending an ellipsis when cut."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


class TavilySearchProvider:
    """Adapter over Tavily's `/search` endpoint."""

    def __init__(self, api_key: str, *, timeout: float = _DEFAULT_TIMEOUT_S):
        self._api_key = api_key
        self._timeout = timeout

    async def search(self, query: str, *, max_results: int = 5) -> list[SourceItem]:
        client = _build_client(self._timeout)
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
        }
        try:
            response = await client.post(_TAVILY_URL, json=payload)
        except httpx.HTTPError as exc:
            raise TavilySearchError(f"Tavily request failed: {exc}") from exc
        if response.status_code != 200:
            raise TavilySearchError(
                f"Tavily returned HTTP {response.status_code}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise TavilySearchError("Tavily returned a non-JSON body") from exc

        results = data.get("results") or []
        items: list[SourceItem] = []
        for idx, result in enumerate(results, start=1):
            if not isinstance(result, dict):
                continue
            url = str(result.get("url") or "")
            title = str(result.get("title") or url or f"Result {idx}")
            content = result.get("content")
            snippet = _truncate(str(content)) if content else None
            items.append(
                SourceItem(
                    id=idx,
                    title=title,
                    url=url,
                    snippet=snippet,
                    domain=_domain_of(url),
                )
            )
        return items

"""Env-driven web-search backend selection.

`SEARCH_BACKEND=none` (default) → no search provider; the web_search tool is
never advertised and behavior is byte-for-byte unchanged from a pre-web-search
build.
`SEARCH_BACKEND=fake` → `FakeSearchProvider` (deterministic, no network).
`SEARCH_BACKEND=tavily` → `TavilySearchProvider` when `TAVILY_API_KEY` is set;
when the key is missing this degrades to `None` (no provider) so a
misconfiguration disables search rather than crashing every turn.

`search_enabled(settings)` is the single truth source for "is web search
usable?" — the wire/route layer imports it from THIS module
(`app.search.factory.search_enabled`); keep the name/location stable.
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.search.fake import FakeSearchProvider
from app.search.protocol import SearchProvider
from app.search.tavily import TavilySearchProvider


def get_search_provider(settings: Settings | None = None) -> SearchProvider | None:
    """Return a `SearchProvider` for the configured backend, or `None`.

    `None` means "web search is not available" — either the backend is `none`
    / unset, or `tavily` is selected but no `TAVILY_API_KEY` is configured.
    """
    s = settings if settings is not None else get_settings()
    if s.search_backend == "fake":
        return FakeSearchProvider()
    if s.search_backend == "tavily":
        if not s.tavily_api_key:
            return None
        return TavilySearchProvider(api_key=s.tavily_api_key)
    return None


def search_enabled(settings: Settings | None = None) -> bool:
    """True iff a usable web-search backend is configured.

    Equivalent to `get_search_provider(...) is not None`, expressed directly so
    callers that only need the boolean don't construct a client.
    """
    s = settings if settings is not None else get_settings()
    if s.search_backend == "fake":
        return True
    if s.search_backend == "tavily":
        return bool(s.tavily_api_key)
    return False

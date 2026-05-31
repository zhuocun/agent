"""Web-search backend package.

Public surface:

- `SourceItem` / `SearchProvider` — the canonical source object and backend
  Protocol (`protocol`).
- `FakeSearchProvider` / `TavilySearchProvider` — the two backends.
- `get_search_provider` / `search_enabled` — env-driven selection (`factory`).

`search/` deliberately does NOT import `app.providers.*`; the dependency runs
provider → search only, never the reverse, to avoid an import cycle.
"""

from __future__ import annotations

from app.search.factory import get_search_provider, search_enabled
from app.search.fake import FakeSearchProvider
from app.search.protocol import SearchProvider, SourceItem
from app.search.tavily import TavilySearchError, TavilySearchProvider

__all__ = [
    "FakeSearchProvider",
    "SearchProvider",
    "SourceItem",
    "TavilySearchError",
    "TavilySearchProvider",
    "get_search_provider",
    "search_enabled",
]

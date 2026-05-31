"""Deterministic, no-network search backend for dev/tests/e2e.

Returns three `SourceItem`s derived purely from the query string so distinct
queries produce distinct (but stable) sources. No sleeps, no I/O — tests can
assert the exact shape.
"""

from __future__ import annotations

import hashlib

from app.search.protocol import SourceItem


def _slug(query: str) -> str:
    """A short, URL-safe, stable slug derived from the query."""
    h = hashlib.sha256(query.encode("utf-8")).hexdigest()[:8]
    return h


class FakeSearchProvider:
    """In-process fake search. No network. Deterministic per `query`."""

    async def search(self, query: str, *, max_results: int = 5) -> list[SourceItem]:
        slug = _slug(query)
        domains = ("example.com", "docs.example.org", "news.example.net")
        items: list[SourceItem] = []
        # Always three deterministic items (ids 1..3), capped at max_results so
        # a caller asking for fewer still gets a well-formed prefix.
        for i in range(min(3, max(max_results, 0)) or 3):
            n = i + 1
            domain = domains[i % len(domains)]
            items.append(
                SourceItem(
                    id=n,
                    title=f"Result {n} for {query}",
                    url=f"https://{domain}/{slug}/{n}",
                    snippet=f"Deterministic snippet {n} about {query} ({slug}).",
                    domain=domain,
                )
            )
        return items

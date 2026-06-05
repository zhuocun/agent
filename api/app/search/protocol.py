"""Search abstraction: a swappable web-search backend.

`SourceItem` is the canonical source / citation object surfaced for a
web-search turn — it is shared verbatim with the provider event layer
(`app.providers.protocol.Sources`) and, downstream, the wire schema. Keep its
fields tight to what the FE renders: an ordered citation with a title, a URL,
and optional snippet / domain.

`SearchProvider` is the Protocol every backend (`TavilySearchProvider`,
`FakeSearchProvider`) implements. The provider layer depends on `search/`, NOT
the other way around — `search/` must never import `app.providers.*` (that
would create an import cycle).
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel


class SourceItem(BaseModel):
    """One resolved web source / citation for a turn.

    `id` is a 1-based ordinal within the turn's source list (the FE renders
    inline citations like `[1]` / `[2]` keyed on it). `title` / `url` are
    required; `snippet` (a short excerpt) and `domain` (the URL's host) are
    optional display affordances.

    `provenance` is the source's origin class (PRD 07 §4.3 transparency
    contract): `web` is the only live one today; `knowledge` (private RAG) and
    `connector` (third-party docs) are RESERVED in the enum so the field
    round-trips everywhere now without a later schema migration. Defaulting to
    `web` means the search protocol, the provider `Sources` event, the
    `SourcesEvent` SSE payload, the persisted `SourcesPart`, and the public-share
    `PublicMessage.parts` all carry it for free.
    """

    id: int
    title: str
    url: str
    snippet: str | None = None
    domain: str | None = None
    provenance: Literal["web", "knowledge", "connector"] = "web"


class SearchProvider(Protocol):
    """Swappable web-search backend.

    `search(...)` runs a single query and returns up to `max_results` ordered
    `SourceItem`s (ids 1..N). Implementations that hit the network MUST raise a
    clear exception on transport / non-200 failures so the caller can degrade
    gracefully (the provider drops the tool result rather than failing the
    whole turn).
    """

    async def search(self, query: str, *, max_results: int = 5) -> list[SourceItem]: ...

"""Memory-fact wire schemas (transparent long-term memory v1, D19).

camelCase wire shapes (via `CamelModel`) for the `/api/account/memory` CRUD
surface and the account export. `MemoryFact` mirrors `web/src/lib/types.ts`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import StringConstraints, field_validator

from app.schemas.common import CamelModel

# A single fact's content. Bounded so a runaway client can't store unbounded
# blobs. `max_length` caps the raw string; a per-model validator strips and
# rejects whitespace-only content (the route stores the trimmed value).
MemoryFactContent = Annotated[str, StringConstraints(max_length=2000)]

MemoryFactSource = Literal["manual", "conversation"]


def _require_non_blank(value: str) -> str:
    """Reject whitespace-only content as INVALID_INPUT (raises ValueError)."""
    if not value.strip():
        raise ValueError("content must not be blank")
    return value


class MemoryFact(CamelModel):
    id: str
    content: str
    source: MemoryFactSource
    source_conversation_id: str | None = None
    created_at: str
    updated_at: str


class MemoryFactCreateRequest(CamelModel):
    content: MemoryFactContent
    # Optional back-reference when a fact is saved from a specific conversation
    # (the cheap "Save to memory" affordance). Defaults to a manual fact.
    source_conversation_id: str | None = None

    _non_blank = field_validator("content")(_require_non_blank)


class MemoryFactUpdateRequest(CamelModel):
    content: MemoryFactContent

    _non_blank = field_validator("content")(_require_non_blank)

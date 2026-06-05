"""Tag wire schemas (Conversation Org v2).

camelCase wire shapes (via `CamelModel`) for the `/api/tags` CRUD surface, the
bootstrap payload, and the account export. `Tag` mirrors `web/src/lib/types.ts`.

A Tag is a thin user-scoped label assignable to conversations. `name` is
required, stripped, and bounded; a per-model validator rejects blank names.
`color` is optional and the BE does not interpret it.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints, field_validator

from app.schemas.common import CamelModel

# A tag name. Stripped + bounded; a per-field validator rejects blank names.
TagName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
# An optional display color. Stripped + bounded; the BE stores it opaquely.
TagColor = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)
]


def _require_non_blank(value: str | None) -> str | None:
    """Reject a whitespace-only name. NULL passes (only `name` is required)."""
    if value is not None and not value.strip():
        raise ValueError("must not be blank")
    return value


class Tag(CamelModel):
    id: str
    name: str
    color: str | None = None
    created_at: str
    updated_at: str


class TagCreateRequest(CamelModel):
    name: TagName
    color: TagColor | None = None

    _non_blank = field_validator("name")(_require_non_blank)


class TagUpdateRequest(CamelModel):
    """Body for PATCH /api/tags/:id.

    Both fields optional. `name` omitted leaves it unchanged. `color` is
    THREE-VALUED on the wire (via `model_fields_set` in the route): omitted =
    leave unchanged; explicit `null` = clear the color; a value = set it.
    """

    name: TagName | None = None
    color: TagColor | None = None

    _non_blank = field_validator("name")(_require_non_blank)

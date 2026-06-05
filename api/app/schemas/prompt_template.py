"""Prompt-template wire schemas (prompt library, D23).

camelCase wire shapes (via `CamelModel`) for the `/api/account/prompt-templates`
CRUD surface and the account export. `PromptTemplate` mirrors
`web/src/lib/types.ts`.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints, field_validator

from app.schemas.common import CamelModel

# Bounds so a runaway client can't store unbounded blobs. `max_length` caps the
# raw string; a per-field validator strips and rejects whitespace-only required
# fields (the route stores the trimmed value).
PromptTemplateTitle = Annotated[str, StringConstraints(max_length=200)]
PromptTemplateBody = Annotated[str, StringConstraints(max_length=10000)]
PromptTemplateDescription = Annotated[str, StringConstraints(max_length=500)]


def _require_non_blank(value: str) -> str:
    """Reject whitespace-only content as INVALID_INPUT (raises ValueError)."""
    if not value.strip():
        raise ValueError("value must not be blank")
    return value


class PromptTemplate(CamelModel):
    id: str
    title: str
    body: str
    description: str | None = None
    created_at: str
    updated_at: str


class PromptTemplateCreateRequest(CamelModel):
    title: PromptTemplateTitle
    body: PromptTemplateBody
    description: PromptTemplateDescription | None = None

    _non_blank_title = field_validator("title")(_require_non_blank)
    _non_blank_body = field_validator("body")(_require_non_blank)


class PromptTemplateUpdateRequest(CamelModel):
    title: PromptTemplateTitle
    body: PromptTemplateBody
    description: PromptTemplateDescription | None = None

    _non_blank_title = field_validator("title")(_require_non_blank)
    _non_blank_body = field_validator("body")(_require_non_blank)

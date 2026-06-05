"""Project/Space wire schemas (D20).

camelCase wire shapes (via `CamelModel`) for the `/api/projects` CRUD surface,
the bootstrap payload, and the account export. `Project` mirrors
`web/src/lib/types.ts`.

A Project is a thin scoping container: it groups conversations and scopes the
existing wedge controls. Every setting is OPTIONAL and `None` means "inherit the
user-global value" — a labeled default, not a lock. `defaultTierId` is validated
against the known-tier registry when provided (NULL stays NULL = inherit).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints, field_validator

from app.providers.tiers import is_known_tier
from app.schemas.common import CamelModel

# A project name. Stripped + bounded; a per-model validator rejects blank names.
ProjectName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
# Shared project instructions. Bounded to mirror `Preferences.custom_instructions`
# (String(4000)); not stripped so intentional formatting survives.
ProjectInstructions = Annotated[str, StringConstraints(max_length=4000)]


def _require_known_tier(value: str | None) -> str | None:
    """Reject an unknown `defaultTierId` as INVALID_INPUT. NULL passes (inherit)."""
    if value is not None and not is_known_tier(value):
        raise ValueError("defaultTierId must be a known tier id")
    return value


class Project(CamelModel):
    id: str
    name: str
    custom_instructions: str | None = None
    default_tier_id: str | None = None
    retention_days: int | None = None
    per_conversation_budget_usd: float | None = None
    created_at: str
    updated_at: str


class ProjectSummary(CamelModel):
    """Lighter shape for the bootstrap sidebar — the settings drive the FE
    pickers, so they ride along, but messages/timestamps stay out."""

    id: str
    name: str
    custom_instructions: str | None = None
    default_tier_id: str | None = None
    retention_days: int | None = None
    per_conversation_budget_usd: float | None = None


class ProjectCreateRequest(CamelModel):
    name: ProjectName
    custom_instructions: ProjectInstructions | None = None
    default_tier_id: str | None = None
    # Project retention window in days. NULL = inherit. Capped at 3650 (~10y) to
    # match the per-conversation override bound.
    retention_days: Annotated[int, Field(ge=1, le=3650)] | None = None
    # Project per-conversation budget sub-cap in USD. Non-negative; NULL = inherit.
    per_conversation_budget_usd: Annotated[float, Field(ge=0)] | None = None

    _known_tier = field_validator("default_tier_id")(_require_known_tier)


class ProjectUpdateRequest(CamelModel):
    """Body for PATCH /api/projects/:id.

    All fields optional. `name` omitted leaves it unchanged. The four settings
    are THREE-VALUED on the wire (via `model_fields_set` in the route): omitted =
    leave unchanged; explicit `null` = clear back to inherit; a value = set it.
    The field types permit `None` so an explicit clear validates; the route tells
    "omitted" from an explicit `null` by inspecting `model_fields_set`.
    """

    name: ProjectName | None = None
    custom_instructions: ProjectInstructions | None = None
    default_tier_id: str | None = None
    retention_days: Annotated[int, Field(ge=1, le=3650)] | None = None
    per_conversation_budget_usd: Annotated[float, Field(ge=0)] | None = None

    _known_tier = field_validator("default_tier_id")(_require_known_tier)

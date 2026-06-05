"""Trust-surface wire shapes (PRD 07 §6.5 / PRD 05 §7.4 / PRD 08 §5.6).

The data-access activity log, the per-message processing-provenance rollup, and
the moderation-appeal capture. All camelCase on the wire via `CamelModel`. None
of these surface message content — only event-relevant ids/labels and counts.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import CamelModel


class ActivityEvent(CamelModel):
    """One row of the data-access activity log (an `AuditEvent` projection)."""

    id: str
    event_type: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class DataProcessingBucket(CamelModel):
    """Per-provider rollup of where the caller's messages were processed.

    `jurisdiction` is read from the LIVE provider registry
    (`data_policy.data_residency`); a provider with no policy is `None`, which
    the FE renders as "policy unavailable". Never hardcoded.
    """

    provider_id: str
    provider_label: str
    jurisdiction: str | None = None
    message_count: int
    is_byok_count: int
    platform_count: int
    substitution_count: int


class DataProcessingRollup(CamelModel):
    total_attributed: int
    by_provider: list[DataProcessingBucket] = Field(default_factory=list)


class ModerationAppealRequest(CamelModel):
    """Request-review capture for a blocked turn — no operator tooling.

    All fields optional: the FE forwards whatever the error envelope carried
    (`reasonCode` / `source`) plus an optional free-text note from the user.
    """

    reason_code: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=2000)

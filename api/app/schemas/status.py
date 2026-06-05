"""Public platform-status wire schema (PRD 08 §10).

The `/api/status` route is the second unauthenticated read in the API (after
public share). It exposes a calm, platform-level health summary derived from
recent `Stream` telemetry — no per-user data, no per-provider breakdown.
"""

from __future__ import annotations

from typing import Literal

from app.schemas.common import CamelModel


class PlatformStatus(CamelModel):
    """Platform health summary for the public status page + degraded banner.

    `status` is `operational` by default and only flips to `degraded` when the
    recent window holds a meaningful sample AND the error ratio exceeds the
    configured threshold (see `app.config` STATUS_* settings). The remaining
    fields are disclosed so the status page can show the evidence behind the
    verdict without leaking any user or conversation content.
    """

    status: Literal["operational", "degraded"]
    window_seconds: int
    sample_size: int
    error_count: int
    updated_at: str

"""Analytics event schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import CamelModel

AnalyticsEventType = Literal[
    "settings.opened",
    "usage.viewed",
    "attribution.opened",
    "tier.changed",
    "provider.changed",
    "byok.form_opened",
    "byok.saved",
    "byok.deleted",
    "install_prompt.shown",
    "install_prompt.accepted",
    "install_prompt.dismissed",
]

AnalyticsScalar = str | int | float | bool | None


class AnalyticsEventRequest(CamelModel):
    event_type: AnalyticsEventType
    properties: dict[str, AnalyticsScalar] = Field(default_factory=dict)

    @field_validator("properties")
    @classmethod
    def validate_properties(cls, value: dict[str, AnalyticsScalar]) -> dict[str, AnalyticsScalar]:
        if len(value) > 12:
            raise ValueError("properties may contain at most 12 keys")
        blocked_fragments = ("text", "prompt", "message", "content", "api_key", "apikey")
        cleaned: dict[str, AnalyticsScalar] = {}
        for key, item in value.items():
            if len(key) > 40:
                raise ValueError("property keys must be at most 40 characters")
            lowered = key.lower()
            if any(fragment in lowered for fragment in blocked_fragments):
                raise ValueError("properties must not include message or secret content")
            if isinstance(item, str) and len(item) > 80:
                raise ValueError("string property values must be at most 80 characters")
            cleaned[key] = item
        return cleaned

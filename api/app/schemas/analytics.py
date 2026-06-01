"""Analytics event schemas."""

from __future__ import annotations

import re
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
_BLOCKED_PROPERTY_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "content",
    "cookie",
    "credential",
    "email",
    "message",
    "password",
    "prompt",
    "secret",
    "session",
    "text",
    "token",
)
_TOKEN_LEFT_BOUNDARY = r"(?<![a-z0-9_-])"
_SECRET_VALUE_RE = re.compile(
    rf"(?i)(^\s*bearer\s+|{_TOKEN_LEFT_BOUNDARY}sk-[a-z0-9_-]{{8,}}|"
    rf"{_TOKEN_LEFT_BOUNDARY}sk_(?:live|test)_[a-z0-9_-]+|"
    rf"{_TOKEN_LEFT_BOUNDARY}sk-ant-[a-z0-9_-]+|"
    rf"{_TOKEN_LEFT_BOUNDARY}sk-proj-[a-z0-9_-]+|"
    rf"{_TOKEN_LEFT_BOUNDARY}gh[pousr]_[a-z0-9_-]+|"
    rf"{_TOKEN_LEFT_BOUNDARY}github_pat_[a-z0-9_-]+|"
    rf"{_TOKEN_LEFT_BOUNDARY}AIza[0-9A-Za-z_-]{{20,}}|-----BEGIN\s+)"
)


def analytics_property_key_is_blocked(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _BLOCKED_PROPERTY_KEY_FRAGMENTS)


def analytics_value_looks_sensitive(value: str) -> bool:
    return _SECRET_VALUE_RE.search(value) is not None


class AnalyticsEventRequest(CamelModel):
    event_type: AnalyticsEventType
    properties: dict[str, AnalyticsScalar] = Field(default_factory=dict)

    @field_validator("properties")
    @classmethod
    def validate_properties(cls, value: dict[str, AnalyticsScalar]) -> dict[str, AnalyticsScalar]:
        if len(value) > 12:
            raise ValueError("properties may contain at most 12 keys")
        cleaned: dict[str, AnalyticsScalar] = {}
        for key, item in value.items():
            if len(key) > 40:
                raise ValueError("property keys must be at most 40 characters")
            if analytics_property_key_is_blocked(key):
                raise ValueError("properties must not include message or secret content")
            if isinstance(item, str) and len(item) > 80:
                raise ValueError("string property values must be at most 80 characters")
            if isinstance(item, str) and analytics_value_looks_sensitive(item):
                raise ValueError("properties must not include message or secret content")
            cleaned[key] = item
        return cleaned

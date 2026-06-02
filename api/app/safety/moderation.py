"""Deterministic safety preflight for user-submitted content.

The first launch-grade safety seam is intentionally local and conservative:
operators can configure a comma-separated blocklist, and the route checks the
current user message, extracted text attachments, and saved custom instructions
before any provider call or message persistence. The module shape leaves room
for a provider/gateway moderation adapter later without moving the route
integration point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.config import Settings
from app.providers.protocol import AttachmentPayload

SafetySource = Literal["message", "attachment", "custom_instructions"]


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason_code: str | None = None
    source: SafetySource | None = None


def _blocked(source: SafetySource) -> SafetyDecision:
    return SafetyDecision(
        allowed=False,
        reason_code="configured_blocklist",
        source=source,
    )


def _contains_blocked_term(value: str, terms: tuple[str, ...]) -> bool:
    haystack = " ".join(value.casefold().split())
    return any(term in haystack for term in terms)


def check_user_turn(
    settings: Settings,
    *,
    text: str,
    attachments: list[AttachmentPayload] | None = None,
    custom_instructions: str | None = None,
) -> SafetyDecision:
    """Return whether a user turn may proceed to persistence/provider calls."""
    terms = settings.safety_block_terms
    if settings.safety_backend != "local" or not terms:
        return SafetyDecision(allowed=True)

    if _contains_blocked_term(text, terms):
        return _blocked("message")

    for attachment in attachments or []:
        if attachment.extracted_text and _contains_blocked_term(
            attachment.extracted_text,
            terms,
        ):
            return _blocked("attachment")

    if custom_instructions and _contains_blocked_term(custom_instructions, terms):
        return _blocked("custom_instructions")

    return SafetyDecision(allowed=True)

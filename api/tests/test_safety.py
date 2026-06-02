"""Safety preflight tests."""

from __future__ import annotations

from app.config import Settings
from app.safety import check_user_turn


def test_safety_blocklist_requires_local_backend() -> None:
    settings = Settings(
        SAFETY_BACKEND="disabled",
        SAFETY_BLOCKLIST="blocked phrase",
    )

    decision = check_user_turn(settings, text="contains blocked phrase")

    assert decision.allowed is True


def test_safety_blocklist_normalizes_whitespace() -> None:
    settings = Settings(
        SAFETY_BACKEND="local",
        SAFETY_BLOCKLIST="blocked   phrase",
    )

    decision = check_user_turn(settings, text="contains blocked phrase")

    assert decision.allowed is False
    assert decision.reason_code == "configured_blocklist"
    assert decision.source == "message"


def test_safety_blocklist_checks_custom_instructions() -> None:
    settings = Settings(
        SAFETY_BACKEND="local",
        SAFETY_BLOCKLIST="blocked phrase",
    )

    decision = check_user_turn(
        settings,
        text="regular user text",
        custom_instructions="Always include the blocked phrase.",
    )

    assert decision.allowed is False
    assert decision.reason_code == "configured_blocklist"
    assert decision.source == "custom_instructions"

"""Unit tests for the cache-stable prompt assembly (T20) + datetime block.

The system prefix now always leads with the current UTC date and time, so it is
ALWAYS a non-None string. These tests pin ``now`` for determinism and cover:

- the datetime block rendering / placement,
- UTC normalization of aware (non-UTC) and naive inputs,
- block ordering (datetime, then memory, then instructions),
- empty / whitespace memory + instructions still yielding the datetime block.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from app.prompt_assembly import build_system_prefix, build_user_turn

# A fixed instant: Monday, 2024-01-15 09:05 UTC.
_PINNED = datetime(2024, 1, 15, 9, 5, 30, tzinfo=UTC)
_RENDERED = "Monday, 2024-01-15 09:05 UTC"


def test_datetime_block_uses_pinned_now() -> None:
    prefix = build_system_prefix(now=_PINNED)
    assert prefix is not None
    assert _RENDERED in prefix
    # No memory / instructions ⇒ datetime block stands alone.
    assert "<memory>" not in prefix
    assert "<custom_instructions>" not in prefix


def test_prefix_is_never_none_with_empty_inputs() -> None:
    """Empty memory + blank instructions still yields the datetime block."""
    prefix = build_system_prefix("", [], now=_PINNED)
    assert prefix is not None
    assert _RENDERED in prefix

    whitespace = build_system_prefix("   ", ["   ", ""], now=_PINNED)
    assert whitespace is not None
    assert _RENDERED in whitespace
    assert "<memory>" not in whitespace
    assert "<custom_instructions>" not in whitespace


def test_aware_non_utc_now_is_normalized_to_utc() -> None:
    # 2024-01-15 18:05:30 +09:00 == 09:05:30 UTC == the pinned render.
    tokyo = timezone(timedelta(hours=9))
    aware = datetime(2024, 1, 15, 18, 5, 30, tzinfo=tokyo)
    prefix = build_system_prefix(now=aware)
    assert _RENDERED in prefix


def test_naive_now_is_assumed_utc() -> None:
    naive = datetime(2024, 1, 15, 9, 5, 30)
    prefix = build_system_prefix(now=naive)
    assert _RENDERED in prefix


def test_block_ordering_datetime_then_memory_then_instructions() -> None:
    prefix = build_system_prefix(
        "Always answer in terse bullets.",
        ["I am a pilot.", "I live in Tokyo."],
        now=_PINNED,
    )
    assert prefix is not None
    # Memory facts render as a bulleted list inside the <memory> block.
    assert "- I am a pilot." in prefix
    assert "- I live in Tokyo." in prefix
    assert "<memory>" in prefix
    assert "<custom_instructions>" in prefix
    assert "Always answer in terse bullets." in prefix
    # Ordering: datetime first, then memory, then instructions.
    assert prefix.index(_RENDERED) < prefix.index("<memory>")
    assert prefix.index("<memory>") < prefix.index("<custom_instructions>")


def test_memory_only_has_no_instructions_block() -> None:
    prefix = build_system_prefix(None, ["I am a pilot."], now=_PINNED)
    assert _RENDERED in prefix
    assert "<memory>" in prefix
    assert "<custom_instructions>" not in prefix


def test_instructions_only_has_no_memory_block() -> None:
    prefix = build_system_prefix("Be terse.", None, now=_PINNED)
    assert _RENDERED in prefix
    assert "<memory>" not in prefix
    assert "Be terse." in prefix


def test_default_now_is_current_utc() -> None:
    before = datetime.now(UTC)
    prefix = build_system_prefix()
    after = datetime.now(UTC)
    # The rendered minute must match one of the boundary instants.
    rendered_minutes = {
        before.strftime("%A, %Y-%m-%d %H:%M UTC"),
        after.strftime("%A, %Y-%m-%d %H:%M UTC"),
    }
    assert any(minute in prefix for minute in rendered_minutes)


def test_build_user_turn_is_identity() -> None:
    assert build_user_turn("hello world") == "hello world"

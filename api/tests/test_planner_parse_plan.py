"""Unit tests for planner sub-question parsing and its tool-markup scrub.

`parse_plan` turns a planner model reply into a bounded sub-question list. As a
second layer behind the streaming `ToolMarkupSanitizer`, it must never let leaked
tool-call markup become a sub-question, while leaving markup-free replies
byte-for-byte identical. The scrub runs over the WHOLE reply ONCE before the
split, so it mirrors the stream sanitizer's truncate-from-first-marker
semantics: everything from the first leak onward is dropped, including any
clean-looking lines (e.g. closing tags) that follow the leak.

`｜` is U+FF5C (fullwidth vertical bar); `▁` is U+2581 (lower one-eighth block).
"""

from __future__ import annotations

from app.agentic.planner import parse_plan
from app.runtime.answer_policy import contains_tool_markup

_DSML = "<｜｜DSML｜｜"
_NATIVE_CALLS = "<｜tool▁calls▁begin｜>"
_NATIVE_CALL = "<｜tool▁call▁begin｜>"


def test_clean_reply_is_unchanged_by_scrub() -> None:
    """A markup-free reply parses exactly as before (scrub is a no-op)."""
    reply = "What is X?\n- How does Y work?\n1. Compare X and Y"
    assert parse_plan(reply, max_workers=4, fallback="fb") == [
        "What is X?",
        "How does Y work?",
        "Compare X and Y",
    ]


def test_line_starting_with_marker_is_dropped() -> None:
    """A line that is purely a leaked tool-call block never becomes a sub-question."""
    reply = f'What is X?\n{_DSML}invoke name="web_search">{{"q":"x"}}'
    out = parse_plan(reply, max_workers=4, fallback="fb")
    assert out == ["What is X?"]
    assert all(not contains_tool_markup(q) for q in out)


def test_marker_mid_line_truncates_and_drops_post_leak_lines() -> None:
    """A clean prefix before an inline marker survives; everything after drops.

    The whole-reply scrub truncates at the FIRST marker, so the clean prefix on
    the leaking line is kept but the following line (`How does Y work?`) — which
    lives AFTER the leak — is dropped, matching the stream sanitizer that stops
    emitting once a marker is seen.
    """
    reply = f'What is X? {_DSML}tool_calls>garbage\nHow does Y work?'
    out = parse_plan(reply, max_workers=4, fallback="fb")
    assert out == ["What is X?"]
    assert all(not contains_tool_markup(q) for q in out)


def test_clean_line_after_a_leak_is_dropped() -> None:
    """A perfectly clean sub-question that appears AFTER a leak is dropped.

    This is the closing-tag residual: a leaked block is often followed by a
    stray closing-tag line (or, as here, an otherwise-valid-looking line). Since
    the scrub truncates the whole reply at the first marker, none of it survives
    as a spurious sub-question.
    """
    reply = f"Real question one\n{_DSML}tool_calls>\n</｜｜DSML｜｜tool_calls>\nReal question two"
    out = parse_plan(reply, max_workers=8, fallback="fb")
    assert out == ["Real question one"]
    assert all(not contains_tool_markup(q) for q in out)


def test_earliest_native_marker_truncates_the_reply() -> None:
    """The earliest tool-call START marker (any variant) truncates the reply."""
    reply = (
        f"Real question one\n"
        f"{_NATIVE_CALLS}leak\n"
        f"{_NATIVE_CALL}leak\n"
        f"Real question two"
    )
    out = parse_plan(reply, max_workers=8, fallback="fb")
    assert out == ["Real question one"]
    assert all(not contains_tool_markup(q) for q in out)


def test_reply_that_is_all_markup_degrades_to_fallback() -> None:
    """When every line is leaked markup, the parse degrades to the fallback."""
    reply = f'{_DSML}tool_calls>\n{_DSML}invoke name="web_search">'
    assert parse_plan(reply, max_workers=4, fallback="fb") == ["fb"]

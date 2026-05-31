"""Unit tests for the streaming tool-call-markup sanitizer.

The sanitizer is the belt-and-braces safety net for the web-search path: once a
tool-call START marker appears in ANSWER content it truncates there (legitimate
answers never contain these markers). It must be streaming-safe — a marker can
split across chunk boundaries — and it must NOT over-strip ordinary text/code
that merely contains `<`, `|`, or a bare `<｜` that is not a real tool token.

`｜` is U+FF5C (fullwidth vertical bar); `▁` is U+2581 (lower one-eighth block).
"""

from __future__ import annotations

from app.providers._tool_markup import ToolMarkupSanitizer

_DSML = "<｜｜DSML｜｜"
_NATIVE_CALLS = "<｜tool▁calls▁begin｜>"
_NATIVE_CALL = "<｜tool▁call▁begin｜>"


def _drain(san: ToolMarkupSanitizer, chunks: list[str]) -> str:
    """Feed all chunks then finish; return the concatenated clean output."""
    out: list[str] = []
    for c in chunks:
        out.append(san.feed(c))
    out.append(san.finish())
    return "".join(out)


def test_clean_text_passes_through_unchanged() -> None:
    """A normal answer with incidental `<`, `|`, and code passes through verbatim."""
    text = (
        "Here is a comparison: a < b and b | c.\n"
        "```python\nif x < y or y | z:\n    print('ok')\n```\n"
        "Tables use | as a separator. Done."
    )
    # Stream it in many small chunks to exercise the hold-back logic.
    chunks = [text[i : i + 3] for i in range(0, len(text), 3)]
    assert _drain(ToolMarkupSanitizer(), chunks) == text


def test_bare_angle_fullwidth_bar_not_a_marker_passes_through() -> None:
    """A bare `<｜` NOT followed by a tool token is not a marker — keep it."""
    text = "Edge case: <｜ is just two characters here, not a tool token."
    assert _drain(ToolMarkupSanitizer(), [text]) == text


def test_marker_mid_text_truncates_at_marker() -> None:
    """A marker mid-stream truncates the answer exactly at the marker."""
    san = ToolMarkupSanitizer()
    out = san.feed(f"Real answer prose here.{_DSML}tool_calls> garbage")
    assert out == "Real answer prose here."
    assert san.truncated is True
    # Everything after truncation is suppressed.
    assert san.feed("more leaked junk") == ""
    assert san.finish() == ""


def test_marker_split_across_two_chunks() -> None:
    """A marker straddling a chunk boundary is still detected (nothing leaks)."""
    san = ToolMarkupSanitizer()
    clean_prefix = "The answer is 42."
    full = clean_prefix + _DSML + "tool_calls>"
    # Split right in the middle of the marker.
    split_at = len(clean_prefix) + len(_DSML) // 2
    first = san.feed(full[:split_at])
    second = san.feed(full[split_at:])
    tail = san.finish()
    combined = first + second + tail
    assert combined == clean_prefix
    assert _DSML not in combined
    assert "tool_calls" not in combined


def test_held_back_prefix_flushed_when_not_a_marker() -> None:
    """A trailing fragment that looks like a marker prefix but isn't is flushed."""
    san = ToolMarkupSanitizer()
    # Ends with `<｜` which COULD start a marker — held back...
    first = san.feed("Trailing edge <｜")
    # ...then the next chunk reveals it's ordinary text, so it must be emitted.
    second = san.feed(" not a tool.")
    tail = san.finish()
    assert (first + second + tail) == "Trailing edge <｜ not a tool."


def test_native_deepseek_calls_marker_truncates() -> None:
    """The DeepSeek-native `<｜tool▁calls▁begin｜>` marker truncates too."""
    san = ToolMarkupSanitizer()
    out = san.feed(f"Clean.{_NATIVE_CALLS}stuff")
    assert out == "Clean."
    assert san.truncated is True


def test_native_deepseek_call_singular_marker_truncates() -> None:
    """The singular `<｜tool▁call▁begin｜>` marker truncates too."""
    san = ToolMarkupSanitizer()
    out = san.feed(f"Clean.{_NATIVE_CALL}stuff")
    assert out == "Clean."
    assert san.truncated is True


def test_marker_at_very_start_yields_empty() -> None:
    """A leak with no clean prefix yields no answer at all."""
    san = ToolMarkupSanitizer()
    assert san.feed(f"{_DSML}tool_calls>") == ""
    assert san.finish() == ""
    assert san.truncated is True


def test_empty_and_finish_only() -> None:
    """Empty feeds and a bare finish are well-behaved (no crash, empty out)."""
    san = ToolMarkupSanitizer()
    assert san.feed("") == ""
    assert san.finish() == ""

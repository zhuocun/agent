"""Streaming-safe sanitizer for leaked tool-call markup in ANSWER content.

Belt-and-braces safety net for the web-search path. The agentic tool loop in
`openai.py` is the real fix (it keeps the `web_search` schema advertised across
rounds so the OpenAI-compatible endpoint parses tool calls into STRUCTURED
`delta.tool_calls` instead of leaking them as text). But on the final, capped
round we force `tool_choice="none"`, and a stubborn model can still emit raw
tool-call special tokens into `delta.content`. This sanitizer scrubs that out of
the answer stream so users never see garbage like:

    <｜｜DSML｜｜tool_calls>\n<｜｜DSML｜｜invoke name="web_search">...

Design (streaming-safe):
- We feed CONTENT deltas (never `reasoning_content`) through `feed(...)`.
- Once a tool-call START marker appears, we STOP emitting any further content as
  answer (truncate there). Legitimate answers never contain these markers, so a
  hard truncate is safe and simple.
- A marker can split across chunk boundaries, so we hold back a small TAIL that
  could be the prefix of a start marker, and only emit confirmed-clean text. The
  held-back tail is flushed on `finish()` once we know no marker followed.

Markers handled (start markers only — that's all we need to detect a leak):
- ``<｜｜DSML｜｜``           the captured prod leak; ``｜`` is U+FF5C (fullwidth
                              vertical bar).
- ``<｜tool▁calls▁begin｜>``  DeepSeek-native tool-call block open; ``▁`` is
- ``<｜tool▁call▁begin｜>``   U+2581 (lower one-eighth block), ``｜`` is U+FF5C.

We anchor precisely on these sequences so ordinary text/code/markdown that
merely contains ``<``, ``|``, or even a bare ``<｜`` (not followed by a tool
token) passes through untouched.
"""

from __future__ import annotations

# Fullwidth vertical bar U+FF5C and the DeepSeek "▁" U+2581 used in native
# special tokens. Spelled out as escapes so the source stays ASCII-safe and the
# exact code points are unambiguous.
_FW_BAR = "｜"  # ｜
_USCORE = "▁"  # ▁

# Exact tool-call START markers. Order does not matter for detection; we scan
# for the earliest occurrence of any of them.
_START_MARKERS: tuple[str, ...] = (
    f"<{_FW_BAR}{_FW_BAR}DSML{_FW_BAR}{_FW_BAR}",  # <｜｜DSML｜｜
    f"<{_FW_BAR}tool{_USCORE}calls{_USCORE}begin{_FW_BAR}>",  # <｜tool▁calls▁begin｜>
    f"<{_FW_BAR}tool{_USCORE}call{_USCORE}begin{_FW_BAR}>",  # <｜tool▁call▁begin｜>
)

# Longest marker length — used to bound how much trailing text we must hold back
# as a possible split-across-chunks marker prefix.
_MAX_MARKER_LEN = max(len(m) for m in _START_MARKERS)


def _longest_suffix_that_is_marker_prefix(text: str) -> int:
    """Length of the longest suffix of `text` that is a strict prefix of a marker.

    Used to decide how much trailing text to hold back: if the buffer ends with
    something that could be the beginning of a start marker once the next chunk
    arrives, we must not emit it yet. Returns 0 when no suffix is a marker prefix.
    Only proper (non-full) prefixes count — a full marker is handled as a hit by
    the caller before this is consulted.
    """
    # The relevant suffix can be at most (longest_marker - 1) chars long.
    max_len = min(len(text), _MAX_MARKER_LEN - 1)
    for length in range(max_len, 0, -1):
        suffix = text[len(text) - length :]
        for marker in _START_MARKERS:
            if len(suffix) < len(marker) and marker.startswith(suffix):
                return length
    return 0


class ToolMarkupSanitizer:
    """Streaming-safe scrubber: emit clean answer text, truncate at any leak.

    Usage::

        san = ToolMarkupSanitizer()
        for chunk in content_deltas:
            clean = san.feed(chunk)
            if clean:
                yield AnswerDelta(text=clean)
        tail = san.finish()
        if tail:
            yield AnswerDelta(text=tail)

    Once a start marker is seen, `truncated` flips True and all subsequent output
    (this call's remainder and every later `feed`/`finish`) is suppressed.
    """

    def __init__(self) -> None:
        self._buf = ""
        self.truncated = False

    def feed(self, text: str) -> str:
        """Add `text`; return the confirmed-clean portion safe to emit now."""
        if self.truncated or not text:
            return ""
        self._buf += text
        # If a complete marker is present, emit everything before it and stop.
        hit = self._earliest_marker_index()
        if hit is not None:
            clean = self._buf[:hit]
            self._buf = ""
            self.truncated = True
            return clean
        # No full marker yet. Hold back only a trailing slice that could still
        # become a marker once more text arrives; emit the rest.
        hold = _longest_suffix_that_is_marker_prefix(self._buf)
        if hold == 0:
            out = self._buf
            self._buf = ""
            return out
        out = self._buf[: len(self._buf) - hold]
        self._buf = self._buf[len(self._buf) - hold :]
        return out

    def finish(self) -> str:
        """Flush any held-back tail. Safe to emit — no marker followed it."""
        if self.truncated:
            return ""
        out = self._buf
        self._buf = ""
        return out

    def _earliest_marker_index(self) -> int | None:
        """Index of the earliest start-marker occurrence in the buffer, or None."""
        best: int | None = None
        for marker in _START_MARKERS:
            idx = self._buf.find(marker)
            if idx != -1 and (best is None or idx < best):
                best = idx
        return best

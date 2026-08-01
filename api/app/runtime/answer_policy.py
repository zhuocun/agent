"""One neutral owner of answer emptiness, retry copy, and markup scrubbing.

Every layer that decides "did this turn produce a written answer?" reads this
module: the streaming handler's done-path guard, the agent-loop backstop, the
OpenAI-compatible provider relay, and the agentic orchestrator. It lives under
`app.runtime` rather than `app.streaming` (its previous home) or
`app.providers` (which owned the scrubber) because providers, tools, and
agentic code are all consumers — importing the policy upward from the streaming
layer made the delivery layer a dependency of the engines feeding it.

Two responsibilities, deliberately in one module because the first is defined in
terms of the second:

1. **Emptiness + retry copy.** `main_answer_is_empty` is the ONE backend
   definition of "this turn produced no written main answer." It mirrors the FE
   `stripToolMarkup` + trim arbiter (`web/src/lib/strip-tool-markup.ts` /
   `resolveMainBubbleText`) by scrubbing leaked tool-call markup before
   trimming, so a markup-only completion counts as empty on BOTH sides. This
   closes the live gap on the unsanitized Anthropic provider
   (`app/providers/anthropic.py` yields raw `AnswerDelta` with no
   `ToolMarkupSanitizer`) and any future provider that skips the sanitizer:
   non-empty raw markup would pass a bare `.strip()` guard (BE thinks it
   answered) yet be stripped to empty by the FE, firing the dead-end note.
2. **Generic tool-markup scrubbing.** `strip_tool_markup` /
   `contains_tool_markup` / `ToolMarkupSanitizer` are provider-independent: the
   markers are model special tokens, and the emptiness arbiter, the planner
   parser, and the OpenAI stream all scrub with the same rules.
"""

from __future__ import annotations

# Emitted when a turn reaches `status=done` without non-whitespace main answer
# text after tool/subagent/reasoning activity (or on a pathological empty turn).
# Reused by the handler guard, agent loop backstop, OpenAI web-search relay,
# and agentic single-mode orchestrator so fallback text stays consistent.
EMPTY_REPLY_FALLBACK = (
    "I finished processing but didn't produce a written reply. "
    "Please try again or rephrase your question."
)

# Soft system nudge appended to the retry pass that fires when a turn would end
# empty (see `app/tools/agent_loop.py` / `app/streaming/empty_reply_retry.py`).
# It is gated to genuinely-empty prior passes ONLY — never the reserved
# tool-exhaustion final pass, whose "you produced no answer" would be false. The
# base copy is JSON-safe (no "plain text" clause) so it stays valid when the turn
# requested structured output; the plain-prose clause is appended ONLY when no
# `response_format` was requested (see `empty_reply_retry_nudge`).
EMPTY_REPLY_RETRY_NUDGE = (
    "Your previous attempt did not produce a written answer. Provide your best "
    "final answer to the user's request now. Do not call tools."
)

_EMPTY_REPLY_RETRY_PLAIN_PROSE_CLAUSE = " Respond in plain prose."

# Fullwidth vertical bar U+FF5C and the DeepSeek "▁" U+2581 used in native
# special tokens. Spelled out as escapes so the source stays ASCII-safe and the
# exact code points are unambiguous.
_FW_BAR = "｜"  # ｜
_USCORE = "▁"  # ▁

# Exact tool-call START markers. Order does not matter for detection; we scan
# for the earliest occurrence of any of them.
#
# - ``<｜｜DSML｜｜``           the captured prod leak.
# - ``<｜tool▁calls▁begin｜>``  DeepSeek-native tool-call block open.
# - ``<｜tool▁call▁begin｜>``   DeepSeek-native single-call open.
#
# We anchor precisely on these sequences so ordinary text/code/markdown that
# merely contains ``<``, ``|``, or even a bare ``<｜`` (not followed by a tool
# token) passes through untouched.
_START_MARKERS: tuple[str, ...] = (
    f"<{_FW_BAR}{_FW_BAR}DSML{_FW_BAR}{_FW_BAR}",  # <｜｜DSML｜｜
    f"<{_FW_BAR}tool{_USCORE}calls{_USCORE}begin{_FW_BAR}>",  # <｜tool▁calls▁begin｜>
    f"<{_FW_BAR}tool{_USCORE}call{_USCORE}begin{_FW_BAR}>",  # <｜tool▁call▁begin｜>
)

# Longest marker length — used to bound how much trailing text we must hold back
# as a possible split-across-chunks marker prefix.
_MAX_MARKER_LEN = max(len(m) for m in _START_MARKERS)


def empty_reply_retry_nudge(*, response_format_requested: bool) -> str:
    """Assemble the retry nudge, response-format aware.

    Appends the plain-prose clause only when the turn did NOT request structured
    output; when a `response_format` is set that clause is omitted so the nudge
    never contradicts a JSON-mode instruction.
    """
    if response_format_requested:
        return EMPTY_REPLY_RETRY_NUDGE
    return EMPTY_REPLY_RETRY_NUDGE + _EMPTY_REPLY_RETRY_PLAIN_PROSE_CLAUSE


def main_answer_is_empty(text: str) -> bool:
    """Whether `text` carries no written main answer (markup-aware).

    Strips leaked tool-call markup (`strip_tool_markup`) BEFORE trimming so a
    markup-only completion counts as empty — matching what the FE renders. This
    is the single BE source of truth for main-answer emptiness.
    """
    return not strip_tool_markup(text).strip()


def _earliest_marker_index(text: str) -> int | None:
    """Index of the earliest start-marker occurrence in `text`, or None."""
    best: int | None = None
    for marker in _START_MARKERS:
        idx = text.find(marker)
        if idx != -1 and (best is None or idx < best):
            best = idx
    return best


def contains_tool_markup(text: str) -> bool:
    """True when `text` contains any tool-call START marker.

    Non-streaming counterpart to `ToolMarkupSanitizer` for callers holding a
    complete string (no chunk-boundary concerns). Legitimate answers never
    contain these markers, so a hit means leaked tool-call markup is present.
    """
    return _earliest_marker_index(text) is not None


def strip_tool_markup(text: str) -> str:
    """Return `text` truncated at the first tool-call START marker.

    Non-streaming counterpart to `ToolMarkupSanitizer`: for a complete string,
    everything from the first start marker onward (the leaked tool-call block)
    is dropped. Returns `text` unchanged when no marker is present.
    """
    hit = _earliest_marker_index(text)
    return text if hit is None else text[:hit]


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

    Belt-and-braces safety net for the web-search path. The agentic tool loop in
    `providers/openai.py` is the real fix (it keeps the `web_search` schema
    advertised across rounds so the OpenAI-compatible endpoint parses tool calls
    into STRUCTURED `delta.tool_calls` instead of leaking them as text). But on
    the final, capped round we force `tool_choice="none"`, and a stubborn model
    can still emit raw tool-call special tokens into `delta.content`.

    Usage::

        san = ToolMarkupSanitizer()
        for chunk in content_deltas:
            clean = san.feed(chunk)
            if clean:
                yield AnswerDelta(text=clean)
        tail = san.finish()
        if tail:
            yield AnswerDelta(text=tail)

    Feed CONTENT deltas only (never `reasoning_content`). Once a start marker is
    seen, `truncated` flips True and all subsequent output (this call's remainder
    and every later `feed`/`finish`) is suppressed: legitimate answers never
    contain these markers, so a hard truncate is safe and simple.
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
        hit = _earliest_marker_index(self._buf)
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

"""Shared streaming constants and the single BE emptiness arbiter.

`main_answer_is_empty` is the ONE backend definition of "this turn produced no
written main answer." It mirrors the FE `stripToolMarkup` + trim arbiter
(`web/src/lib/strip-tool-markup.ts` / `resolveMainBubbleText`) by scrubbing
leaked tool-call markup via `strip_tool_markup` before trimming, so a
markup-only completion counts as empty on BOTH sides. Every BE emptiness check
(handler done-path guard, agent-loop backstop, OpenAI web-search relay, agentic
orchestrator) routes through it. This closes the live gap on the unsanitized
Anthropic provider (`app/providers/anthropic.py` yields raw `AnswerDelta` with
no `ToolMarkupSanitizer`) and any future provider that skips the sanitizer:
non-empty raw markup would pass a bare `.strip()` guard (BE thinks it answered)
yet be stripped to empty by the FE, firing the dead-end note.
"""

from __future__ import annotations

from app.providers._tool_markup import strip_tool_markup

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

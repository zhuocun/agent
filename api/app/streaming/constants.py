"""Shared streaming constants."""

# Emitted when a turn reaches `status=done` without non-whitespace main answer
# text after tool/subagent/reasoning activity (or on a pathological empty turn).
# Reused by the handler guard, agent loop backstop, OpenAI web-search relay,
# and agentic single-mode orchestrator so fallback text stays consistent.
EMPTY_REPLY_FALLBACK = (
    "I finished processing but didn't produce a written reply. "
    "Please try again or rephrase your question."
)

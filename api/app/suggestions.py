"""Static prompt suggestion set, BE-owned for M0.

Mirrors the values in `web/src/lib/mock-data.ts:MOCK_SUGGESTIONS`. The FE will
consume these via bootstrap once `apiClient` lands; the mock will be deleted.
"""

from __future__ import annotations

from app.schemas.tier import PromptSuggestion

PROMPT_SUGGESTIONS: tuple[PromptSuggestion, ...] = (
    PromptSuggestion(
        id="s1",
        icon="debug",
        title="Debug a stack trace",
        prompt=(
            "I'm getting a TypeError in this function — here's the stack trace. "
            "Walk me through finding the root cause."
        ),
    ),
    PromptSuggestion(
        id="s2",
        icon="explain",
        title="Explain a concept",
        prompt=(
            "Explain the difference between optimistic and pessimistic locking, "
            "with a concrete example of when each is the right choice."
        ),
    ),
    PromptSuggestion(
        id="s3",
        icon="write",
        title="Draft a message",
        prompt=(
            "Help me write a clear, friendly message letting my team know a "
            "deadline is slipping by a few days and why."
        ),
    ),
    PromptSuggestion(
        id="s4",
        icon="analyze",
        title="Compare options",
        prompt=(
            "Compare REST, GraphQL, and gRPC for a mobile app backend. Give "
            "me a short table of trade-offs and a recommendation."
        ),
    ),
)


def list_suggestions() -> list[PromptSuggestion]:
    return list(PROMPT_SUGGESTIONS)

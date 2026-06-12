"""Deep-research planning: decompose a prompt into bounded sub-questions.

M2 ships a DETERMINISTIC decomposition so the fake provider and the test suite
have a stable contract: a prompt prefixed with ``DEEP_RESEARCH:`` is split on
``|`` into sub-questions, trimmed, de-blanked, and truncated to
``AGENTIC_MAX_WORKERS``. A prompt without the marker yields a single sub-question
(the whole prompt) so a deep-research turn always has at least one worker. A real
LLM-driven planner can replace `decompose` later without changing the
orchestrator contract.
"""

from __future__ import annotations

# Prefix that opts a prompt into explicit sub-question decomposition. The planner
# splits everything AFTER this prefix on `|`. The fake provider does NOT key on
# this marker itself — the orchestrator constructs per-worker prompts (see
# `worker_prompt`) that the fake recognizes.
DEEP_RESEARCH_PREFIX = "DEEP_RESEARCH:"

# Prefix of the per-worker prompt the orchestrator hands a worker subagent. The
# fake provider recognizes this to emit a deterministic worker answer; a real
# provider just sees a normal user turn asking the sub-question.
WORKER_PROMPT_PREFIX = "DEEP_RESEARCH_WORKER:"


def decompose(user_text: str, *, max_workers: int) -> list[str]:
    """Split a deep-research prompt into at most `max_workers` sub-questions.

    `DEEP_RESEARCH: a | b | c` → ``["a", "b", "c"]`` (trimmed, blanks dropped),
    capped at `max_workers`. A prompt without the marker (or with no non-blank
    parts after it) collapses to a single sub-question carrying the whole prompt,
    so the orchestrator always fans out to >= 1 worker.
    """
    bound = max(1, max_workers)
    if user_text.startswith(DEEP_RESEARCH_PREFIX):
        rest = user_text[len(DEEP_RESEARCH_PREFIX) :]
        parts = [segment.strip() for segment in rest.split("|")]
        sub_questions = [segment for segment in parts if segment]
        if sub_questions:
            return sub_questions[:bound]
    return [user_text]


def worker_prompt(index: int, sub_question: str) -> str:
    """Build the per-worker prompt for sub-question `index`.

    The fake provider keys on `WORKER_PROMPT_PREFIX` (`DEEP_RESEARCH_WORKER:n:`)
    to emit a deterministic per-worker answer; a real provider reads it as a plain
    request to answer `sub_question`. Tool output / sub-question text is untrusted
    — it only ever flows as this user-turn data, never spliced into instructions.
    """
    return f"{WORKER_PROMPT_PREFIX}{index}:{sub_question}"

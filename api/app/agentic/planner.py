"""Deep-research planning: decompose a prompt into bounded sub-questions.

Two decomposition strategies share one orchestrator contract:

- **Deterministic** (`decompose`): the fake-provider / test contract. A prompt
  prefixed with ``DEEP_RESEARCH:`` is split on ``|`` into sub-questions, trimmed,
  de-blanked, and truncated to ``AGENTIC_MAX_WORKERS``; a prompt without the
  marker yields a single sub-question (the whole prompt). Stable and provider-
  free, so the fake provider and the test suite have a fixed contract.
- **Model-driven** (`build_planner_prompt` + `parse_plan`): the real-provider
  path. The orchestrator runs a bounded `run_agent_loop` over the planner prompt
  and parses the model's reply into sub-questions, so a real deep-research turn
  fans out WITHOUT the user having to type the ``DEEP_RESEARCH:`` marker.

SECURITY: the user's request is the only instruction surface here. Sub-question
text is carried into worker / synthesis prompts as user-turn DATA (appended after
a fixed instruction), never spliced into instructions — the same untrusted-output
discipline the tool seam uses.
"""

from __future__ import annotations

# Prefix that opts a prompt into explicit sub-question decomposition. The planner
# splits everything AFTER this prefix on `|`. The fake provider does NOT key on
# this marker itself — the orchestrator constructs per-worker prompts (see
# `worker_prompt`) that the fake recognizes.
DEEP_RESEARCH_PREFIX = "DEEP_RESEARCH:"

# Prefix of the per-worker prompt the orchestrator hands a worker subagent on the
# SCAFFOLDED (fake-provider) path. The fake provider recognizes this to emit a
# deterministic worker answer; it must NEVER reach a real provider (a real worker
# gets the clean instruction built by `worker_prompt(scaffolded=False)`).
WORKER_PROMPT_PREFIX = "DEEP_RESEARCH_WORKER:"

# Fixed instruction wrapping a sub-question for a REAL worker subagent. The
# sub-question is appended as the trailing DATA of a normal user turn (the same
# pattern as title autogen / memory extraction), so untrusted sub-question text
# is never interpreted as a control instruction.
_WORKER_INSTRUCTION = (
    "You are a focused research sub-agent contributing to a larger answer. "
    "Research and answer ONLY the following question, thoroughly but concisely. "
    "Do not address anything beyond it.\n\nQuestion: "
)

# Fixed instruction asking a real provider to decompose the user's request into
# independent sub-questions. The request itself is appended as trailing DATA.
_PLANNER_INSTRUCTION = (
    "You are the planner for a deep-research run. Break the user's request into "
    "at most {n} focused, independent, non-overlapping sub-questions that together "
    "fully answer it. Return ONLY the sub-questions, one per line, with no "
    "numbering, bullets, preamble, or commentary. If the request is already a "
    "single focused question, return it unchanged as the only line.\n\n"
    "Request: "
)


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


def build_planner_prompt(user_text: str, *, max_workers: int) -> str:
    """Build the planner prompt for the real-provider decomposition pass.

    The model is asked to return one sub-question per line; `parse_plan` turns
    its reply back into a bounded list. `user_text` is appended as trailing DATA
    so the user's request is never treated as planner instructions.
    """
    bound = max(1, max_workers)
    return _PLANNER_INSTRUCTION.format(n=bound) + user_text


def parse_plan(reply: str, *, max_workers: int, fallback: str) -> list[str]:
    """Parse the planner model's reply into a bounded list of sub-questions.

    Each non-blank line is a sub-question; common leading bullet/numbering
    markers are stripped. Duplicates (case-insensitive) are dropped, the list is
    capped at `max_workers`, and an empty/unusable reply degrades to
    ``[fallback]`` (the whole request as a single sub-question) so a deep-research
    turn always fans out to >= 1 worker.
    """
    bound = max(1, max_workers)
    out: list[str] = []
    seen: set[str] = set()
    for raw in (reply or "").splitlines():
        cleaned = raw.strip().lstrip("-*•0123456789.)( \t").strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if len(out) >= bound:
            break
    return out or [fallback]


def worker_prompt(index: int, sub_question: str, *, scaffolded: bool) -> str:
    """Build the per-worker prompt for sub-question `index`.

    `scaffolded=True` (fake provider): emit the deterministic
    ``DEEP_RESEARCH_WORKER:n:<sub-question>`` marker the fake keys on. This must
    never reach a real provider. `scaffolded=False` (real provider): wrap the
    sub-question in a clean research instruction with NO scaffolding marker, so
    the provider sees a normal research request and the answer carries no
    internal markers. Either way the sub-question is untrusted DATA — it only
    flows as this user-turn payload, never spliced into instructions.
    """
    if scaffolded:
        return f"{WORKER_PROMPT_PREFIX}{index}:{sub_question}"
    return f"{_WORKER_INSTRUCTION}{sub_question}"

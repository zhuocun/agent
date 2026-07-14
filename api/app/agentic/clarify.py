"""Clarify-before-plan helpers for deep-research HITL.

Optional pause (``AGENTIC_CLARIFY_BEFORE_PLAN``) that asks 1–3 clarifying
questions before planning / admission / fan-out. Reuses the shipped
``awaiting_approval`` + ``toolApproval`` primitives via a pseudo-tool
(``agentic_plan_clarify``), mirroring plan-approval.
"""

from __future__ import annotations

# Fake-provider deterministic trigger: when this marker appears in the user
# text, clarify-before-plan pauses (flag must also be on). Real providers use
# the always-ask / ambiguity path instead.
CLARIFY_MARKER = "CLARIFY:"

# Fixed questions for the fake path when the marker is present (stable test
# contract). Real path uses a small fixed set.
_FAKE_CLARIFY_QUESTIONS: tuple[str, ...] = (
    "What specific aspect should the research prioritize?",
    "Any constraints (region, timeframe, audience) to apply?",
)

_REAL_CLARIFY_QUESTIONS: tuple[str, ...] = (
    "What is the primary goal or decision this research should inform?",
    "Any constraints (time period, geography, audience) we should respect?",
    "Which sources or perspectives matter most if trade-offs arise?",
)


def needs_clarify(*, user_text: str, scaffolded: bool) -> bool:
    """Whether a deep-research turn should pause for clarifying questions.

    Fake (scaffolded): only when ``CLARIFY:`` appears — deterministic marker.
    Real: always ask 1–3 questions when the flag is on (callers gate the flag).
    """
    text = (user_text or "").strip()
    if not text:
        return False
    if scaffolded:
        return CLARIFY_MARKER in text
    return True


def build_clarify_questions(*, user_text: str, scaffolded: bool) -> list[str]:
    """Return 1–3 clarifying questions for the pause card."""
    if scaffolded:
        # Optional: `CLARIFY: q1 | q2` overrides the fixed fake questions.
        if CLARIFY_MARKER in user_text:
            after = user_text.split(CLARIFY_MARKER, 1)[1]
            # Stop before a following DEEP_RESEARCH: plan marker.
            if "DEEP_RESEARCH:" in after:
                after = after.split("DEEP_RESEARCH:", 1)[0]
            custom = [p.strip() for p in after.split("|") if p.strip()]
            if custom:
                return custom[:3]
        return list(_FAKE_CLARIFY_QUESTIONS)
    return list(_REAL_CLARIFY_QUESTIONS[:3])


def augment_user_text_with_answers(user_text: str, answers: list[str]) -> str:
    """Append user clarifications as trailing DATA for planner / workers."""
    cleaned = [a.strip() for a in answers if isinstance(a, str) and a.strip()]
    if not cleaned:
        return user_text
    lines = ["", "Clarifications from the user:"]
    for index, answer in enumerate(cleaned, start=1):
        lines.append(f"{index}. {answer}")
    return user_text + "\n".join(lines)

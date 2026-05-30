"""Auto-tier complexity router (v0).

The `auto` tier is a request-time alias: the user delegates model choice to us.
Until now `auto` statically mapped to the `smart` model class (see
`tiers._AUTO_RESOLVES_TO`). This module replaces that static mapping with a
deterministic, no-extra-LLM-call complexity classifier that picks the CHEAPEST
capable concrete tier per turn and escalates only on detected complexity.

Design (PRD 05 §5.2 / §5.4 — routing is the margin lever: "classify easy
queries to the cheapest capable model; escalate only on explicit user choice or
detected complexity"; PRD §2.2.4 / §7.4 — "never silently downgrade"):

- Pure + synchronous + no I/O. Every signal is computed from the prompt text
  and the conversation depth alone, so the classifier is fully unit-testable
  and auditable.
- Default to `fast` (the cheapest capable tier). Escalate to `smart` on
  moderate complexity and to `pro` only on strong reasoning cues.
- v0 is INTENTIONALLY simple and auditable: a small set of additive integer
  signals crossing two thresholds. It is not a learned model and makes no
  provider call. The thresholds are documented constants below; tuning them is
  a follow-up, not a rewrite.

Honest surfacing: the caller compares the routed tier against the `auto`
baseline (`smart`). When the router picks a CHEAPER tier than the baseline
(i.e. `fast`), that is a downgrade and the caller emits an
`auto_downgrade` substitution so the served-vs-requested delta is visible on
the wire (the only auto-routing reason code the FE renders today — see
`web/src/lib/types.ts::SubstitutionReasonCode`). Picking the baseline or
escalating ABOVE it is not a downgrade and emits no substitution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.providers.protocol import ChatMessage as ProviderChatMessage
from app.schemas.common import ModelTierId

# --- Heuristic constants (v0) -------------------------------------------------
#
# Token estimate: chars / 4 is the usual rough English ratio. We never need
# exactness here — only an order-of-magnitude signal for "this is a long /
# context-heavy ask."
_CHARS_PER_TOKEN = 4

# Length signals (estimated tokens). A short small-talk turn sits well under
# the first threshold; a multi-paragraph spec blows past the second.
_LONG_PROMPT_TOKENS = 280
_VERY_LONG_PROMPT_TOKENS = 900

# Conversation-depth signal: long threads accumulate context the cheap tier
# handles worse. Count prior turns (history messages).
_DEEP_HISTORY_TURNS = 8

# Programming cues: fenced code blocks, or common language/keyword tokens. Code
# work biases toward the smart class even when short.
_CODE_FENCE_RE = re.compile(r"```")
_CODE_KEYWORD_RE = re.compile(
    r"\b(def|class|function|const|let|var|import|return|async|await|"
    r"public|private|static|void|struct|interface|select|insert|update|"
    r"delete|regex|stack ?trace|traceback|compile|null ?pointer|segfault)\b",
    re.IGNORECASE,
)
# Inline-code / shell-ish punctuation density (e.g. `foo()`, `a[b]`, `x => y`).
_CODE_PUNCT_RE = re.compile(r"(\)\s*\{|=>|::|\)\s*->|`[^`]+`)")

# Math / LaTeX cues: dollar-delimited math, LaTeX commands, or explicit math
# verbs. Math reasoning biases toward smart/pro.
_MATH_RE = re.compile(
    r"(\$\$?[^$]+\$\$?|\\[a-zA-Z]+\{|\\frac|\\sum|\\int|"
    r"\b(integral|derivative|theorem|equation|matrix|eigen\w*|probability)\b)",
    re.IGNORECASE,
)

# Strong multi-step / deep-reasoning cues. These escalate to `pro` because they
# explicitly ask the model to reason, not just answer.
_REASONING_RE = re.compile(
    r"\b(reason|think (step|through)|step[- ]by[- ]step|prove|proof|"
    r"derive|analy[sz]e|analysis|explain why|trade[- ]?offs?|"
    r"design (a|an|the)|architect|optimi[sz]e|debug|root cause|"
    r"compare and contrast)\b",
    re.IGNORECASE,
)

# Signal weights and thresholds. Score is additive; two cut points map the
# score to a tier. Kept tiny and legible on purpose.
_SMART_THRESHOLD = 2
_PRO_THRESHOLD = 4

# The `auto` baseline tier — the tier `auto` resolved to before real routing.
# Routing BELOW this (to a cheaper tier) is a downgrade we must surface.
AUTO_BASELINE_TIER: ModelTierId = "smart"

# Tier cost ordering, cheapest first. Used to decide "cheaper than baseline".
_TIER_COST_ORDER: tuple[ModelTierId, ...] = ("fast", "smart", "pro")


@dataclass(frozen=True)
class RoutedTier:
    """Result of routing an `auto` request to a concrete tier.

    `tier_id` is the chosen concrete tier (`fast` / `smart` / `pro`).
    `is_downgrade` is True iff the chosen tier is CHEAPER than the `auto`
    baseline (`smart`); the caller uses it to decide whether to emit an
    `auto_downgrade` substitution. `score` and `signals` are retained for
    logging / auditing the decision.
    """

    tier_id: ModelTierId
    is_downgrade: bool
    score: int
    signals: tuple[str, ...]


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (chars / 4). Order-of-magnitude only."""
    return len(text) // _CHARS_PER_TOKEN


def _is_cheaper_than(tier_id: ModelTierId, baseline: ModelTierId) -> bool:
    """True iff `tier_id` is strictly cheaper than `baseline` in cost order."""
    try:
        return _TIER_COST_ORDER.index(tier_id) < _TIER_COST_ORDER.index(baseline)
    except ValueError:  # pragma: no cover - defensive; both are concrete tiers
        return False


def route_auto(
    user_text: str,
    history: list[ProviderChatMessage] | None = None,
) -> RoutedTier:
    """Classify an `auto` turn into a concrete tier (v0 heuristic).

    Pure + synchronous. Computes a small additive complexity score from cheap
    text signals + conversation depth, then maps it across two thresholds:

        score < _SMART_THRESHOLD            -> fast  (cheapest capable)
        _SMART_THRESHOLD <= score < _PRO_*  -> smart (baseline)
        score >= _PRO_THRESHOLD             -> pro   (escalate)

    Default is `fast`: we only escalate on detected complexity, matching the
    PRD's "cheapest capable model; escalate only on detected complexity."
    """
    history = history or []
    text = user_text or ""

    signals: list[str] = []
    score = 0

    tokens = _estimate_tokens(text)
    if tokens >= _VERY_LONG_PROMPT_TOKENS:
        score += 2
        signals.append("very_long_prompt")
    elif tokens >= _LONG_PROMPT_TOKENS:
        score += 1
        signals.append("long_prompt")

    if _CODE_FENCE_RE.search(text):
        score += 2
        signals.append("code_fence")
    elif _CODE_KEYWORD_RE.search(text) or _CODE_PUNCT_RE.search(text):
        score += 1
        signals.append("code_cue")

    if _MATH_RE.search(text):
        score += 1
        signals.append("math")

    if _REASONING_RE.search(text):
        score += 2
        signals.append("reasoning_cue")

    if len(history) >= _DEEP_HISTORY_TURNS:
        score += 1
        signals.append("deep_history")

    if score >= _PRO_THRESHOLD:
        tier_id: ModelTierId = "pro"
    elif score >= _SMART_THRESHOLD:
        tier_id = "smart"
    else:
        tier_id = "fast"

    return RoutedTier(
        tier_id=tier_id,
        is_downgrade=_is_cheaper_than(tier_id, AUTO_BASELINE_TIER),
        score=score,
        signals=tuple(signals),
    )

"""Context-window compaction (FR-35).

A long conversation eventually exceeds the model's context window. Before a turn
is sent to the provider we estimate the history's token footprint and, when it
would crowd out the reply budget, compact it: keep the most recent turns
verbatim (a sliding window) and replace the older prefix with a short
provider-written summary. When no provider is available (or the summary call
fails) we fall back to the pure sliding window — dropping the older prefix — so
compaction never blocks a turn.

Two watermarks, not one. `should_compact` is the HIGH watermark; compaction
lands the result on a LOW watermark (`COMPACTION_TARGET_FRACTION` of the same
budget) instead of shaving just enough to get back under the threshold. A
compact-to-the-threshold pass re-trips on the very next turn with a different
prefix boundary, which misses the summary cache, bills another summarizer call
and rewrites the provider's cached prefix every turn. Clearing a batch of
tokens at once amortizes that cache write over the several turns it buys.

The cut is anchored to the LEADING prefix, not to the newest message. Nothing
persists a compaction: the route re-projects the whole conversation from the
database on every turn and compacts that projection afresh, so a boundary
measured backwards from the newest message slides forward by one turn every
turn. That hands `_boundary_cache_key` a different older prefix each time, and
the low watermark buys nothing on the production path — every turn past the
high watermark bills its own summarizer call. Quantizing the cut over the
oldest-forward running total (`COMPACTION_CUT_QUANTUM_FRACTION`) instead pins
it: appending messages leaves every existing prefix total untouched, so the
boundary only moves once growth crosses the next quantum, and the turns in
between hit the cache.

The token estimate is a deliberately cheap heuristic (~4 chars/token plus a
small per-message overhead): it never calls a tokenizer, so `should_compact` is
safe to run on every turn and is a no-op (returns False) for the common short
conversation, leaving that path byte-for-byte unchanged.

B13/B22: summarizer `complete()` usage is returned on `CompactionResult` so the
route can bill it; summaries are cached by compacted-boundary hash; the result
is remeasured and shrunk until it aims to fit the budget (including when the
recent window alone overflows).
"""

from __future__ import annotations

import hashlib
from bisect import bisect_left, bisect_right
from collections import OrderedDict
from dataclasses import dataclass

from app.config import get_settings
from app.providers.protocol import ChatMessage, CompleteResult, Provider, UsageUpdate
from app.providers.tiers import TierBinding

# Average characters per token for the cheap estimate. English text on the
# common tokenizers sits around 3.5-4.5 chars/token; 4 is a safe midpoint.
_CHARS_PER_TOKEN = 4
# Per-message overhead (role markers, separators) the wire adds around each
# message. A small fixed pad so a long run of tiny messages isn't undercounted.
_PER_MESSAGE_TOKEN_OVERHEAD = 4
# Floor on the verbatim window. Below two messages the immediate exchange the
# current turn depends on (a user turn and its reply) no longer survives, so the
# low watermark never shrinks the window past this; `_fit_to_budget` is still
# free to truncate text underneath it.
_MIN_KEEP_RECENT = 2
# Headroom (fraction of the context window) reserved on top of the reply budget
# so the estimate's slop + the system prefix + the current user turn don't push
# the real request over the window.
_HEADROOM_FRACTION = 0.1
# In-process summary cache keyed by (model_id, older-prefix digest). Bounded so
# a long-lived process cannot grow without limit.
_SUMMARY_CACHE_MAX = 64
_summary_cache: OrderedDict[str, str] = OrderedDict()

# The preservation contract a compaction has to honour: what survives the lossy
# transition is fixed, so the next turn can continue without the original text.
_SUMMARY_PROMPT = (
    "Summarize the earlier conversation below so a later turn can continue from "
    "the summary alone. Preserve it under these labels, in this order, omitting "
    "a label only when the conversation carries nothing for it:\n"
    "Objective: what the user is trying to achieve.\n"
    "Constraints: requirements, preferences, and limits stated so far.\n"
    "Decisions: each decision with the rationale that produced it.\n"
    "Open questions: what is still unresolved or was asked and not answered.\n"
    "Todos: work agreed on but not yet done.\n"
    "Evidence: findings, results, and data the conversation established.\n"
    "Pointers: file names, URLs, and identifiers needed to restore detail.\n"
    "Drop pleasantries and restatements. One or two terse lines per label; no "
    "preamble.\n\nConversation:\n"
)


@dataclass(frozen=True)
class CompactionResult:
    """Compacted history plus optional summarizer usage for route metering.

    HANDOFF (conversations route): when ``usage`` is set, bill/surface it on
    the turn (B13). Compaction no longer discards meters silently — the route
    owns folding this into attribution / ledger.
    """

    history: list[ChatMessage]
    usage: UsageUpdate | None = None
    cache_hit: bool = False
    compacted: bool = False


def estimate_tokens(history: list[ChatMessage]) -> int:
    """Cheaply estimate the token footprint of `history`.

    Heuristic only — ~4 chars/token plus a fixed per-message overhead. Never
    calls a tokenizer, so it's safe to call on every turn.
    """
    total = 0
    for message in history:
        total += len(message.text) // _CHARS_PER_TOKEN
        total += _PER_MESSAGE_TOKEN_OVERHEAD
    return total


def _compaction_budget(binding: TierBinding) -> int:
    """Tokens of history we allow before compacting.

    The window minus the reply budget (`max_output_tokens`) minus headroom for
    the system prefix, the current user turn, and the estimate's slop.
    """
    headroom = int(binding.context_window * _HEADROOM_FRACTION)
    budget = binding.context_window - binding.max_output_tokens - headroom
    return max(budget, 0)


def should_compact(binding: TierBinding, history: list[ChatMessage]) -> bool:
    """Whether `history` would crowd out the reply budget for `binding`.

    The HIGH watermark. False (the common case) for any conversation that
    comfortably fits, so the caller skips the summary call entirely.
    """
    return estimate_tokens(history) > _compaction_budget(binding)


def _target_budget(binding: TierBinding) -> int:
    """The LOW watermark a compaction pass lands on.

    A fraction of the same budget `should_compact` gates on, so one pass clears
    enough tokens for the following turns instead of re-tripping immediately.
    """
    return int(_compaction_budget(binding) * get_settings().compaction_target_fraction)


def _cut_quantum(binding: TierBinding) -> int:
    """Token granularity the compaction cut snaps to. At least 1 token."""
    fraction = get_settings().compaction_cut_quantum_fraction
    return max(int(_target_budget(binding) * fraction), 1)


def _select_recent(
    history: list[ChatMessage], binding: TierBinding
) -> list[ChatMessage]:
    """The verbatim tail left after cutting the oldest messages at a quantum.

    Anchored to the leading prefix: the cut index is the largest index whose
    leading prefix fits within `n * quantum` tokens, for the smallest positive
    `n` whose resulting tail fits under the low watermark. Both quantities are
    measured over the oldest-forward running total, so appending messages
    cannot move the cut — only growth past the next quantum can. That is what
    keeps the summarized older prefix (and therefore its cache key) identical
    across the turns of one quantum; a walk backwards from the newest message
    moved it on every turn instead.

    The tail this returns is already under the target unless `_MIN_KEEP_RECENT`
    floors it, which it does when even the immediate exchange overflows;
    `_fit_to_budget` stays the backstop that shrinks whatever the floor forces
    through.
    """
    target = _target_budget(binding)
    quantum = _cut_quantum(binding)

    # prefix_totals[i] == estimate_tokens(history[:i]), strictly increasing
    # because every message costs at least the per-message overhead.
    prefix_totals = [0]
    for message in history:
        prefix_totals.append(prefix_totals[-1] + estimate_tokens([message]))
    total = prefix_totals[-1]

    # The tail fits the target from `least` onwards, so the smallest admissible
    # `n` is the one whose cap reaches that prefix; the cut is then the last
    # index still under the cap, which can only be further along.
    least = bisect_left(prefix_totals, total - target)
    n = max((prefix_totals[least] + quantum - 1) // quantum, 1)
    cut = bisect_right(prefix_totals, n * quantum) - 1

    return history[min(cut, max(len(history) - _MIN_KEEP_RECENT, 0)) :]


def _render_transcript(history: list[ChatMessage]) -> str:
    """Render messages as a plain `Role: text` transcript for summarization."""
    return "\n".join(f"{message.role}: {message.text}" for message in history)


def _boundary_cache_key(model_id: str, older: list[ChatMessage]) -> str:
    digest = hashlib.sha256()
    digest.update(model_id.encode("utf-8"))
    digest.update(b"\0")
    for message in older:
        digest.update(message.role.encode("utf-8"))
        digest.update(b"\0")
        digest.update(message.text.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _cache_get(key: str) -> str | None:
    cached = _summary_cache.get(key)
    if cached is None:
        return None
    _summary_cache.move_to_end(key)
    return cached


def _cache_put(key: str, summary: str) -> None:
    _summary_cache[key] = summary
    _summary_cache.move_to_end(key)
    while len(_summary_cache) > _SUMMARY_CACHE_MAX:
        _summary_cache.popitem(last=False)


def _truncate_message_text(message: ChatMessage, max_chars: int) -> ChatMessage:
    if max_chars <= 0:
        return ChatMessage(role=message.role, text="")
    if len(message.text) <= max_chars:
        return message
    if max_chars <= 3:
        return ChatMessage(role=message.role, text=message.text[:max_chars])
    return ChatMessage(role=message.role, text=message.text[: max_chars - 3] + "...")


def _fit_to_budget(history: list[ChatMessage], budget: int) -> list[ChatMessage]:
    """Shrink ``history`` until it aims to fit ``budget`` tokens.

    Drops oldest messages first; if a single remaining message still overflows,
    truncates its text rather than passing an unbounded request through (B22).
    """
    if budget <= 0:
        return []
    result = list(history)
    while result and estimate_tokens(result) > budget:
        if len(result) > 1:
            result = result[1:]
            continue
        # One message still over budget — truncate text to the char budget.
        overhead = _PER_MESSAGE_TOKEN_OVERHEAD
        max_chars = max(0, (budget - overhead) * _CHARS_PER_TOKEN)
        result = [_truncate_message_text(result[0], max_chars)]
        break
    return result


async def compact_history(
    history: list[ChatMessage],
    binding: TierBinding,
    *,
    provider: Provider | None = None,
    model_id: str | None = None,
    api_key: str | None = None,
) -> CompactionResult:
    """Return a history that fits `binding`'s window, compacting if needed.

    No-op when `should_compact` is False — returns `history` unchanged. When
    compaction is needed: cut the oldest messages at a quantized prefix
    boundary, keep the tail verbatim, and replace the cut prefix with a single
    summary message. The summary is produced via `provider.complete`; if no
    provider/model is supplied or the call fails, fall back to the pure sliding
    window (older prefix dropped) so a turn is never blocked on summarization.

    Always remeasures and fits the result so a recent-window-only overflow
    cannot pass through unbounded (B22). Summarizer usage is returned for route
    billing (B13); summaries are cached by compacted-boundary digest.
    """
    if not should_compact(binding, history):
        return CompactionResult(history=history)

    target = _target_budget(binding)
    recent = _select_recent(history, binding)
    older = history[: len(history) - len(recent)]
    if not older:
        # Nothing to summarize — the recent window alone is over budget. Fit
        # rather than pass-through unbounded (B22).
        return CompactionResult(
            history=_fit_to_budget(recent, target),
            compacted=True,
        )

    summary: str | None = None
    usage: UsageUpdate | None = None
    cache_hit = False
    cache_key: str | None = None
    if provider is not None and model_id is not None:
        cache_key = _boundary_cache_key(model_id, older)
        cached = _cache_get(cache_key)
        if cached is not None:
            summary = cached
            cache_hit = True
        else:
            try:
                result: CompleteResult = await provider.complete(
                    model_id=model_id,
                    history=[],
                    user_text=_SUMMARY_PROMPT + _render_transcript(older),
                    api_key=api_key,
                )
                summary = result.text
                usage = result.usage
            except Exception:
                # Summarization is best-effort — fall through to the sliding window.
                summary = None

    cleaned = (summary or "").strip()
    if not cleaned:
        fitted = _fit_to_budget(recent, target)
        return CompactionResult(history=fitted, usage=usage, compacted=True)

    if cache_key is not None and not cache_hit:
        _cache_put(cache_key, cleaned)

    summary_message = ChatMessage(
        role="assistant",
        text=f"[Summary of earlier conversation]\n{cleaned}",
    )
    # The summary stands in for everything older, so it is the last thing to
    # give up room: the verbatim window absorbs whatever the summary leaves.
    room = target - estimate_tokens([summary_message])
    if room <= 0:
        fitted = _fit_to_budget([summary_message], target)
    else:
        fitted = [summary_message, *_fit_to_budget(recent, room)]
    return CompactionResult(
        history=fitted,
        usage=usage,
        cache_hit=cache_hit,
        compacted=True,
    )

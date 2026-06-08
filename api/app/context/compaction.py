"""Context-window compaction (FR-35).

A long conversation eventually exceeds the model's context window. Before a turn
is sent to the provider we estimate the history's token footprint and, when it
would crowd out the reply budget, compact it: keep the most recent N turns
verbatim (a sliding window) and replace the older prefix with a short
provider-written summary. When no provider is available (or the summary call
fails) we fall back to the pure sliding window — dropping the older prefix — so
compaction never blocks a turn.

The token estimate is a deliberately cheap heuristic (~4 chars/token plus a
small per-message overhead): it never calls a tokenizer, so `should_compact` is
safe to run on every turn and is a no-op (returns False) for the common short
conversation, leaving that path byte-for-byte unchanged.
"""

from __future__ import annotations

from app.providers.protocol import ChatMessage, Provider
from app.providers.tiers import TierBinding

# Average characters per token for the cheap estimate. English text on the
# common tokenizers sits around 3.5-4.5 chars/token; 4 is a safe midpoint.
_CHARS_PER_TOKEN = 4
# Per-message overhead (role markers, separators) the wire adds around each
# message. A small fixed pad so a long run of tiny messages isn't undercounted.
_PER_MESSAGE_TOKEN_OVERHEAD = 4
# Number of most-recent messages to keep verbatim when compacting. Enough to
# preserve the immediate back-and-forth the current turn depends on.
KEEP_LAST_N = 6
# Headroom (fraction of the context window) reserved on top of the reply budget
# so the estimate's slop + the system prefix + the current user turn don't push
# the real request over the window.
_HEADROOM_FRACTION = 0.1

_SUMMARY_PROMPT = (
    "Summarize the following earlier conversation so it can be used as context "
    "for what comes next. Keep durable facts, decisions, names, and open "
    "questions; drop pleasantries. Write a compact paragraph (no preamble, no "
    "bullet headers).\n\nConversation:\n"
)


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

    False (the common case) for any conversation that comfortably fits, so the
    caller skips the summary call entirely.
    """
    return estimate_tokens(history) > _compaction_budget(binding)


def _render_transcript(history: list[ChatMessage]) -> str:
    """Render messages as a plain `Role: text` transcript for summarization."""
    return "\n".join(f"{message.role}: {message.text}" for message in history)


async def compact_history(
    history: list[ChatMessage],
    binding: TierBinding,
    *,
    provider: Provider | None = None,
    model_id: str | None = None,
    api_key: str | None = None,
) -> list[ChatMessage]:
    """Return a history that fits `binding`'s window, compacting if needed.

    No-op when `should_compact` is False — returns `history` unchanged. When
    compaction is needed: keep the last `KEEP_LAST_N` messages verbatim and
    replace the older prefix with a single summary message. The summary is
    produced via `provider.complete`; if no provider/model is supplied or the
    call fails, fall back to the pure sliding window (older prefix dropped) so a
    turn is never blocked on summarization.
    """
    if not should_compact(binding, history):
        return history

    recent = history[-KEEP_LAST_N:] if KEEP_LAST_N > 0 else []
    older = history[: len(history) - len(recent)]
    if not older:
        # Nothing to summarize (the recent window alone is over budget). Send
        # the recent window as-is — there's no older prefix to drop or compact.
        return recent

    summary: str | None = None
    if provider is not None and model_id is not None:
        try:
            summary = await provider.complete(
                model_id=model_id,
                history=[],
                user_text=_SUMMARY_PROMPT + _render_transcript(older),
                api_key=api_key,
            )
        except Exception:
            # Summarization is best-effort — fall through to the sliding window.
            summary = None

    cleaned = (summary or "").strip()
    if not cleaned:
        # Sliding-window fallback: drop the older prefix entirely.
        return recent

    summary_message = ChatMessage(
        role="assistant",
        text=f"[Summary of earlier conversation]\n{cleaned}",
    )
    return [summary_message, *recent]

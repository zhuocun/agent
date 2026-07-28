"""Plain-chat empty-reply retry wrapper (Layer B).

Wraps a single raw provider stream (the non-tools, non-agentic chat path) so a
genuinely-empty first pass triggers ONE suppress-tools, answer-eliciting retry
before the handler's static ``EMPTY_REPLY_FALLBACK`` last resort fires. It
mirrors the agent loop exactly on the two things that must stay identical across
the two empty-retry paths:

- **Usage fold** via the shared ``make_usage_folder`` so both attempts bill into
  the single cumulative ``Complete`` (the handler reads ``final_usage`` off it).
- **Markup-drop** of markup-only / whitespace deltas while no written answer has
  been emitted, so leaked tool-call markup can't precede a fallback and get
  wiped by the FE truncate-from-first-marker scrub.

It emits NO static text itself — when both passes are empty the handler's
``_inject_empty_reply_fallback_if_needed`` injector remains the final net. The
terminal ``Complete`` carries the internal ``empty_retry`` /
``empty_retry_recovered`` analytics markers.

Wire safety: exactly one terminal ``Complete`` reaches the wire. The first
pass's blank ``Complete`` is deferred (usage folded, not relayed) and the retry
pass's ``Complete`` is suppressed; a single synthesized ``Complete`` closes the
turn. A non-empty first pass is a transparent pass-through (its ``Complete`` is
relayed and no retry runs).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.config import Settings
from app.providers.protocol import AnswerDelta, Complete, ProviderEvent
from app.streaming.constants import main_answer_is_empty
from app.tools.agent_loop import MakeStream, make_usage_folder


async def run_chat_with_empty_retry(
    make_stream: MakeStream,
    settings: Settings,
) -> AsyncIterator[ProviderEvent]:
    """Relay ``make_stream([], False)``, retrying once on a genuinely-empty pass.

    The caller only wraps the raw stream when
    ``settings.empty_reply_retry_enabled`` is True (otherwise it passes the raw
    stream straight through, byte-for-byte identical to a pre-retry build); the
    flag is re-checked here defensively.
    """
    fold_usage, reset_usage, get_cumulative = make_usage_folder()
    answer_emitted = False

    def _note(delta: AnswerDelta) -> None:
        nonlocal answer_emitted
        if not main_answer_is_empty(delta.text):
            answer_emitted = True

    # Pass 1: relay the raw stream, dropping markup-only deltas while empty and
    # deferring a blank terminal Complete.
    reset_usage()
    async for event in make_stream([], False):
        if isinstance(event, AnswerDelta):
            _note(event)
            if main_answer_is_empty(event.text) and not answer_emitted:
                continue
            yield event
            continue
        if isinstance(event, Complete):
            folded = fold_usage(event)
            if answer_emitted:
                # Non-empty first pass: transparent pass-through, no retry.
                yield folded
                return
            # Empty first pass: defer the blank Complete; fall through to retry.
            continue
        yield fold_usage(event)

    if answer_emitted:
        # First pass answered but sent no Complete (rare). Nothing to synthesize —
        # match the raw stream, which likewise ends without a Complete.
        return

    retry_ran = False
    if settings.empty_reply_retry_enabled:
        retry_ran = True
        reset_usage()
        async for event in make_stream([], True, answer_nudge=True):
            if isinstance(event, AnswerDelta):
                _note(event)
                if main_answer_is_empty(event.text) and not answer_emitted:
                    continue
                yield event
                continue
            if isinstance(event, Complete):
                # Fold usage but suppress — the single terminal Complete is
                # synthesized below with the markers.
                fold_usage(event)
                continue
            yield fold_usage(event)

    # One cumulative terminal Complete. No static text — the handler injector is
    # the last resort when both passes came back empty.
    yield Complete(
        usage=get_cumulative(),
        empty_retry=retry_ran,
        empty_retry_recovered=retry_ran and answer_emitted,
    )

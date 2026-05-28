"""Anthropic SDK adapter.

Maps `client.messages.stream(...)` events to our internal `ProviderEvent`s:

- `thinking` block → `ReasoningDelta` + a single `ReasoningDone` at block end.
- `text` block → `AnswerDelta`.
- `message_delta` carries `usage` as a running cumulative count (NOT a delta);
  we last-write-wins each event and emit a single final `UsageUpdate` +
  `Complete` once the `messages.stream` context closes.

Per PRD 07 §7 rule 7 (enforced in `pricing.py`), reasoning tokens bill at the
output rate; we map Anthropic's extended-thinking token count (if present)
into our canonical `reasoning_tokens` field. Cache token counts map cleanly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast

from anthropic import AsyncAnthropic

from app.providers.protocol import (
    AnswerDelta,
    ChatMessage,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    ReasoningDone,
    UsageUpdate,
)


def _safe_int(value: Any) -> int:
    """Coerce SDK usage fields (often `int | None`) to int."""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class AnthropicProvider:
    """Adapter over `anthropic.AsyncAnthropic.messages.stream(...)`."""

    def __init__(self, api_key: str, max_tokens: int = 16000):
        self._client = AsyncAnthropic(api_key=api_key)
        self._max_tokens = max_tokens

    async def stream(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
    ) -> AsyncIterator[ProviderEvent]:
        # Build messages: history + the current user turn.
        messages: list[dict[str, Any]] = [
            {"role": m.role, "content": m.text} for m in history
        ]
        messages.append({"role": "user", "content": user_text})

        # Last cumulative usage seen on `message_delta`. Anthropic emits the
        # running cumulative count on each message_delta, not deltas, so
        # last-write-wins captures the final tally without summation.
        input_tokens = 0
        output_tokens = 0
        reasoning_tokens = 0
        cached_input_tokens = 0

        # Track whether we're currently inside a thinking block so we can
        # emit exactly one ReasoningDone at block end.
        in_thinking = False

        async with self._client.messages.stream(
            model=model_id,
            max_tokens=self._max_tokens,
            messages=cast(Any, messages),
        ) as stream:
            async for event in stream:
                etype = getattr(event, "type", None)

                if etype == "content_block_start":
                    block = getattr(event, "content_block", None)
                    block_type = getattr(block, "type", None)
                    if block_type == "thinking":
                        in_thinking = True

                elif etype == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    dtype = getattr(delta, "type", None)
                    if dtype == "thinking_delta":
                        yield ReasoningDelta(text=getattr(delta, "thinking", ""))
                    elif dtype == "text_delta":
                        yield AnswerDelta(text=getattr(delta, "text", ""))

                elif etype == "content_block_stop":
                    if in_thinking:
                        yield ReasoningDone()
                        in_thinking = False

                elif etype == "message_delta":
                    usage = getattr(event, "usage", None)
                    if usage is not None:
                        input_tokens = _safe_int(getattr(usage, "input_tokens", None))
                        output_tokens = _safe_int(getattr(usage, "output_tokens", None))
                        cache_create = _safe_int(
                            getattr(usage, "cache_creation_input_tokens", None)
                        )
                        cache_read = _safe_int(
                            getattr(usage, "cache_read_input_tokens", None)
                        )
                        cached_input_tokens = cache_create + cache_read
                        # Optional extended-thinking token count. Field name
                        # is not stable across SDK versions; try a few.
                        r_tokens = (
                            getattr(usage, "thinking_tokens", None)
                            or getattr(usage, "reasoning_tokens", None)
                            or getattr(usage, "thinking_output_tokens", None)
                        )
                        if r_tokens is not None:
                            reasoning_tokens = _safe_int(r_tokens)

        # Stream context closed: emit final usage + complete.
        usage_update = UsageUpdate(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens,
        )
        yield usage_update
        yield Complete(usage=usage_update)

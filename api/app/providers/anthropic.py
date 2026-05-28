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
    """Adapter over `anthropic.AsyncAnthropic.messages.stream(...)`.

    Holds a default client built from the platform key. Per-request BYOK
    overrides build a fresh `AsyncAnthropic(api_key=...)` on the spot (the
    SDK is cheap to construct -- HTTP session is lazy). This keeps the
    default fast path identical to M1 while making BYOK opt-in per call.
    """

    def __init__(self, api_key: str, max_tokens: int = 16000):
        self._default_api_key = api_key
        self._client = AsyncAnthropic(api_key=api_key)
        self._max_tokens = max_tokens

    def _client_for(self, api_key: str | None) -> AsyncAnthropic:
        """Return the default client, or a fresh one bound to `api_key`.

        The default client is reused across requests for connection pooling;
        BYOK clients are throwaway and rely on the SDK's own connection
        management for that single call.
        """
        if api_key is None or api_key == self._default_api_key:
            return self._client
        return AsyncAnthropic(api_key=api_key)

    async def stream(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
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

        client = self._client_for(api_key)
        async with client.messages.stream(
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

    async def complete(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
    ) -> str:
        """Non-streaming variant. One `messages.create` call, collected text.

        Used by title autogen — small/fast tier, short max_tokens. Concatenates
        any `text` blocks in the SDK response and returns the joined string.
        Returns empty string on a response without a text block (defensive —
        the caller will swallow empty titles).
        """
        # Title-autogen calls are short; cap output tokens aggressively so a
        # runaway model can't burn a full max_tokens budget on a 5-word title.
        # The number is intentionally generous (5 words ~ a couple dozen
        # tokens) to leave headroom for unusual tokenizers.
        messages: list[dict[str, Any]] = [
            {"role": m.role, "content": m.text} for m in history
        ]
        messages.append({"role": "user", "content": user_text})

        client = self._client_for(api_key)
        response = await client.messages.create(
            model=model_id,
            max_tokens=64,
            messages=cast(Any, messages),
        )
        # `response.content` is a list of content blocks; we concatenate text
        # blocks (skip thinking / tool_use etc.). SDK shapes vary by version
        # so we duck-type defensively.
        texts: list[str] = []
        for block in getattr(response, "content", []) or []:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_val = getattr(block, "text", "")
                if isinstance(text_val, str):
                    texts.append(text_val)
        return "".join(texts).strip()

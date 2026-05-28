"""Deterministic fake provider for dev/tests.

Emits 2 short reasoning deltas, one `ReasoningDone`, 4 answer deltas, and a
final usage update. The answer text varies by `user_text` hash so distinct
inputs produce distinct outputs (idempotency tests need this).

Sleeps ~20ms between deltas so streaming is observable but tests stay fast.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator

from app.providers.protocol import (
    AnswerDelta,
    ChatMessage,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    ReasoningDone,
    UsageUpdate,
)

# Small bank of response templates. Hash the input to pick one deterministically.
_RESPONSE_TEMPLATES: tuple[tuple[str, str, str, str], ...] = (
    ("Sure", ", here's", " a quick", " answer."),
    ("Got", " it.", " Let me", " explain."),
    ("Yes", ", I can", " help with", " that."),
    ("Hmm", ", interesting", " — here's", " my take."),
    ("OK", ", thinking", " about that", " now."),
    ("Right", " — let's", " walk through", " it together."),
    ("Alright", ", here's", " what I", " think."),
    ("Sure thing", ". Here's", " a quick", " response."),
)


def _pick_template(user_text: str) -> tuple[str, str, str, str]:
    """Pick a template deterministically from the user text."""
    h = hashlib.sha256(user_text.encode("utf-8")).digest()
    idx = h[0] % len(_RESPONSE_TEMPLATES)
    return _RESPONSE_TEMPLATES[idx]


class FakeProvider:
    """In-process fake. No network. Deterministic per `user_text`."""

    def __init__(self, delay_ms: int = 20):
        self._delay = delay_ms / 1000.0

    async def stream(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
    ) -> AsyncIterator[ProviderEvent]:
        # Two short reasoning deltas, then done.
        await asyncio.sleep(self._delay)
        yield ReasoningDelta(text="Let me think")
        await asyncio.sleep(self._delay)
        yield ReasoningDelta(text="... OK")
        await asyncio.sleep(self._delay)
        yield ReasoningDone()

        # Four answer deltas varying by input.
        chunks = _pick_template(user_text)
        for chunk in chunks:
            await asyncio.sleep(self._delay)
            yield AnswerDelta(text=chunk)

        # Synthetic usage. Reasoning tokens stay nonzero so pricing tests
        # exercise the PRD 07 §7 rule 7 path.
        usage = UsageUpdate(
            input_tokens=50,
            output_tokens=100,
            reasoning_tokens=10,
            cached_input_tokens=0,
        )
        yield usage
        yield Complete(usage=usage)

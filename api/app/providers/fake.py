"""Deterministic fake provider for dev/tests.

Emits 2 short reasoning deltas, one `ReasoningDone`, 4 answer deltas, and a
final usage update. The answer text varies by `user_text` hash so distinct
inputs produce distinct outputs (idempotency tests need this).

Sleeps ~20ms between deltas so streaming is observable but tests stay fast.

`complete()` is the non-streaming variant — used by title autogen. It returns
a deterministic ~5-word title derived from the input hash; no sleeps so tests
can poll cheaply.

M4: forced fallback path. When `user_text` starts with `FORCE_FALLBACK:`, the
provider streams normally but the terminal `Complete` event carries
`substitution="provider_fallback"` plus a stubbed served (provider, model,
label) triple. Exercises the substitution emission seam end-to-end.

Forced mid-stream error: when `user_text` starts with `FORCE_ERROR:`, the
provider emits the reasoning block and a couple of answer deltas, then raises
mid-stream (before usage / Complete). Exercises the handler's provider-error
path: the client receives an `error` frame and no assistant row is persisted.

Forced rate limit: when `user_text` starts with `FORCE_RATE_LIMIT:`, the
provider raises a typed `AppError(RATE_LIMITED)` with `retryAfterMs` mid-stream,
mirroring how the real provider maps a 429. Exercises the handler surfacing a
typed provider error (code + retryAfterMs) on the wire.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator

from app.errors import AppError, ErrorEnvelope
from app.providers.protocol import (
    AnswerDelta,
    AttachmentPayload,
    ChatMessage,
    Complete,
    ProviderEvent,
    ReasoningDelta,
    ReasoningDone,
    Sources,
    StatusUpdate,
    ToolCall,
    ToolResult,
    UsageUpdate,
)
from app.search.fake import FakeSearchProvider
from app.search.protocol import SourceItem

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


# Small bank of 5-word title templates. Hash-pick a stem and append a
# stable noun derived from the input length so different inputs produce
# different titles deterministically (title-autogen tests need this).
_TITLE_STEMS: tuple[tuple[str, str, str, str, str], ...] = (
    ("Quick", "chat", "about", "the", "topic"),
    ("Friendly", "exchange", "covering", "your", "question"),
    ("Brief", "thread", "on", "your", "request"),
    ("Conversation", "exploring", "the", "given", "input"),
    ("Casual", "discussion", "around", "your", "prompt"),
    ("Helpful", "back-and-forth", "on", "your", "ask"),
    ("Short", "session", "answering", "your", "query"),
    ("Talk", "covering", "the", "user", "message"),
)


def _pick_template(user_text: str) -> tuple[str, str, str, str]:
    """Pick a template deterministically from the user text."""
    h = hashlib.sha256(user_text.encode("utf-8")).digest()
    idx = h[0] % len(_RESPONSE_TEMPLATES)
    return _RESPONSE_TEMPLATES[idx]


def _pick_title(user_text: str) -> str:
    """Pick a 5-word title deterministically from the user text."""
    h = hashlib.sha256(user_text.encode("utf-8")).digest()
    idx = h[1] % len(_TITLE_STEMS)
    return " ".join(_TITLE_STEMS[idx])


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
        attachments: list[AttachmentPayload] | None = None,
        api_key: str | None = None,
        thinking: bool | None = None,
        reasoning_effort: str | None = None,
        web_search: bool = False,
    ) -> AsyncIterator[ProviderEvent]:
        # `thinking` / `reasoning_effort` are accepted to satisfy the Provider
        # Protocol but ignored — the fake's output is fixed/deterministic.
        # Two short reasoning deltas, then done.
        await asyncio.sleep(self._delay)
        yield ReasoningDelta(text="Let me think")
        await asyncio.sleep(self._delay)
        yield ReasoningDelta(text="... OK")
        await asyncio.sleep(self._delay)
        yield ReasoningDone()

        # Web-search path: emit the status line + deterministic sources between
        # the reasoning block and the answer, mirroring the real provider's
        # event order (StatusUpdate active → done → Sources → grounded answer).
        # Deterministic via FakeSearchProvider so e2e/tests can assert exact
        # shape. When `web_search=False` this whole block is skipped and the
        # fake's output is byte-for-byte unchanged.
        search_items: list[SourceItem] = []
        if web_search:
            await asyncio.sleep(self._delay)
            yield ToolCall(
                id="fake_web_search_1",
                name="web_search",
                label="Search web",
                status="running",
                input={"query": user_text},
            )
            yield StatusUpdate(label="Searching the web…", state="active")
            search_items = await FakeSearchProvider().search(user_text, max_results=3)
            await asyncio.sleep(self._delay)
            yield StatusUpdate(label="Searching the web…", state="done")
            yield Sources(items=search_items)
            yield ToolResult(
                tool_call_id="fake_web_search_1",
                name="web_search",
                label="Search web",
                status="succeeded",
                summary=f"{len(search_items)} sources",
                output={"results": [item.model_dump() for item in search_items]},
            )

        # Four answer deltas varying by input. On a web_search turn, prepend a
        # citation-bearing delta so the grounded answer references the sources.
        if web_search and search_items:
            await asyncio.sleep(self._delay)
            yield AnswerDelta(text="Based on the sources [1][2], ")
        if attachments:
            names = ", ".join(attachment.name for attachment in attachments)
            await asyncio.sleep(self._delay)
            yield AnswerDelta(text=f"Received attachments: {names}. ")
            extracted = [
                attachment.extracted_text
                for attachment in attachments
                if attachment.extracted_text
            ]
            if extracted:
                await asyncio.sleep(self._delay)
                yield AnswerDelta(text=f"Extracted text: {extracted[0][:120]}. ")
        chunks = _pick_template(user_text)
        for i, chunk in enumerate(chunks):
            await asyncio.sleep(self._delay)
            yield AnswerDelta(text=chunk)
            # Forced mid-stream error: raise after a couple of answer deltas,
            # before usage / Complete. The handler surfaces this as an `error`
            # frame and persists nothing for the turn.
            if user_text.startswith("FORCE_ERROR:") and i >= 1:
                raise RuntimeError("forced provider error")
            if user_text.startswith("FORCE_RATE_LIMIT:") and i >= 1:
                # Mirror the real provider mapping a 429 to a typed AppError so
                # the handler surfaces RATE_LIMITED + retryAfterMs to the wire.
                raise AppError(
                    ErrorEnvelope(
                        code="RATE_LIMITED",
                        severity="error",
                        title="Rate limited",
                        body="The model provider is rate-limiting requests. Please retry shortly.",
                        retry_after_ms=4200,
                    ),
                    status_code=429,
                )

        # Synthetic usage. Reasoning tokens stay nonzero so pricing tests
        # exercise the PRD 07 §7 rule 7 path.
        usage = UsageUpdate(
            input_tokens=50,
            output_tokens=100,
            reasoning_tokens=10,
            cached_input_tokens=0,
        )
        yield usage
        # M4 forced-fallback path. Marker prefix in user_text flips the
        # terminal Complete event into the substitution shape. Stubbed served
        # (provider, model, label) triple — what the handler would have got
        # back from a real provider-fallback router. The wire still only
        # carries `reasonCode` + `reasonText` (per FE shape); the served
        # triple is bookkeeping for future use.
        if user_text.startswith("FORCE_FALLBACK:"):
            yield Complete(
                usage=usage,
                substitution="provider_fallback",
                substituted_provider="fallback-provider",
                substituted_model="fallback-model",
                substituted_display_label="Fallback Model",
            )
        else:
            yield Complete(usage=usage)

    async def complete(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
    ) -> str:
        """Non-streaming variant. Deterministic ~5-word title from `user_text`.

        Used by title autogen — must return fast (no sleeps) so the detached
        `asyncio.create_task(...)` resolves within a polling window in tests.
        """
        return _pick_title(user_text)

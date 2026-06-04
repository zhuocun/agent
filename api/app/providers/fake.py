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

Forced provider-fallback retry: when `user_text` starts with
`FORCE_FALLBACK_RETRY:`, the provider raises a retryable
`AppError(PROVIDER_UPSTREAM, 503)` BEFORE yielding any event — but ONLY on the
primary route (`model_id != "fake-fallback"`). The route selects a fallback
binding with `model_id="fake-fallback"`, on which this marker is a no-op, so the
handler's one-shot pre-token fallback retries onto it and streams a normal
answer carrying a `provider_fallback` substitution. Distinct from
`FORCE_RATE_LIMIT:`, which raises AFTER deltas (post-token) and therefore must
NOT be retried.

Mermaid diagram: when `user_text` starts with `MERMAID:`, the provider emits the
usual reasoning block then a single well-formed, closed fenced ```mermaid block
as its answer (instead of the templated text). Exercises the FE's Streamdown
mermaid plugin rendering a diagram from streamed markdown end-to-end.

Continue a stopped turn: when `user_text` is the continuation instruction the
route sends to extend a Stopped turn (it CONTAINS the marker phrase
"Continue your previous response"), the provider emits the usual reasoning block
then a distinctive deterministic answer beginning with "…continued: " so e2e /
BE tests can assert the continuation streamed as a NEW assistant bubble. The
prior partial answer lives in the replayed `history` (trailing assistant turn),
not in `user_text`.

Slow stream: when `user_text` starts with `SLOW:`, the provider emits the usual
reasoning block then ~40 non-empty answer deltas at 50ms each, so an e2e can
deterministically catch the stream mid-flight (e.g. to click Stop and commit a
non-empty `stopped` partial). Without it the default stream is too fast to stop.

Backend tool calling (only when `settings.tools_enabled` is True — otherwise
these markers are ignored and the provider streams a normal templated answer, so
the flag-off path is byte-for-byte unchanged):

- `TOOL_TIME:` exercises the AUTO (no-approval) tool path. Round 1 emits the
  reasoning block then a bare `ToolCall(name="get_current_time", status="running")`
  and ENDS (no answer / no `Complete`). The agent loop executes the tool, emits
  the `ToolResult`, and re-invokes this stream with the result appended to
  `history` (prefixed by `agent_loop.TOOL_FEEDBACK_SENTINEL`); seeing that
  sentinel, round 2 emits a grounded answer + `Complete`.
- `TOOL_APPROVE:` exercises the HITL approval pause. It emits the reasoning block
  then `ToolCall(id="fake_cal_1", name="calendar_create_event",
  status="awaiting_approval", approval_state="pending", input={"title": ...})`
  followed by `AwaitingApproval(tool_call_id="fake_cal_1")` and RETURNS (no
  `Complete`) — the PAUSE. On the RESUME turn the route seeds the decision and
  sends a continuation `user_text` containing "Tool approved:" / "Tool denied:";
  the fake then emits the post-tool answer ("…tool approved: …" / "…tool denied:
  …") + `Complete`. The seeded `tool_result` is emitted by the handler before
  this stream runs.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator

from app.config import get_settings
from app.errors import AppError, ErrorEnvelope
from app.providers.protocol import (
    AnswerDelta,
    AttachmentPayload,
    AwaitingApproval,
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
from app.tools.agent_loop import TOOL_FEEDBACK_SENTINEL

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
        supports_vision: bool = True,
    ) -> AsyncIterator[ProviderEvent]:
        # `thinking` / `reasoning_effort` / `supports_vision` are accepted to
        # satisfy the Provider Protocol but ignored — the fake's output is
        # fixed/deterministic and it never emits native attachment blocks.
        # Forced provider-fallback retry: when `user_text` starts with
        # `FORCE_FALLBACK_RETRY:`, raise a retryable upstream error BEFORE
        # yielding ANYTHING — but ONLY on the primary route. The route hands the
        # fallback a binding whose `model_id == "fake-fallback"`, so the retry
        # streams a normal answer and the handler emits a `provider_fallback`
        # substitution. Exercises the handler's pre-token fallback seam E2E.
        if user_text.startswith("FORCE_FALLBACK_RETRY:") and model_id != "fake-fallback":
            raise AppError(
                ErrorEnvelope(
                    code="PROVIDER_UPSTREAM",
                    severity="error",
                    title="Provider error",
                    body="The model provider returned an error. Please try again.",
                ),
                status_code=503,
            )
        # Backend tool calling. Gated on `tools_enabled` so the flag-off path is
        # byte-for-byte unchanged (the markers fall through to the normal answer).
        tools_on = get_settings().tools_enabled
        # A feedback round = the agent loop re-invoked us with tool results
        # appended to history. We skip the reasoning block on those continuation
        # rounds so reasoning isn't duplicated across rounds.
        has_tool_feedback = any(
            TOOL_FEEDBACK_SENTINEL in message.text for message in history
        )

        # Two short reasoning deltas, then done (skipped on a tool-feedback round).
        if not has_tool_feedback:
            await asyncio.sleep(self._delay)
            yield ReasoningDelta(text="Let me think")
            await asyncio.sleep(self._delay)
            yield ReasoningDelta(text="... OK")
            await asyncio.sleep(self._delay)
            yield ReasoningDone()

        if tools_on and user_text.startswith("TOOL_TIME:"):
            if not has_tool_feedback:
                # Round 1: request the auto tool, then end the round (no answer /
                # no Complete) so the agent loop executes it and re-invokes us.
                await asyncio.sleep(self._delay)
                yield ToolCall(
                    id="fake_time_1",
                    name="get_current_time",
                    label="Get current time",
                    status="running",
                    input={},
                )
                return
            # Round 2: the loop fed the tool result back via history. Answer.
            await asyncio.sleep(self._delay)
            yield AnswerDelta(text="The current time was retrieved by the tool.")
            usage = UsageUpdate(
                input_tokens=50,
                output_tokens=100,
                reasoning_tokens=10,
                cached_input_tokens=0,
            )
            yield usage
            yield Complete(usage=usage)
            return

        if tools_on and user_text.startswith("TOOL_APPROVE:"):
            # Approval-gated tool: emit the pending tool_call, then the pause
            # sentinel, and RETURN (no Complete). The handler ends the turn in
            # `awaiting_approval`; a resume POST applies the decision.
            await asyncio.sleep(self._delay)
            yield ToolCall(
                id="fake_cal_1",
                name="calendar_create_event",
                label="Create calendar event",
                status="awaiting_approval",
                approval_state="pending",
                input={"title": "Planning review"},
            )
            yield AwaitingApproval(tool_call_id="fake_cal_1")
            return

        if tools_on and "Tool approved:" in user_text:
            # Resume → approve. The handler already emitted the approved
            # tool_result; we emit the post-tool answer + Complete.
            await asyncio.sleep(self._delay)
            yield AnswerDelta(text="…tool approved: the calendar event was created.")
            usage = UsageUpdate(
                input_tokens=50,
                output_tokens=100,
                reasoning_tokens=10,
                cached_input_tokens=0,
            )
            yield usage
            yield Complete(usage=usage)
            return

        if tools_on and "Tool denied:" in user_text:
            # Resume → deny. The handler already emitted the cancelled
            # tool_result; we emit the denial answer + Complete.
            await asyncio.sleep(self._delay)
            yield AnswerDelta(text="…tool denied: I did not create the calendar event.")
            usage = UsageUpdate(
                input_tokens=50,
                output_tokens=100,
                reasoning_tokens=10,
                cached_input_tokens=0,
            )
            yield usage
            yield Complete(usage=usage)
            return

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
        # Continuation trigger: the route sends a fixed instruction as the new
        # user turn when continuing a Stopped turn. Detect it (the marker phrase
        # is stable) and emit a distinctive deterministic answer so tests can
        # assert the continuation streamed as a NEW assistant bubble. The prior
        # partial text lives in the replayed history, not here.
        if "Continue your previous response" in user_text:
            await asyncio.sleep(self._delay)
            yield AnswerDelta(text="…continued: ")
            await asyncio.sleep(self._delay)
            yield AnswerDelta(text="and here is the rest of the answer.")
            usage = UsageUpdate(
                input_tokens=50,
                output_tokens=100,
                reasoning_tokens=10,
                cached_input_tokens=0,
            )
            yield usage
            yield Complete(usage=usage)
            return

        # Slow trigger: emit many answer deltas with a longer delay so a
        # mid-stream Stop has a wide, DETERMINISTIC window. The default fake
        # stream is ~150ms end-to-end — too fast for an e2e to reliably catch
        # the "Stop generating" button or commit a non-empty `stopped` partial.
        # Each delta is non-empty so the stopped turn is continuable.
        if user_text.startswith("SLOW:"):
            for i in range(40):
                await asyncio.sleep(0.05)
                yield AnswerDelta(text=f"part {i} ")
            usage = UsageUpdate(
                input_tokens=50,
                output_tokens=100,
                reasoning_tokens=10,
                cached_input_tokens=0,
            )
            yield usage
            yield Complete(usage=usage)
            return

        # Mermaid trigger: emit a well-formed, closed fenced mermaid block as the
        # answer body (instead of the templated text). Split across a couple of
        # AnswerDelta chunks so the fence streams in, but always closing it so
        # the FE renders the diagram rather than raw source.
        if user_text.startswith("MERMAID:"):
            await asyncio.sleep(self._delay)
            yield AnswerDelta(text="```mermaid\ngraph TD\n")
            await asyncio.sleep(self._delay)
            yield AnswerDelta(text="  A[Start] --> B[End]\n```")
            usage = UsageUpdate(
                input_tokens=50,
                output_tokens=100,
                reasoning_tokens=10,
                cached_input_tokens=0,
            )
            yield usage
            yield Complete(usage=usage)
            return

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

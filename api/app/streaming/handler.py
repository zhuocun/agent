"""Stream-and-persist orchestration.

Consumes `ProviderEvent`s and:
1. Yields wire SSE events (`submitted` → `reasoning_delta*` → `reasoning_done?`
   → `answer_delta*` → `terminal | error`).
2. Persists the assistant message on terminal (status=done) OR on client
   disconnect (status=stopped, costConfidence=estimate).
3. Skips ALL persistence when `is_temporary` is True.

Cancellation: the provider iteration runs inside an `asyncio.Task`; the
generator polls `request.is_disconnected()` between yields. On disconnect:
cancel the task, flush accumulators into parts, persist with `status=stopped`,
and exit WITHOUT yielding terminal (socket is already closed).

Per plan §"Streaming" invariant: exactly one `reasoning_done` precedes any
`answer_delta`. We track `_emitted_answer_delta` and `_emitted_reasoning_done`
to enforce this — if the provider yields an `AnswerDelta` before
`ReasoningDone` but after at least one `ReasoningDelta`, we emit
`ReasoningDone` first (defensive).

Title autogen: on the FIRST terminal of a conversation (count(role=assistant)
== 0 immediately before persistence), schedule a detached `asyncio.Task`
that calls `provider.complete(...)` on the small/fast tier and writes
`conversation.title`. Fire-and-forget — does NOT block the streaming
response. If the worker dies before the task completes, title stays "New
chat" until next turn fires the check again (plan §"Explicit non-features").
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import jsonschema
import structlog
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette import ServerSentEvent

from app.config import get_settings
from app.db.repositories import analytics as analytics_repo
from app.db.repositories import conversations as conversations_repo
from app.db.repositories import memory_facts as memory_facts_repo
from app.db.repositories import messages as messages_repo
from app.db.repositories import streams as streams_repo
from app.db.repositories import usage as usage_repo
from app.db.session import get_session_factory
from app.errors import AppError, ErrorEnvelope
from app.prompt_assembly import build_system_prefix, build_user_turn
from app.providers.factory import build_provider
from app.providers.pricing import build_attribution, compute_cost_breakdown
from app.providers.protocol import (
    AnswerDelta,
    AttachmentPayload,
    AwaitingApproval,
    ChatMessage,
    Complete,
    Provider,
    ProviderEvent,
    ReasoningDelta,
    ReasoningDone,
    ResponseFormat,
    Sources,
    StatusUpdate,
    ToolCall,
    ToolDefinition,
    ToolResult,
    UsageUpdate,
)
from app.providers.tiers import TierBinding, get_binding
from app.schemas.common import ModelTierId, SubstitutionReasonCode
from app.schemas.conversation import ToolApprovalDecision
from app.schemas.message import ModelAttribution, ToolCallPart, ToolResultPart
from app.schemas.stream_events import (
    AnswerDeltaEvent,
    ReasoningDeltaEvent,
    ReasoningDoneEvent,
    SourcesEvent,
    StatusEvent,
    SubmittedEvent,
    TerminalEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.search.protocol import SourceItem
from app.streaming.replay_registry import ReplayLogBuffer
from app.streaming.sse import (
    encode_answer_delta,
    encode_error,
    encode_reasoning_delta,
    encode_reasoning_done,
    encode_sources,
    encode_status,
    encode_submitted,
    encode_terminal,
    encode_tool_call,
    encode_tool_result,
)
from app.streaming.stop_registry import clear_stop_async, is_stop_requested_async
from app.tools.agent_loop import run_agent_loop, tool_feedback_to_history
from app.tools.builtin import TOOL_REGISTRY, execute_tool
from app.tools.protocol import ToolCallRequest

log = logging.getLogger(__name__)
_struct_log = structlog.get_logger(__name__)

# Detached background tasks (title autogen). `asyncio.create_task` only holds
# a weak reference to the returned Task; without a strong ref the task can
# be garbage-collected mid-flight under some event-loop policies. Keep a
# module-level strong-ref set and discard each entry in the done callback.
_BG_TASKS: set[asyncio.Task[None]] = set()

# Detached resumable-stream PRODUCER tasks (flag ON only). Held strongly here so
# they survive the POST request that spawned them (the producer outlives its
# originating connection — that is the whole point) and so the app lifespan can
# cancel any still-running producer on shutdown. Each entry discards itself in a
# done callback. See `run_detached_producer` + `cancel_all_producers`.
_PRODUCER_TASKS: set[asyncio.Task[None]] = set()


class _NeverDisconnectedRequest:
    """A stand-in `Request` whose socket never reports disconnected.

    The detached producer (flag ON) must NOT be torn down by the originating
    client closing its HTTP connection — that is the resumable-stream semantics
    inversion. `stream_and_persist` polls `request.is_disconnected()` to detect
    a stop; by handing it this stub, the ONLY live cancel paths left are the
    dedicated stop endpoint (via `stop_registry`, which the handler also polls)
    and natural completion. Disconnect of the POST/reconnect subscriber simply
    stops that subscriber tailing; the producer keeps running.
    """

    async def is_disconnected(self) -> bool:
        return False


async def cancel_all_producers() -> None:
    """Cancel every in-flight detached producer. Called on app shutdown.

    Mirrors the lifespan's handling of other detached tasks: a clean cancel so a
    producer doesn't leak past process shutdown. A hard crash (SIGKILL / OOM)
    still bypasses this, leaving the durable `stream` row `active` — that gap is
    the orphan-reaper's job (the same gap the non-resumable path has today).
    """
    tasks = list(_PRODUCER_TASKS)
    for task in tasks:
        task.cancel()
    for task in tasks:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


@dataclass(frozen=True)
class ResumeToolSeed:
    """Resolved instruction for resuming a turn paused on an approval-gated tool.

    Built by the route's `_prepare_resume_tool` AFTER it re-validated server-side
    that the tool exists, genuinely needs approval, and any `edited_input` is
    allowlisted (the approval gate is the trust boundary — the client decision is
    never trusted on its own). The handler turns this into the seeded
    `tool_result` it emits BEFORE running the post-approval provider pass:

    - ``decision == "approve"`` → execute the tool (timeout-wrapped) and emit a
      ``ToolResult(approval_state="approved")``.
    - ``decision == "deny"`` → synthesize a cancelled/rejected ``ToolResult``
      WITHOUT executing (the side effect must not happen on a denial).
    """

    tool_call_id: str
    name: str
    label: str | None
    decision: str
    input: dict[str, Any] | None


@dataclass(frozen=True)
class _PumpError:
    """Carries a provider exception from the pump task to the consumer.

    The pump drains the provider iterator on its own task; if the iterator
    raises mid-stream we must surface that to the consumer loop rather than
    swallow it. Enqueuing this sentinel lets the consumer re-raise the
    original exception so the top-level handler emits an `error` frame and
    skips persistence (plan §"Persistence": `error` does not persist).
    """

    exc: BaseException


# Provider error codes that are safe to retry on a fallback route: a rate limit
# or a transient upstream failure. These mirror the typed `AppError`s the real
# provider adapters raise (`openai.py` / `anthropic.py` `_map_sdk_error`).
_RETRYABLE_CODES = {"RATE_LIMITED", "PROVIDER_UPSTREAM"}


def _is_retryable(exc: BaseException) -> bool:
    """Whether a provider exception qualifies for a fallback-route retry."""
    return isinstance(exc, AppError) and exc.envelope.code in _RETRYABLE_CODES


def _fold_complete_substitution(
    ev: Complete,
    current: tuple[str | None, str | None, str | None, str | None],
) -> tuple[str | None, str | None, str | None, str | None]:
    """Fold a `Complete` event's substitution into the running sub state.

    `current` is the `(sub_code, sub_provider, sub_model, sub_label)` tuple
    accumulated so far — it may already hold a router-side `auto_downgrade`
    seed. A provider-side fallback WINS precedence and overwrites the seed,
    bringing the real served-model triple with it. But this only happens when
    the provider ACTUALLY substituted: a `Complete` with `substitution is None`
    means "no provider fallback" and MUST NOT clobber the router seed (the
    silent-downgrade-leak invariant). In that case `current` is returned
    unchanged.

    Centralizing this so the three `Complete` consumers (the two inline
    streaming branches AND the disconnect/stop drain branch) can never drift
    apart on the guard.
    """
    if ev.substitution is None:
        return current
    return (
        ev.substitution,
        ev.substituted_provider,
        ev.substituted_model,
        ev.substituted_display_label,
    )


def _derive_session_factory(
    db: AsyncSession,
) -> async_sessionmaker[AsyncSession]:
    """Build a sessionmaker pointing at the same engine as `db`.

    The detached title-autogen task needs a fresh session — the request
    scope is closing. We can't use `get_session_factory()` because in tests
    that's the process-wide factory bound to env DATABASE_URL, NOT the
    per-test SQLite file the request session was bound to.

    Falls back to `get_session_factory()` if the bind can't be extracted
    (defensive — should not happen in practice; `AsyncSession.bind`
    is an `AsyncEngine` once the session has executed anything).
    """
    bind = db.bind
    if bind is None:
        return get_session_factory()
    return async_sessionmaker(
        bind=bind,
        expire_on_commit=False,
        autoflush=False,
    )


# Prompt used for title autogen. Kept short — the small/fast tier sees the
# user's first turn plus this instruction and returns a 4-6 word title.
# Phrased as the user side of a single turn (no system prompt seam in our
# Protocol) so the provider treats it as a normal completion.
_TITLE_AUTOGEN_PROMPT = (
    "Summarize the following user message as a concise 4-6 word title. "
    "Return ONLY the title — no quotes, no punctuation at the end, no "
    "explanation.\n\nMessage: "
)

def _apply_structured_output(
    attribution: ModelAttribution,
    *,
    response_format: ResponseFormat | None,
    answer_text: str,
) -> None:
    """Surface structured-output (JSON mode) validation on the attribution.

    The "schema validation at the boundary" step. No-op when `response_format`
    is None. Otherwise it records the requested `output_format` and computes
    `output_valid` from the accumulated answer text:

    - `json.loads(answer_text)` must succeed (any json mode). A parse failure ⇒
      `output_valid=False`.
    - For `json_schema` with a schema present, the parsed value is additionally
      validated with `jsonschema.validate`; a `ValidationError`/`SchemaError` ⇒
      `output_valid=False`.

    Invalid output NEVER hard-fails the turn — the raw text is preserved and the
    status stays `done`; only `output_valid` reflects the failure. Mutates
    `attribution` in place (additive fields kept at the END of the model). Shared
    by the inline and detached-producer paths so they can't drift.
    """
    if response_format is None:
        return
    attribution.output_format = response_format.type
    try:
        instance = json.loads(answer_text)
    except (ValueError, TypeError):
        attribution.output_valid = False
        return
    if response_format.type == "json_schema" and response_format.schema is not None:
        try:
            jsonschema.validate(instance, response_format.schema)
        except (jsonschema.ValidationError, jsonschema.SchemaError):
            attribution.output_valid = False
            return
    attribution.output_valid = True


async def _autogen_title(
    *,
    conversation_id: UUID,
    user_text: str,
    session_factory: async_sessionmaker[AsyncSession],
    provider_id: str,
    api_key: str | None,
) -> None:
    """Detached task: call the fast tier, write `conversation.title`.

    Owns its own session (the request scope is already closed by the time
    this runs). The session factory is passed in by the caller so tests can
    point the task at the per-test SQLite file rather than the process-wide
    factory (which is built lazily from env DATABASE_URL — wrong in tests).

    Swallows all exceptions — title autogen is best-effort and must never
    propagate into the streaming response or leak as an unhandled task
    exception.
    """
    try:
        settings = get_settings()
        binding = get_binding("fast", settings=settings, provider_id=provider_id)
        if binding is None:
            # Registry misconfigured — log and bail. Title stays "New chat".
            log.warning("autogen_title.no_fast_binding", extra={"provider_id": provider_id})
            return
        provider = build_provider(settings, provider_id=provider_id, api_key=api_key)
        title = await provider.complete(
            model_id=binding.model_id,
            history=[],
            user_text=_TITLE_AUTOGEN_PROMPT + user_text,
            api_key=api_key,
        )
        # Strip surrounding whitespace/quotes/trailing period defensively —
        # providers sometimes ignore "no quotes" instructions.
        cleaned = title.strip().strip('"').strip("'").rstrip(".")
        if not cleaned:
            log.warning("autogen_title.empty_response")
            return
        # Cap at a sane length so a runaway model can't blow out the column.
        cleaned = cleaned[:120]
        async with session_factory() as session:
            await conversations_repo.update_title(
                session,
                conversation_id=conversation_id,
                title=cleaned,
            )
            await session.commit()
    except Exception as exc:
        log.warning("autogen_title.failed", exc_info=exc)


# Memory auto-extraction (D19). After a turn completes we ask the model to pull
# a handful of durable, personal facts out of the exchange and append them to
# the user's ledger. Bounded hard: at most `_MEMORY_EXTRACT_MAX` facts per turn,
# and never beyond `_MEMORY_FACTS_PER_USER_CAP` total per user, so an automated
# pipeline can't grow the ledger without limit.
_MEMORY_EXTRACT_MAX = 3
_MEMORY_FACTS_PER_USER_CAP = 200
# Bound a single extracted fact's length to the schema's content cap so a
# runaway model can't store an unbounded blob.
_MEMORY_FACT_MAX_CHARS = 2000
_MEMORY_EXTRACTION_PROMPT = (
    "From the conversation turn below, extract 0 to 3 DURABLE facts about the "
    "user worth remembering long-term (stable preferences, identity, ongoing "
    "projects, constraints). Ignore one-off task details, questions, and "
    "anything not about the user. Respond ONLY with a JSON array of short "
    "strings (e.g. [\"Prefers metric units\"]). Return [] if there is nothing "
    "durable.\n\n"
)


def _parse_extracted_facts(raw: str) -> list[str]:
    """Parse the model's extraction reply into a bounded list of fact strings.

    Tolerant: accepts a JSON array of strings (the requested shape) and falls
    back to newline-delimited lines (stripping list bullets) when the reply
    isn't valid JSON. Drops blanks, trims to the content cap, dedupes, and caps
    the count at `_MEMORY_EXTRACT_MAX`. Returns `[]` for unusable input so the
    caller simply stores nothing.
    """
    text = (raw or "").strip()
    if not text:
        return []
    candidates: list[str] = []
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, list):
        candidates = [str(item) for item in parsed if isinstance(item, str | int | float)]
    else:
        # Fallback: treat each non-empty line as a fact, stripping common
        # bullet/markdown prefixes the model may have emitted despite the ask.
        for line in text.splitlines():
            cleaned_line = line.strip().lstrip("-*0123456789.) ").strip()
            if cleaned_line:
                candidates.append(cleaned_line)

    out: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        fact = candidate.strip()[:_MEMORY_FACT_MAX_CHARS].strip()
        if not fact or fact.lower() in seen:
            continue
        seen.add(fact.lower())
        out.append(fact)
        if len(out) >= _MEMORY_EXTRACT_MAX:
            break
    return out


async def _extract_memory_facts(
    *,
    provider: Provider,
    model_id: str,
    api_key: str | None,
    conversation_id: UUID,
    user_id: UUID,
    user_text: str,
    answer_text: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Detached task: pull durable facts from a completed turn into the ledger.

    Best-effort and fire-and-forget (mirrors `_autogen_title`): owns its own
    session, swallows every exception so it can never propagate into the
    streaming response, and is bounded by the per-turn and per-user caps. Only
    invoked when memory is enabled and the turn is non-temporary (the caller
    gates this).
    """
    try:
        transcript = f"User: {user_text}\nAssistant: {answer_text}".strip()
        if not transcript:
            return
        reply = await provider.complete(
            model_id=model_id,
            history=[],
            user_text=_MEMORY_EXTRACTION_PROMPT + transcript,
            api_key=api_key,
        )
        facts = _parse_extracted_facts(reply)
        if not facts:
            return
        async with session_factory() as session:
            existing = await memory_facts_repo.count_for_user(session, user_id)
            room = _MEMORY_FACTS_PER_USER_CAP - existing
            if room <= 0:
                return
            inserted = 0
            for fact in facts[:room]:
                await memory_facts_repo.add(
                    session,
                    user_id=user_id,
                    content=fact,
                    source="conversation",
                    source_conversation_id=conversation_id,
                )
                inserted += 1
            if inserted:
                await session.commit()
    except Exception as exc:
        log.warning("memory_extraction.failed", exc_info=exc)


async def stream_and_persist(
    *,
    request: Request,
    db: AsyncSession,
    provider: Provider,
    binding: TierBinding,
    requested_tier_id: ModelTierId,
    conversation_id: UUID | None,
    user_message_id: UUID,
    user_text: str,
    history: list[ChatMessage],
    is_temporary: bool,
    is_initial: bool = True,
    user_id: UUID | None = None,
    api_key: str | None = None,
    provider_id: str | None = None,
    stream_id: UUID | None = None,
    router_substitution: SubstitutionReasonCode | None = None,
    web_search: bool = False,
    response_format: ResponseFormat | None = None,
    attachments: list[AttachmentPayload] | None = None,
    custom_instructions: str | None = None,
    memory_facts: list[str] | None = None,
    memory_fact_ids: list[str] | None = None,
    memory_enabled: bool = False,
    reasoning_effort_override: str | None = None,
    thinking_override: bool | None = None,
    monthly_quota_usd_override: float | None = None,
    fallback_binding: TierBinding | None = None,
    fallback_provider_id: str | None = None,
    fallback_api_key: str | None = None,
    fallback_substitution: SubstitutionReasonCode | None = None,
    tool_approval: ToolApprovalDecision | None = None,
    resume_seed: ResumeToolSeed | None = None,
) -> AsyncIterator[ServerSentEvent]:
    """Drive the provider, persist, yield wire SSE events.

    `conversation_id` is None for temporary chats — persistence is skipped.
    The caller MUST have already persisted the user message (or generated a
    synthetic id for temporary chats) before invoking this.

    `is_initial=True` means this is a fresh user send (not a regen, not an
    edit). Title autogen requires BOTH `is_initial` AND `count_assistant_messages
    == 0` so a regen/edit-of-first-turn (which truncates assistants → count
    returns 0) does NOT re-fire autogen and overwrite a user-renamed title.
    Defaults to True so single-call sites without explicit passing keep
    behaving as fresh sends.

    `user_id` + `api_key` (both M3):
    - `user_id` is the caller; required for usage_rollup increments. None is
      accepted only for temporary chats (no persistence, no rollup).
    - `api_key` is the resolved BYOK key for this turn (None means platform
      default). Passed through to `provider.stream(...)`. The `is_byok` flag
      on the rollup row is derived from `api_key is not None`.

    `router_substitution` (auto-routing): a substitution reason decided BEFORE
    the provider call — set by the route when the `auto` tier routed to a
    cheaper-than-baseline concrete tier (`auto_downgrade`). It seeds the
    attribution's substitution so an auto downgrade is surfaced honestly. The
    PROVIDER's own substitution (a real fallback emitted on the `Complete`
    event) takes PRECEDENCE: a provider fallback ON TOP of an auto route
    describes a more urgent, accurate served-vs-requested delta, so it wins and
    overwrites the router-side seed (it carries the actual served model label).
    When neither side substitutes, no `substitution` is emitted.

    `reasoning_effort_override` / `thinking_override` (Feature 1): per-turn
    overrides of the binding's `reasoning_effort` / `thinking` defaults. When
    non-None they REPLACE the binding default for that hint at the provider call;
    when None the binding default is used unchanged. Providers ignore hints they
    don't support, so this is always safe.

    `monthly_quota_usd_override` (Feature 3): the effective monthly quota (min of
    the operator cap and the user's own cap) used for the credit-debit math at
    the `increment_for_period(...)` calls. None falls back to the operator
    `USAGE_BUDGET_USD` so existing callers are unchanged.

    `fallback_*` (Phase 2 provider fallback): an alternate route to retry ONCE
    when the primary provider raises a retryable error BEFORE emitting any token.
    The route owns ALL selection policy and passes a fully-resolved
    `(fallback_binding, fallback_provider_id, fallback_api_key)` plus a
    `fallback_substitution` reason code; the handler stays dumb. When
    `fallback_binding` is None (the default / no alternate) the error surfaces as
    today.

    `tool_approval` / `resume_seed` (HITL tool calling): present only on a resume
    POST that applies an approve/deny decision to a turn previously paused in
    `awaiting_approval`. When `resume_seed` is set the handler emits the seeded
    `tool_result` (executing the approved tool, or synthesizing a cancelled
    result on deny) BEFORE the post-approval provider pass. The agent loop only
    wraps the provider when `settings.tools_enabled`; otherwise the provider
    stream is consumed directly and this whole feature is inert (the flag-off
    path is byte-for-byte unchanged).
    """
    # Emit `submitted` immediately. Resumable clients need the durable stream
    # id in-band so they can reconnect to the exact producer they just started.
    yield encode_submitted(
        SubmittedEvent(
            message_id=str(user_message_id),
            stream_id=str(stream_id) if stream_id is not None else None,
        )
    )
    turn_started_at = time.monotonic()
    first_answer_ms: int | None = None

    # Accumulators for parts + usage.
    reasoning_buf: list[str] = []
    answer_buf: list[str] = []
    final_usage = UsageUpdate()
    emitted_reasoning_done = False
    # Web-search accumulators (only populated when the provider emits the
    # corresponding events). `latest_status` holds the most recent
    # (label, state) so the persisted `status` part records the final line (the
    # `done` line for a completed search). `search_items` holds the resolved
    # `Sources`. When neither is emitted (the common, web_search=False path) the
    # persist sites append no status/sources parts and the stream is unchanged.
    latest_status: tuple[str, str] | None = None
    search_items: list[SourceItem] = []
    # Whether a provider `Sources` event arrived this turn. Distinct from
    # `search_items` being empty: a provider may emit `Sources([])`, and the
    # honesty rule (PRD 07 §4.3) still needs to know that web search RAN. When
    # web search was effective (`web_search`) but no `Sources` event ever
    # arrived, the done-path synthesizes a final empty `sources` frame so the
    # ungrounded state ("Answered without live sources") survives the live turn,
    # reload, replay, and public share.
    saw_sources_event = False
    tool_parts: list[dict[str, Any]] = []
    # HITL pause state (tools only). Set when the agent loop emits an
    # `AwaitingApproval` sentinel: the turn ends in the NEW terminal state
    # `awaiting_approval` rather than `done`. Stays False on every non-tool path.
    paused = False
    paused_tool_call_id: str | None = None
    # Captured once so the per-turn tools gate + agent-loop wrapping read a
    # stable value (and tests can override via a settings cache flush).
    handler_settings = get_settings()
    tools_active = handler_settings.tools_enabled
    # Transparent long-term memory (D19): how many facts were injected into this
    # turn. Surfaced on the attribution (and thus the persisted message + the
    # terminal frame) so the FE can render the "Memory used here" chip. Zero when
    # memory is off, no facts exist, or the turn is temporary (the caller passes
    # no `memory_facts` on the temporary path). The empty/no-op case keeps the
    # wire byte-for-byte unchanged because `build_attribution` omits a 0 value.
    memory_applied_count = len(
        [fact for fact in (memory_facts or []) if fact and fact.strip()]
    )
    # The ids of the injected facts, recorded on the attribution so the FE can
    # link the "Memory used here" chip back to the exact ledger rows (D19).
    # None when nothing was injected so the wire shape is unchanged.
    memory_fact_ids_applied = list(memory_fact_ids or []) or None
    # T19: count image attachments once so the cost math can fold in a per-image
    # input-token estimate on multimodal bindings (no-op when the served binding
    # sets no `image_token_formula`, which is every wired route today).
    image_attachment_count = sum(
        1 for attachment in (attachments or []) if attachment.media_type == "image"
    )
    # Working route state. These start at the primary route and are REASSIGNED in
    # place if a provider-fallback retry fires (Phase 2). The inner closures
    # (`_persist_assistant`, `_terminal_properties`, `_apply_event`,
    # `build_attribution` calls) all read these names at call time, so a
    # pre-first-token rebind is transparently reflected downstream.
    active_provider = provider
    active_api_key = api_key
    is_byok_turn = active_api_key is not None
    runtime_provider_id = provider_id or binding.provider_id
    # Single-shot fallback guard: at most ONE retry, ever.
    fallback_attempted = False
    # Substitution metadata threaded into build_attribution(...). Two sources
    # feed it, with provider-side winning (see below + the docstring):
    #  1. Router-side (auto-routing): seeded here from `router_substitution`.
    #     This is the `auto_downgrade` decided before the provider call. It has
    #     no substituted model triple — the routed concrete `binding` already
    #     carries the served tier/label, so the attribution renders correctly
    #     off the binding alone.
    #  2. Provider-side (M4 fallback): the provider's `Complete` event. When the
    #     provider substituted, `_apply_event` / the Complete branch OVERWRITE
    #     the router-side seed (provider fallback wins precedence) and bring the
    #     real served-model triple with it.
    # When both stay None the wire emits no `substitution` field.
    sub_code: str | None = router_substitution
    sub_provider: str | None = None
    sub_model: str | None = None
    sub_label: str | None = None

    # Build ONE raw provider stream for the current working route + optional
    # agent-loop tool feedback. `tool_feedback` carries the results the agent
    # loop accumulated across rounds, appended to `history` as synthetic turns
    # (the `Provider.stream` Protocol intentionally has no tool params). Empty on
    # round 1 / the non-tool path, so the provider stream is byte-for-byte
    # unchanged there.
    # Cache-stable system prefix (custom instructions + long-term memory) and
    # the clean per-turn user text, assembled once via `prompt_assembly` (T20).
    # Hoisting memory + instructions into the system prefix (instead of wrapping
    # them into the user turn) lets a cache-aware backend reuse the stable
    # prefix across turns. `turn_system_prefix` is None when there's nothing to
    # inject, so the no-instructions / memory-off path sends no system role —
    # byte-for-byte unchanged.
    turn_system_prefix = build_system_prefix(custom_instructions, memory_facts or [])
    turn_user_text = build_user_turn(user_text)

    # Native tool advertisement for REAL providers (agent loop). When tools are
    # enabled we hand the provider the registry's tool schemas so it can
    # advertise them and parse the model's calls into structured `ToolCall`
    # events; the fake provider ignores this and uses its deterministic markers.
    # None when tools are off ⇒ no tools advertised, provider stream unchanged.
    turn_tool_definitions = (
        [
            ToolDefinition(name=spec.name, label=spec.label, parameters=spec.schema)
            for spec in TOOL_REGISTRY.values()
        ]
        if tools_active
        else None
    )

    def _build_raw_stream(tool_feedback: list[ToolResult]) -> AsyncIterator[ProviderEvent]:
        round_history = history + tool_feedback_to_history(tool_feedback)
        return active_provider.stream(
            model_id=binding.model_id,
            history=round_history,
            user_text=turn_user_text,
            attachments=attachments,
            api_key=active_api_key,
            # DeepSeek V4 dual-mode hints. The per-turn override REPLACES the
            # binding default when set; otherwise the binding default is used.
            # None means "provider default" (alternate bindings leave both unset,
            # and adapters ignore what they don't support).
            thinking=(
                thinking_override if thinking_override is not None else binding.thinking
            ),
            reasoning_effort=(
                reasoning_effort_override
                if reasoning_effort_override is not None
                else binding.reasoning_effort
            ),
            # Opt this turn into the web_search tool. False (the default) leaves
            # the provider stream byte-for-byte unchanged — no StatusUpdate /
            # Sources.
            web_search=web_search,
            # Opt this turn into structured output (JSON mode). None (the
            # default) leaves the provider stream byte-for-byte unchanged; the
            # adapters degrade gracefully and the boundary validation surfaces
            # the result on the attribution.
            response_format=response_format,
            # Whether the active binding can interpret images / native PDF
            # document blocks. On a non-vision binding the real-provider adapters
            # suppress native image/PDF blocks (PDFs degrade to transcript text);
            # the route already rejects images to a non-vision binding before this
            # point.
            supports_vision=binding.supports_vision,
            # Cache-stable preamble (custom instructions + memory). None ⇒ no
            # system role, byte-for-byte unchanged.
            system_prefix=turn_system_prefix,
            # Agent-loop tools advertised to a real provider (None when tools are
            # off). The fake provider ignores this; the OpenAI/Anthropic adapters
            # advertise them natively and emit `ToolCall`s the agent loop fulfils.
            tools=turn_tool_definitions,
        )

    # The current provider iterator. Rebuilt on a fallback retry so the pump
    # drains the alternate route. When tools are enabled the raw stream is wrapped
    # in the bounded agent loop (which intercepts `ToolCall`s, runs the registry,
    # and emits the HITL `AwaitingApproval` pause); otherwise it is the raw
    # provider stream — byte-for-byte the pre-tools path. The fallback rebuild
    # path calls this again, so a fallback route is wrapped identically.
    def _build_provider_iter() -> AsyncIterator[ProviderEvent]:
        if tools_active:
            return run_agent_loop(
                make_stream=_build_raw_stream,
                settings=handler_settings,
            )
        return _build_raw_stream([])

    # Wrap the provider iteration in a Task so we can cancel on disconnect.
    provider_iter = _build_provider_iter()

    queue: asyncio.Queue[ProviderEvent | _PumpError | None] = asyncio.Queue()

    async def _pump(iterator: AsyncIterator[ProviderEvent]) -> None:
        """Drain the provider iterator into the queue.

        A provider exception is forwarded to the consumer as a `_PumpError`
        sentinel so the consumer can re-raise it (→ `error` frame, no
        persistence). `CancelledError` (disconnect/cleanup cancel) is NOT
        forwarded — it just ends the pump. The terminal `None` always closes
        the queue so the consumer never blocks.
        """
        try:
            async for ev in iterator:
                await queue.put(ev)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await queue.put(_PumpError(exc))
        finally:
            await queue.put(None)

    pump_task = asyncio.create_task(_pump(provider_iter))

    def _no_output_yet() -> bool:
        """True iff NOTHING has been emitted/accumulated for this turn yet.

        The fallback retry is only safe before the first token/content: zero
        answer deltas (`first_answer_ms is None`), empty reasoning/answer/tool
        accumulators, and empty usage. If any of these is non-empty the primary
        route already produced visible output, so retrying would double-emit /
        double-bill — we must NOT retry.
        """
        return (
            first_answer_ms is None
            and not reasoning_buf
            and not answer_buf
            and not tool_parts
            and final_usage == UsageUpdate()
        )

    def _fallback_pending(exc: BaseException | None) -> bool:
        """Whether `exc` should trigger the one-shot fallback retry.

        ALL of these must hold (the safety boundary): an alternate route exists
        (`fallback_binding`), we have not already retried (`fallback_attempted`),
        the error is retryable (`_is_retryable`), and NOTHING was emitted yet
        (`_no_output_yet`). `None` is never retryable (used for the defensive
        exhaustion check). Keeping the predicate in one place so the `_PumpError`
        branch and the exhaustion guard can't drift.
        """
        return (
            exc is not None
            and fallback_binding is not None
            and not fallback_attempted
            and _is_retryable(exc)
            and _no_output_yet()
        )

    def _build_parts() -> list[dict[str, Any]]:
        """Assemble the persisted assistant parts in canonical order.

        Order for a web-search turn: [reasoning?] [tool transcript*]
        [status(done)] [text] [sources]. The status part is appended only if a
        `StatusUpdate` was seen (recording the FINAL line — `state="done"` for
        a completed search). The sources part is appended whenever web search
        was EFFECTIVE for the turn (`web_search`) — carrying the resolved items
        plus `requested=True` — so the grounded list AND the ungrounded
        (`items=[]`, `requested=True`) state both persist. On a non-web-search
        turn none of those enrichment parts are present, so the parts are
        exactly [reasoning?] [text] as before — the regression-critical no-op
        invariant.
        Shared by the terminal-success and stop-path persist sites so they can
        never drift.
        """
        parts: list[dict[str, Any]] = []
        if reasoning_buf:
            parts.append({"type": "reasoning", "text": "".join(reasoning_buf)})
        parts.extend(tool_parts)
        if latest_status is not None:
            label, _state = latest_status
            parts.append({"type": "status", "label": label, "state": "done"})
        parts.append({"type": "text", "text": "".join(answer_buf)})
        if web_search or search_items:
            parts.append(
                {
                    "type": "sources",
                    "items": [it.model_dump(exclude_none=True) for it in search_items],
                    "requested": web_search,
                }
            )
        return parts

    def _tool_call_part(ev: ToolCall) -> ToolCallPart:
        return ToolCallPart(
            id=ev.id,
            name=ev.name,
            label=ev.label,
            status=ev.status,
            approval_state=ev.approval_state,
            input=ev.input,
        )

    def _tool_result_part(ev: ToolResult) -> ToolResultPart:
        return ToolResultPart(
            tool_call_id=ev.tool_call_id,
            name=ev.name,
            label=ev.label,
            status=ev.status,
            approval_state=ev.approval_state,
            summary=ev.summary,
            output=ev.output,
            error=ev.error,
        )

    async def _persist_assistant(
        *,
        status: str,
        attribution: ModelAttribution,
        session: AsyncSession | None = None,
        commit: bool = True,
        cost_usd: float | None = None,
    ) -> UUID | None:
        if is_temporary or conversation_id is None:
            return None
        parts = _build_parts()
        # Stop-path uses a fresh session (passed via `session=`); terminal-success
        # reuses the request-scoped `db`. Asymmetry: at disconnect the request
        # lifecycle is winding down and the route's get_db cleanup may
        # double-commit, so we decouple by opening a new session for stopped.
        target_session = session if session is not None else db
        row = await messages_repo.create_assistant_message(
            db=target_session,
            conversation_id=conversation_id,
            parts=parts,
            status=status,
            attribution=attribution.model_dump(by_alias=True, exclude_none=True),
            responds_to_message_id=user_message_id,
            cost_usd=cost_usd,
        )
        # When the caller owns the session (stop/fresh-session case, commit=False)
        # we only flush here and let the caller commit AFTER bumping usage, so the
        # assistant row and the meter increment land in ONE commit. The
        # terminal-success path passes no session and commits here as before.
        if commit:
            await target_session.commit()
        else:
            await target_session.flush()
        return row.id

    def _apply_event(ev: ProviderEvent) -> None:
        """Fold a queue event into accumulators (no yields).

        Used to drain any remaining UsageUpdate / Complete events after
        cancelling the pump on disconnect, so `final_usage` reflects the
        latest cumulative usage even on stopped turns.
        """
        nonlocal final_usage, first_answer_ms, sub_code, sub_provider, sub_model, sub_label
        nonlocal latest_status, search_items, saw_sources_event
        if isinstance(ev, ReasoningDelta):
            reasoning_buf.append(ev.text)
        elif isinstance(ev, AnswerDelta):
            if first_answer_ms is None:
                first_answer_ms = int((time.monotonic() - turn_started_at) * 1000)
            answer_buf.append(ev.text)
        elif isinstance(ev, StatusUpdate):
            latest_status = (ev.label, ev.state)
        elif isinstance(ev, Sources):
            search_items = list(ev.items)
            saw_sources_event = True
        elif isinstance(ev, ToolCall):
            tool_parts.append(_tool_call_part(ev).model_dump(by_alias=True, exclude_none=True))
        elif isinstance(ev, ToolResult):
            tool_parts.append(_tool_result_part(ev).model_dump(by_alias=True, exclude_none=True))
        elif isinstance(ev, UsageUpdate):
            final_usage = ev
        elif isinstance(ev, Complete):
            final_usage = ev.usage
            # Provider-side fallback wins over the router-side seed, but only
            # when the provider ACTUALLY substituted (see helper docstring) —
            # a `substitution is None` here must NOT clobber a router-side
            # `auto_downgrade` already in `sub_code`. Shared with both inline
            # streaming branches via `_fold_complete_substitution`.
            sub_code, sub_provider, sub_model, sub_label = _fold_complete_substitution(
                ev, (sub_code, sub_provider, sub_model, sub_label)
            )

    def _terminal_properties(
        *,
        terminal_status: str,
        attribution: ModelAttribution | None = None,
        message_id: UUID | str | None = None,
        cost_usd: float | None = None,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        provider_value = attribution.provider_id if attribution is not None else runtime_provider_id
        props: dict[str, Any] = {
            "terminalStatus": terminal_status,
            "conversationId": str(conversation_id) if conversation_id else None,
            "messageId": str(message_id) if message_id is not None else None,
            "requestedTierId": requested_tier_id,
            "servedTierId": binding.tier.id,
            "providerId": provider_value,
            "isByok": is_byok_turn,
            "ttftMs": first_answer_ms,
            "turnMs": int((time.monotonic() - turn_started_at) * 1000),
            "webSearch": web_search,
            "attachmentCount": len(attachments or []),
        }
        if cost_usd is not None:
            props["costUsd"] = cost_usd
        if error_code is not None:
            props["errorCode"] = error_code
        return props

    # HITL resume seeding. On a resume POST the route resolved + re-validated the
    # decision into `resume_seed`; emit the corresponding `tool_result` BEFORE
    # consuming the post-approval provider pass so the new assistant row's parts
    # are [tool_result, …answer]. Approve runs the (timeout-wrapped) tool; deny
    # synthesizes a cancelled/rejected result WITHOUT executing — the side effect
    # must never happen on a denial.
    if resume_seed is not None:
        if resume_seed.decision == "approve":
            exec_result = await execute_tool(
                ToolCallRequest(
                    id=resume_seed.tool_call_id,
                    name=resume_seed.name,
                    input=resume_seed.input or {},
                    approval_state="approved",
                )
            )
            seeded_result = ToolResult(
                tool_call_id=exec_result.tool_call_id,
                name=exec_result.name,
                label=resume_seed.label,
                status=exec_result.status,
                approval_state="approved",
                summary=exec_result.summary,
                output=exec_result.output or None,
                error=exec_result.error,
            )
        else:
            seeded_result = ToolResult(
                tool_call_id=resume_seed.tool_call_id,
                name=resume_seed.name,
                label=resume_seed.label,
                status="cancelled",
                approval_state="rejected",
                summary="User denied the tool call.",
                error="User denied the tool call.",
            )
        seeded_part = _tool_result_part(seeded_result)
        tool_parts.append(seeded_part.model_dump(by_alias=True, exclude_none=True))
        yield encode_tool_result(
            ToolResultEvent.model_validate(
                seeded_part.model_dump(by_alias=True, exclude_none=True)
            )
        )

    try:
        while True:
            # Tear down on EITHER a server-side stop request (the dedicated stop
            # endpoint set the in-process signal for this stream_id) OR the
            # client closing the socket (disconnect, per plan §"Streaming" rule
            # 6). Both persist the same `status="stopped"` row.
            if (
                stream_id is not None and await is_stop_requested_async(stream_id)
            ) or await request.is_disconnected():
                pump_task.cancel()
                # Suppress ONLY the CancelledError from the cancel we just
                # issued; the pump forwards real provider exceptions through
                # the queue (drained below), so nothing genuine is hidden.
                with contextlib.suppress(asyncio.CancelledError):
                    await pump_task
                # Drain any events the pump already enqueued before cancel —
                # the pump may have pushed a final UsageUpdate / Complete that
                # we'd otherwise lose, leaving `final_usage` empty on stopped.
                while not queue.empty():
                    drained = queue.get_nowait()
                    if drained is None or isinstance(drained, _PumpError):
                        # Disconnect takes precedence over a late provider
                        # error: we're persisting `stopped`, not erroring, so
                        # a forwarded `_PumpError` is dropped here.
                        continue
                    _apply_event(drained)
                # Flush accumulators, persist with status=stopped + estimate.
                breakdown = compute_cost_breakdown(
                    usage=final_usage,
                    binding=binding,
                    image_count=image_attachment_count,
                )
                # Per-turn cost: matches what build_attribution exposes as
                # `attribution.costUsd` (pricing.py) so the ledger and the
                # wire stay consistent.
                turn_cost = breakdown.subtotal_usd + breakdown.session_surcharge_usd
                attribution = build_attribution(
                    requested_tier_id=requested_tier_id,
                    binding=binding,
                    breakdown=breakdown,
                    cost_confidence="estimate",
                    is_byok=is_byok_turn,
                    substitution=sub_code,
                    substituted_provider=sub_provider,
                    substituted_model=sub_model,
                    substituted_display_label=sub_label,
                    memory_applied=memory_applied_count,
                    memory_fact_ids=memory_fact_ids_applied,
                )
                # Use a fresh session for stop-path persist (see helper docstring).
                # The assistant row and the usage_rollup bump land in ONE commit:
                # the persist flushes (commit=False), the meter bumps, then a
                # single fresh_db.commit() makes both durable atomically. Mirrors
                # the happy path (bump BEFORE its single commit) so a crash
                # between writes can never persist a stopped row without usage.
                async with _derive_session_factory(db)() as fresh_db:
                    stopped_assistant_id = await _persist_assistant(
                        status="stopped",
                        attribution=attribution,
                        session=fresh_db,
                        commit=False,
                        cost_usd=turn_cost,
                    )
                    # Stopped turn still cost partial tokens -- bump the meter.
                    # `is_temporary` already gates persistence; only increment
                    # if we actually have a real user / conversation.
                    if not is_temporary and conversation_id is not None and user_id is not None:
                        await usage_repo.increment_for_period(
                            fresh_db,
                            user_id=user_id,
                            cost_usd_delta=turn_cost,
                            is_byok=is_byok_turn,
                            monthly_quota_usd=(
                                monthly_quota_usd_override
                                if monthly_quota_usd_override is not None
                                else get_settings().usage_budget_usd
                            ),
                            reference_type="message",
                            reference_id=(
                                str(stopped_assistant_id)
                                if stopped_assistant_id is not None
                                else None
                            ),
                        )
                        await analytics_repo.record(
                            fresh_db,
                            user_id=user_id,
                            event_type="response.terminal",
                            properties=_terminal_properties(
                                terminal_status="stopped",
                                attribution=attribution,
                                message_id=stopped_assistant_id,
                                cost_usd=turn_cost,
                            ),
                        )
                    # Land the durable stream lifecycle in the SAME commit as the
                    # stopped assistant row + meter bump. `message_id` points at
                    # the just-persisted assistant row (may be None for
                    # temporary, but the stop path only runs non-temporary
                    # streams).
                    if stream_id is not None:
                        await streams_repo.mark_status(
                            fresh_db,
                            stream_id=stream_id,
                            status="stopped",
                            message_id=stopped_assistant_id,
                        )
                    await fresh_db.commit()
                # Drop the live signal now that the turn is fully torn down.
                if stream_id is not None:
                    await clear_stop_async(stream_id)
                # M4: stop-path turn log at warn level with cost_confidence=estimate.
                _struct_log.warning(
                    "turn.stopped",
                    status="stopped",
                    conversation_id=str(conversation_id) if conversation_id else None,
                    turn_ms=int((time.monotonic() - turn_started_at) * 1000),
                    prompt_tokens=final_usage.input_tokens,
                    completion_tokens=final_usage.output_tokens,
                    reasoning_tokens=final_usage.reasoning_tokens,
                    cost_usd=breakdown.subtotal_usd,
                    cost_confidence="estimate",
                    is_byok=is_byok_turn,
                    tier_id=binding.tier.id,
                    provider_id=attribution.provider_id,
                    provider_label=attribution.provider_label,
                )
                return  # No terminal on disconnect (socket closed).

            try:
                ev = await asyncio.wait_for(queue.get(), timeout=0.1)
            except TimeoutError:
                continue
            if ev is None:
                if _fallback_pending(None):
                    # The primary pump exhausted with `None` only AFTER a
                    # retryable `_PumpError` set up a pending retry below; this
                    # branch is unreachable in practice because `_PumpError`
                    # arrives before its terminal `None`. Kept defensive.
                    continue
                break  # Provider exhausted.
            if isinstance(ev, _PumpError):
                # Provider raised mid-stream. Phase 2: if this is a retryable
                # error that arrived BEFORE any token/content was emitted, and a
                # fallback route is available and we haven't already retried,
                # tear down the first pump and restart on the fallback route —
                # exactly once. Otherwise re-raise into the top-level
                # `except Exception` so we emit an `error` frame and persist
                # nothing (the assistant row was never committed).
                if _fallback_pending(ev.exc):
                    fallback_attempted = True
                    # Drain the pump's terminal `None` (the pump always enqueues
                    # one after the error) so the queue is clean before restart.
                    with contextlib.suppress(asyncio.CancelledError):
                        await pump_task
                    while not queue.empty():
                        leftover = queue.get_nowait()
                        if not (leftover is None or isinstance(leftover, _PumpError)):
                            # Defensive: a retryable pre-token error means no
                            # real events preceded it, but never fold a stray
                            # event in — that would defeat the no-output gate.
                            pass
                    # Rebind the working route to the fallback. `fallback_binding`
                    # is non-None here (checked in `_fallback_pending`).
                    assert fallback_binding is not None
                    binding = fallback_binding
                    runtime_provider_id = (
                        fallback_provider_id or fallback_binding.provider_id
                    )
                    active_api_key = fallback_api_key
                    is_byok_turn = active_api_key is not None
                    # Build the provider for the fallback route. The fallback may
                    # be a DIFFERENT backend (e.g. deepseek→anthropic), so we
                    # cannot reuse the primary provider object — that would send
                    # the fallback model id to the wrong API. Constructing the
                    # provider for an already-chosen route is not routing policy;
                    # all selection happened in the route's `_select_fallback_route`.
                    active_provider = build_provider(
                        get_settings(),
                        provider_id=runtime_provider_id,
                        api_key=active_api_key,
                    )
                    # Surface the substitution. Prefer the caller's explicit
                    # reason, but a RATE_LIMITED primary error reads as
                    # `rate_limited` so the wire reason matches the cause.
                    if (
                        isinstance(ev.exc, AppError)
                        and ev.exc.envelope.code == "RATE_LIMITED"
                    ):
                        sub_code = "rate_limited"
                    else:
                        sub_code = fallback_substitution or "provider_fallback"
                    _struct_log.warning(
                        "turn.provider_fallback",
                        conversation_id=str(conversation_id) if conversation_id else None,
                        fallback_provider_id=runtime_provider_id,
                        reason_code=sub_code,
                    )
                    provider_iter = _build_provider_iter()
                    pump_task = asyncio.create_task(_pump(provider_iter))
                    continue
                raise ev.exc

            if isinstance(ev, ReasoningDelta):
                reasoning_buf.append(ev.text)
                yield encode_reasoning_delta(ReasoningDeltaEvent(text=ev.text))
            elif isinstance(ev, ReasoningDone):
                if not emitted_reasoning_done:
                    yield encode_reasoning_done(ReasoningDoneEvent())
                    emitted_reasoning_done = True
            elif isinstance(ev, StatusUpdate):
                # Web-search status line (reuses the existing `status` SSE
                # event). Emit live and remember the latest (label, state) so
                # the persisted `status` part records the final, `done` line.
                latest_status = (ev.label, ev.state)
                yield encode_status(StatusEvent(label=ev.label, state=ev.state))
            elif isinstance(ev, Sources):
                # Resolved citation list. Emit the `sources` SSE event and stash
                # the items for the persisted `sources` part (appended after the
                # text part at the persist sites). `requested` mirrors whether
                # web search was effective for the turn (it is, here) so the FE
                # can tell grounded from ungrounded on the live stream.
                search_items = list(ev.items)
                saw_sources_event = True
                yield encode_sources(
                    SourcesEvent(items=list(ev.items), requested=web_search)
                )
            elif isinstance(ev, ToolCall):
                call_part = _tool_call_part(ev)
                tool_parts.append(call_part.model_dump(by_alias=True, exclude_none=True))
                yield encode_tool_call(
                    ToolCallEvent.model_validate(
                        call_part.model_dump(by_alias=True, exclude_none=True)
                    )
                )
            elif isinstance(ev, ToolResult):
                result_part = _tool_result_part(ev)
                tool_parts.append(result_part.model_dump(by_alias=True, exclude_none=True))
                yield encode_tool_result(
                    ToolResultEvent.model_validate(
                        result_part.model_dump(by_alias=True, exclude_none=True)
                    )
                )
            elif isinstance(ev, AwaitingApproval):
                # HITL pause. The gated `tool_call` part (awaiting_approval /
                # pending) was already emitted via the ToolCall branch above. Flag
                # the pause and break — this is NOT an error, so it must NOT route
                # through the fallback / `_PumpError` path. Post-loop branching on
                # `paused` ends the turn in `awaiting_approval`.
                paused = True
                paused_tool_call_id = ev.tool_call_id
                break
            elif isinstance(ev, AnswerDelta):
                # Invariant: emit ReasoningDone before the first AnswerDelta,
                # if any reasoning_delta has been seen but done hasn't fired.
                if reasoning_buf and not emitted_reasoning_done:
                    yield encode_reasoning_done(ReasoningDoneEvent())
                    emitted_reasoning_done = True
                if first_answer_ms is None:
                    first_answer_ms = int((time.monotonic() - turn_started_at) * 1000)
                answer_buf.append(ev.text)
                yield encode_answer_delta(AnswerDeltaEvent(text=ev.text))
            elif isinstance(ev, UsageUpdate):
                final_usage = ev
            elif isinstance(ev, Complete):
                final_usage = ev.usage
                # Provider-side fallback wins over the router-side seed, but
                # only when the provider ACTUALLY substituted; a `None` here
                # must not clobber a router-side `auto_downgrade` seed. Shared
                # with the drain branch via `_fold_complete_substitution`.
                sub_code, sub_provider, sub_model, sub_label = _fold_complete_substitution(
                    ev, (sub_code, sub_provider, sub_model, sub_label)
                )

        # HITL pause terminal. The agent loop hit an approval-gated tool and
        # emitted `AwaitingApproval`; end the turn in the NEW terminal state
        # `awaiting_approval` instead of `done`. The paused state lives entirely
        # in the persisted `tool_call` (awaiting_approval / pending) part — no
        # migration is needed (Message/Stream `status` are free String columns).
        # We persist an ESTIMATE attribution (reuse the stopped-path build) over
        # the tokens consumed up to the pause, bump usage, and RELEASE the
        # single-active-stream guard so the resume POST can open its own stream.
        if paused:
            breakdown = compute_cost_breakdown(
                usage=final_usage,
                binding=binding,
                image_count=image_attachment_count,
            )
            turn_cost = breakdown.subtotal_usd + breakdown.session_surcharge_usd
            attribution = build_attribution(
                requested_tier_id=requested_tier_id,
                binding=binding,
                breakdown=breakdown,
                cost_confidence="estimate",
                is_byok=is_byok_turn,
                substitution=sub_code,
                substituted_provider=sub_provider,
                substituted_model=sub_model,
                substituted_display_label=sub_label,
                memory_applied=memory_applied_count,
                memory_fact_ids=memory_fact_ids_applied,
            )
            paused_assistant_id: UUID | None = None
            if not is_temporary and conversation_id is not None:
                paused_assistant_id = await _persist_assistant(
                    status="awaiting_approval",
                    attribution=attribution,
                    commit=False,
                    cost_usd=turn_cost,
                )
                if user_id is not None:
                    await usage_repo.increment_for_period(
                        db,
                        user_id=user_id,
                        cost_usd_delta=turn_cost,
                        is_byok=is_byok_turn,
                        monthly_quota_usd=(
                            monthly_quota_usd_override
                            if monthly_quota_usd_override is not None
                            else get_settings().usage_budget_usd
                        ),
                        reference_type="message",
                        reference_id=(
                            str(paused_assistant_id)
                            if paused_assistant_id is not None
                            else None
                        ),
                    )
                if stream_id is not None:
                    # Release the active-stream guard: the turn is parked awaiting
                    # a human decision, and the resume POST must be allowed to open
                    # its own stream on this conversation.
                    await streams_repo.mark_status(
                        db,
                        stream_id=stream_id,
                        status="awaiting_approval",
                        message_id=paused_assistant_id,
                        release_active_guard=True,
                    )
                await db.commit()
            terminal_message_id = (
                str(paused_assistant_id) if paused_assistant_id is not None else str(uuid4())
            )
            _struct_log.info(
                "turn.awaiting_approval",
                status="awaiting_approval",
                conversation_id=str(conversation_id) if conversation_id else None,
                turn_ms=int((time.monotonic() - turn_started_at) * 1000),
                tool_call_id=paused_tool_call_id,
                cost_usd=breakdown.subtotal_usd,
                cost_confidence="estimate",
                is_byok=is_byok_turn,
                tier_id=binding.tier.id,
                provider_id=attribution.provider_id,
                message_id=terminal_message_id,
            )
            yield encode_terminal(
                TerminalEvent(
                    status="awaiting_approval",
                    message_id=terminal_message_id,
                    attribution=attribution,
                )
            )
            if stream_id is not None:
                await clear_stop_async(stream_id)
            return

        # Honesty rule (PRD 07 §4.3): web search was effective for this turn but
        # NO `Sources` event arrived — the answer is ungrounded. Emit a final
        # `sources` frame with empty items + `requested=True` so the live turn
        # is visibly marked "Answered without live sources" rather than looking
        # cited. The matching empty `SourcesPart` persists via `_build_parts`
        # (gated on `web_search`), so the ungrounded state survives reload,
        # replay, and public share too.
        if web_search and not saw_sources_event:
            yield encode_sources(SourcesEvent(items=[], requested=True))

        # Provider finished cleanly. Compute attribution and emit terminal.
        breakdown = compute_cost_breakdown(
            usage=final_usage,
            binding=binding,
            image_count=image_attachment_count,
        )
        # Per-turn cost: matches what build_attribution exposes as
        # `attribution.costUsd` (pricing.py) so the cost ledger row and the
        # wire attribution agree.
        turn_cost = breakdown.subtotal_usd + breakdown.session_surcharge_usd
        attribution = build_attribution(
            requested_tier_id=requested_tier_id,
            binding=binding,
            breakdown=breakdown,
            cost_confidence="exact",
            is_byok=is_byok_turn,
            substitution=sub_code,
            substituted_provider=sub_provider,
            substituted_model=sub_model,
            substituted_display_label=sub_label,
            memory_applied=memory_applied_count,
            memory_fact_ids=memory_fact_ids_applied,
        )
        # Structured-output boundary validation. No-op unless a `response_format`
        # was requested; then it sets `output_format` and validates the
        # accumulated answer text (JSON parse + optional JSON Schema check),
        # surfacing `output_valid` WITHOUT failing the turn.
        _apply_structured_output(
            attribution,
            response_format=response_format,
            answer_text="".join(answer_buf),
        )

        # Persist the assistant message (skipped for temporary).
        # First-terminal check happens BEFORE the create so we don't count
        # the row we're about to insert. Plan §"Behavior" + §"Title autogen":
        # only fire on the FIRST assistant message for the conversation.
        assistant_id: UUID | None = None
        is_first_terminal = False
        if not is_temporary and conversation_id is not None:
            # Title autogen gate: BOTH "no prior assistant rows" AND "this is a
            # fresh send" (not regen, not edit). Regen / edit-of-first-turn
            # delete the prior assistant(s) → count returns 0, which would
            # otherwise re-fire autogen and clobber a user-renamed title.
            is_first_terminal = is_initial and (
                await messages_repo.count_assistant_messages(db, conversation_id) == 0
            )
            parts = _build_parts()
            row = await messages_repo.create_assistant_message(
                db=db,
                conversation_id=conversation_id,
                parts=parts,
                status="done",
                attribution=attribution.model_dump(by_alias=True, exclude_none=True),
                responds_to_message_id=user_message_id,
                cost_usd=turn_cost,
            )
            # Bump usage_rollup before the commit so both writes land
            # atomically. `user_id` is set on every non-temporary path (the
            # route always passes it for owned conversations). If callers
            # forget to pass it we skip the increment rather than 500 -- the
            # FE meter just stays cold.
            if user_id is not None:
                await usage_repo.increment_for_period(
                    db,
                    user_id=user_id,
                    cost_usd_delta=turn_cost,
                    is_byok=is_byok_turn,
                    monthly_quota_usd=(
                        monthly_quota_usd_override
                        if monthly_quota_usd_override is not None
                        else get_settings().usage_budget_usd
                    ),
                    reference_type="message",
                    reference_id=str(row.id),
                )
            # Transition the durable stream lifecycle to `done` and point it at
            # the assistant row, within the SAME transaction as the assistant
            # row + meter bump so the whole turn commits atomically.
            if stream_id is not None:
                await streams_repo.mark_status(
                    db,
                    stream_id=stream_id,
                    status="done",
                    message_id=row.id,
                )
            if user_id is not None:
                await analytics_repo.record(
                    db,
                    user_id=user_id,
                    event_type="response.terminal",
                    properties=_terminal_properties(
                        terminal_status="done",
                        attribution=attribution,
                        message_id=row.id,
                        cost_usd=turn_cost,
                    ),
                )
                await analytics_repo.record_once_per_user(
                    db,
                    user_id=user_id,
                    event_type="activation.first_successful_response",
                    properties={
                        "conversationId": str(conversation_id),
                        "messageId": str(row.id),
                        "requestedTierId": requested_tier_id,
                        "servedTierId": binding.tier.id,
                        "providerId": attribution.provider_id,
                        "isByok": is_byok_turn,
                        "costUsd": turn_cost,
                        "ttftMs": first_answer_ms,
                    },
                )
            await db.commit()
            assistant_id = row.id

            if is_first_terminal:
                # Fire-and-forget. The task owns its own session; if the
                # worker dies before completion, title stays "New chat" until
                # the next turn re-fires the check (acceptable per plan).
                # Note: we don't `await` here — the streaming response must
                # close immediately after `terminal`. We do hold a reference
                # via a module-level set to keep the task alive against GC
                # in case the asyncio event-loop policy drops weakrefs.
                # The session factory is derived from the request-scoped
                # session's bind so tests can point at the per-test SQLite
                # file. In prod the bind is the process engine; either way
                # the factory targets the right DB.
                task = asyncio.create_task(
                    _autogen_title(
                        conversation_id=conversation_id,
                        user_text=user_text,
                        session_factory=_derive_session_factory(db),
                        provider_id=runtime_provider_id,
                        api_key=active_api_key,
                    )
                )
                _BG_TASKS.add(task)
                task.add_done_callback(_BG_TASKS.discard)

            # Memory auto-extraction (D19). Fire-and-forget on a clean `done`
            # turn when memory is enabled (the route only sets `memory_enabled`
            # for non-temporary turns). Pulls 0-3 durable facts from the turn
            # into the ledger, bounded per-user. Best-effort: the task owns its
            # own session and swallows errors, so it can never affect this turn.
            if memory_enabled and user_id is not None:
                extract_task = asyncio.create_task(
                    _extract_memory_facts(
                        provider=active_provider,
                        model_id=binding.model_id,
                        api_key=active_api_key,
                        conversation_id=conversation_id,
                        user_id=user_id,
                        user_text=user_text,
                        answer_text="".join(answer_buf),
                        session_factory=_derive_session_factory(db),
                    )
                )
                _BG_TASKS.add(extract_task)
                extract_task.add_done_callback(_BG_TASKS.discard)

        # Terminal frame. For temporary chats the message is never persisted,
        # so we mint a fresh uuid4 per turn — using a constant placeholder
        # would collide across consecutive temp turns in one tab and break
        # FE-side vote/copy actions that key off `messageId`.
        terminal_message_id = str(assistant_id) if assistant_id is not None else str(uuid4())
        # M4: terminal-success turn log. Bound contextvars (request_id,
        # user_id) are merged in automatically; here we add per-turn keys.
        _struct_log.info(
            "turn.done",
            status="done",
            conversation_id=str(conversation_id) if conversation_id else None,
            turn_ms=int((time.monotonic() - turn_started_at) * 1000),
            prompt_tokens=final_usage.input_tokens,
            completion_tokens=final_usage.output_tokens,
            reasoning_tokens=final_usage.reasoning_tokens,
            cost_usd=breakdown.subtotal_usd,
            cost_confidence="exact",
            is_byok=is_byok_turn,
            tier_id=binding.tier.id,
            provider_id=attribution.provider_id,
            provider_label=attribution.provider_label,
            message_id=terminal_message_id,
        )
        yield encode_terminal(
            TerminalEvent(message_id=terminal_message_id, attribution=attribution)
        )

    except asyncio.CancelledError:
        # Hard cancel: worker shutdown / deploy / ASGI task cancel mid-stream.
        # Before re-raising we close out the durable stream bookkeeping so the
        # `stream` row doesn't strand at `status="active"` forever and the live
        # stop signal doesn't leak. Mirrors the `except Exception` branch's
        # fresh-session + best-effort pattern.
        #
        # Terminal status here is `"stopped"`, not `"error"`: the turn was
        # cancelled (the work was interrupted), not failed by the provider —
        # `"stopped"` matches the disconnect/explicit-stop semantics. We do NOT
        # persist a partial assistant row in this branch; there is no clean
        # partial-persist contract for a hard cancel, so we only close the
        # stream-lifecycle bookkeeping.
        #
        # A hard worker *crash* (SIGKILL / OOM) delivers no CancelledError, so
        # this cleanup never runs and the row would stay `active`. That gap is
        # closed by the orphan-stream reaper (`app.streaming.reaper` +
        # `streams_repo.reap_stale_active`), which sweeps stale `active` rows to
        # `"error"` on startup and on an interval (PRD 04 §5.1).
        if stream_id is not None:
            with contextlib.suppress(Exception):
                async with _derive_session_factory(db)() as cancel_db:
                    await streams_repo.mark_status(
                        cancel_db,
                        stream_id=stream_id,
                        status="stopped",
                        release_active_guard=True,
                    )
                    await cancel_db.commit()
            with contextlib.suppress(Exception):
                await clear_stop_async(stream_id)
        # Re-raise so the event loop sees the cancellation rather than
        # swallowing it into a fake `error` envelope. The cleanup above must
        # NEVER suppress the cancellation. The `finally` clause still cancels
        # the pump task below.
        raise
    except Exception as exc:
        pump_task.cancel()
        # Suppress ONLY CancelledError from this cleanup cancel. The provider
        # error is already captured in `exc`; the pump forwards via the queue
        # and never re-raises on await, so no real exception is hidden here.
        with contextlib.suppress(asyncio.CancelledError):
            await pump_task
        if isinstance(exc, AppError):
            # Provider raised a typed error (e.g. RATE_LIMITED with
            # retryAfterMs); surface its envelope verbatim.
            envelope = exc.envelope
        else:
            # Unknown failure: generic upstream error. Never leak the raw
            # exception text to the client.
            envelope = ErrorEnvelope(
                code="PROVIDER_UPSTREAM",
                severity="error",
                title="Streaming failed",
                body="The provider stream errored.",
            )
        yield encode_error(envelope)
        # `error` does NOT persist an assistant row (plan §"Persistence" rule).
        # But the durable `stream` row SHOULD reflect the failure so the
        # lifecycle is observable. Best-effort + fresh session: the request
        # session may be poisoned after the provider error (a failed flush
        # leaves it in a rolled-back-pending state), so we open a clean one and
        # swallow any failure — stream-status bookkeeping must never turn a
        # provider error into a 500 or mask the `error` frame already yielded.
        if stream_id is not None:
            try:
                async with _derive_session_factory(db)() as err_db:
                    await streams_repo.mark_status(err_db, stream_id=stream_id, status="error")
                    if user_id is not None:
                        await analytics_repo.record(
                            err_db,
                            user_id=user_id,
                            event_type="response.terminal",
                            properties=_terminal_properties(
                                terminal_status="error",
                                error_code=envelope.code,
                            ),
                        )
                    await err_db.commit()
            except Exception as mark_exc:  # pragma: no cover - defensive
                log.warning("stream.mark_error.failed", exc_info=mark_exc)
            with contextlib.suppress(Exception):
                await clear_stop_async(stream_id)
        return
    finally:
        if not pump_task.done():
            pump_task.cancel()
            # Suppress ONLY CancelledError from this final cleanup cancel; a
            # genuine provider exception would have surfaced via the queue.
            with contextlib.suppress(asyncio.CancelledError):
                await pump_task
        # Stop-registry leak guard: every terminal path must drop the live stop
        # signal exactly once. The stop / disconnect, CancelledError, and
        # `error` branches each `clear_stop` before returning, but the natural
        # `done` terminal path returns through this `finally` WITHOUT having
        # cleared — leaving a `_STOP_REQUESTS` entry behind if a (late) stop was
        # ever requested for this stream. `clear_stop` is idempotent (a plain
        # `set.discard`), so re-clearing here is harmless on the paths that
        # already cleared and closes the leak on the `done` path. Guarded on a
        # non-None stream_id (temporary turns never register a stream).
        if stream_id is not None:
            await clear_stop_async(stream_id)


async def run_detached_producer(
    *,
    buffer: ReplayLogBuffer,
    session_factory: async_sessionmaker[AsyncSession],
    provider: Provider,
    binding: TierBinding,
    requested_tier_id: ModelTierId,
    conversation_id: UUID | None,
    user_message_id: UUID,
    user_text: str,
    history: list[ChatMessage],
    is_temporary: bool,
    is_initial: bool = True,
    user_id: UUID | None = None,
    api_key: str | None = None,
    provider_id: str | None = None,
    stream_id: UUID | None = None,
    router_substitution: SubstitutionReasonCode | None = None,
    web_search: bool = False,
    response_format: ResponseFormat | None = None,
    attachments: list[AttachmentPayload] | None = None,
    custom_instructions: str | None = None,
    memory_facts: list[str] | None = None,
    memory_fact_ids: list[str] | None = None,
    memory_enabled: bool = False,
    reasoning_effort_override: str | None = None,
    thinking_override: bool | None = None,
    monthly_quota_usd_override: float | None = None,
    fallback_binding: TierBinding | None = None,
    fallback_provider_id: str | None = None,
    fallback_api_key: str | None = None,
    fallback_substitution: SubstitutionReasonCode | None = None,
    tool_approval: ToolApprovalDecision | None = None,
    resume_seed: ResumeToolSeed | None = None,
) -> None:
    """Drive `stream_and_persist` DETACHED from any HTTP connection (flag ON).

    Runs the EXACT same producer body as the flag-off path — same provider pump,
    accumulation, cost ledger, usage rollup, attribution, persistence, title
    autogen — so cost/budget/lifecycle semantics are identical. The only
    differences are structural, not behavioral:

    1. It owns a FRESH DB session (the originating POST request's session closes
       as soon as the POST returns; the producer outlives it). The session is
       derived from the process-wide `session_factory` so persistence lands on
       the right engine in both prod and tests.
    2. It hands `stream_and_persist` a `_NeverDisconnectedRequest`, so a client
       disconnect can NOT tear the turn down. The live cancel paths that remain
       are the dedicated stop endpoint (via `stop_registry`, polled inside
       `stream_and_persist`) and natural completion — exactly the resumable
       semantics.
    3. Instead of yielding wire events to a socket, it APPENDS each event to the
       `ReplayBuffer`, from which the POST connection + any reconnects tail.

    On completion (terminal / stopped / error) — or an unexpected exception — it
    `mark_done`s the buffer so every subscriber drains and closes. ONLY this
    producer persists; subscribers never write to the DB, so a reconnect cannot
    double-persist or double-count.
    """
    terminal_kind = "stopped"  # default: no terminal/error frame ⇒ stopped/cancelled
    try:
        async with session_factory() as session:
            async for event in stream_and_persist(
                request=_NeverDisconnectedRequest(),  # type: ignore[arg-type]
                db=session,
                provider=provider,
                binding=binding,
                requested_tier_id=requested_tier_id,
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                user_text=user_text,
                history=history,
                is_temporary=is_temporary,
                is_initial=is_initial,
                user_id=user_id,
                api_key=api_key,
                provider_id=provider_id,
                stream_id=stream_id,
                router_substitution=router_substitution,
                web_search=web_search,
                response_format=response_format,
                attachments=attachments,
                custom_instructions=custom_instructions,
                memory_facts=memory_facts,
                memory_fact_ids=memory_fact_ids,
                memory_enabled=memory_enabled,
                reasoning_effort_override=reasoning_effort_override,
                thinking_override=thinking_override,
                monthly_quota_usd_override=monthly_quota_usd_override,
                fallback_binding=fallback_binding,
                fallback_provider_id=fallback_provider_id,
                fallback_api_key=fallback_api_key,
                fallback_substitution=fallback_substitution,
                tool_approval=tool_approval,
                resume_seed=resume_seed,
            ):
                # Mirror the last frame kind so the buffer's terminal_kind is
                # observable. `terminal`/`error` are the only closing frames;
                # absence of either means the stop-path teardown ran (stopped).
                if event.event == "terminal":
                    terminal_kind = "done"
                elif event.event == "error":
                    terminal_kind = "error"
                await buffer.append(event)
    except asyncio.CancelledError:
        # Shutdown/lifespan cancel. `stream_and_persist` already closed out its
        # own durable `stream` bookkeeping in its CancelledError branch before
        # this propagated; we just close the buffer so subscribers drain.
        terminal_kind = "stopped"
        with contextlib.suppress(Exception):
            await buffer.mark_done(terminal_kind=terminal_kind)
        raise
    except Exception as exc:  # pragma: no cover - defensive
        # `stream_and_persist` already converts provider errors into an `error`
        # frame internally; reaching here means an unexpected failure. Surface
        # nothing to a socket (there isn't one) — just close the buffer.
        log.warning("resumable.producer.failed", exc_info=exc)
        terminal_kind = "error"
    finally:
        # Idempotent: a natural terminal already set the kind via the loop; the
        # CancelledError branch marked done before re-raising. This is the
        # normal close for the non-cancelled paths.
        with contextlib.suppress(Exception):
            await buffer.mark_done(terminal_kind=terminal_kind)


def spawn_detached_producer(
    **kwargs: Any,
) -> asyncio.Task[None]:
    """Spawn `run_detached_producer` as a tracked, GC-safe background task.

    Held strongly in `_PRODUCER_TASKS` so it survives the POST request and so
    the lifespan can cancel it on shutdown. Discards itself on completion.
    """
    task = asyncio.create_task(run_detached_producer(**kwargs))
    _PRODUCER_TASKS.add(task)
    task.add_done_callback(_PRODUCER_TASKS.discard)
    return task

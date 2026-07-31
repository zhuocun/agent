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
from collections.abc import AsyncIterator, Collection
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID, uuid4

import jsonschema
import structlog
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette import ServerSentEvent

from app.agentic import budget
from app.agentic.clarify import (
    ClarificationRecord,
    nonblank_answers,
    parse_clarification_records,
)
from app.agentic.continuation import (
    CONTINUATION_INPUT_KEY,
    put_continuation_in_server_state,
    put_run_ledger_in_server_state,
    sanitize_message_parts_for_api,
    strip_reserved_keys,
    usage_from_wire,
)
from app.agentic.orchestrator import run_orchestrator, run_single
from app.agentic.retry import is_retryable_provider_error
from app.config import get_settings
from app.db.models import Message
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
    RunCost,
    Sources,
    StatusUpdate,
    SubagentDone,
    SubagentStarted,
    ToolCall,
    ToolDefinition,
    ToolResult,
    UsageUpdate,
)
from app.providers.tiers import TierBinding, get_binding
from app.schemas.common import ModelTierId, SubagentOutcome, SubstitutionReasonCode
from app.schemas.conversation import ToolApprovalDecision
from app.schemas.message import (
    AgenticRunSummaryPart,
    ModelAttribution,
    ReasoningPart,
    SourcesPart,
    StatusPart,
    SubagentPart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from app.schemas.stream_events import (
    AnswerDeltaEvent,
    ReasoningDeltaEvent,
    ReasoningDoneEvent,
    RunCostEvent,
    SourcesEvent,
    StatusEvent,
    SubagentDoneEvent,
    SubagentStartedEvent,
    SubmittedEvent,
    TerminalEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from app.search.protocol import SourceItem
from app.streaming.constants import (
    EMPTY_REPLY_FALLBACK,
    empty_reply_retry_nudge,
    main_answer_is_empty,
)
from app.streaming.empty_reply_retry import run_chat_with_empty_retry
from app.streaming.replay_registry import ReplayLogBuffer
from app.streaming.sse import (
    encode_answer_delta,
    encode_error,
    encode_reasoning_delta,
    encode_reasoning_done,
    encode_run_cost,
    encode_sources,
    encode_status,
    encode_subagent_done,
    encode_subagent_started,
    encode_submitted,
    encode_terminal,
    encode_tool_call,
    encode_tool_result,
)
from app.streaming.stop_registry import clear_stop_async, is_stop_requested_async
from app.tools.agent_loop import MakeStream, run_agent_loop, tool_feedback_to_history
from app.tools.approval_settlement import (
    ApprovalDecisionConflict,
    ApprovalSettlementIncomplete,
    claim_and_settle_approval_outcome,
)
from app.tools.builtin import advertised_tool_specs, execute_tool
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


@dataclass
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

    BE-007: when ``settled_result`` is set the route already claimed/settled the
    side effect on the paused row — the handler must emit that result and must
    NOT re-execute.

    BE-005: ``agentic_continuation`` resumes a paused worker in place
    (no re-plan) when present. Aggregator continuation is not supported
    (O-011); aggregators run without gated tools.
    """

    tool_call_id: str
    name: str
    label: str | None
    decision: str
    input: dict[str, Any] | None
    # Plan-approval resume (agentic, T6): True when this seed resumes an
    # orchestration PLAN approval (the pseudo `agentic_plan_approval` tool)
    # rather than a real registry tool. The handler then re-runs the
    # orchestrator with `plan_approved=(decision == "approve")` instead of
    # emitting a seeded `tool_result`.
    is_plan: bool = False
    # Immutable sub-questions from the paused plan tool input (BE-039). Only set
    # when ``is_plan`` and the pending part carried a ``plan`` list.
    approved_plan: tuple[str, ...] | None = None
    # Clarify-before-plan resume (plan 02): True when this seed resumes an
    # `agentic_plan_clarify` pause. Handler re-runs orchestrator with
    # `clarify_answered` / full Q&A records instead of a seeded tool_result.
    is_clarify: bool = False
    # Bound question/answer pairs (C-002). Prefer this over answer-only tuples so
    # question text reaches planner / workers / continuation / plan-approval.
    clarify_records: tuple[ClarificationRecord, ...] | None = None
    # Legacy answer-only list kept for callers that only need non-blank texts;
    # when ``clarify_records`` is set, answers are derived from it.
    clarify_answers: tuple[str, ...] | None = None
    # BE-007: pre-settled execution result (claim happened in the producer after
    # SSE ownership — see stream_and_persist settlement block).
    settled_result: Any | None = None
    # BE-005: fan-out continuation for worker tool HITL (O-011: aggregator
    # continuation is not supported).
    agentic_continuation: Any | None = None
    # Original user text for agentic continuation resume (not the Tool approved: stub).
    resume_user_text: str | None = None
    # H-007: deferred claim/settle inputs — executed inside the stream producer
    # after EventSourceResponse owns cancellation / stream lifecycle.
    paused_message_id: UUID | None = None
    pending_settle: bool = False
    # B4: plan-approval pause ledger (from Message.server_state, not tool input).
    prior_planner_cost_usd: float = 0.0
    prior_planner_usage: UsageUpdate | None = None
    # B5: single-mode pause ledger (from Message.server_state).
    prior_run_cost_usd: float = 0.0
    prior_run_usage: UsageUpdate | None = None
    # FL-28: orchestration mode the pause was taken in, for EVERY pause shape
    # (plan approval / clarify / single / worker continuation). The route pins
    # this instead of honouring a client-chosen `agenticMode`, which would
    # consume the approval and then discard the approved work.
    orchestration_mode: Literal["single", "deep_research"] | None = None


@dataclass
class _SubagentAccumulator:
    """Per-subagent accumulation for an agentic turn (T3).

    Mirrors the flat single-stream accumulators (reasoning / answer / tool
    transcript) but scoped to one orchestrator subagent, so the persisted parts
    can be grouped under a `subagent` marker. `cost_usd` / `usage` are filled from
    the matching `SubagentDone`. Only constructed when `agentic_active`.
    """

    label: str
    role: str
    reasoning: list[str] = field(default_factory=list)
    answer: list[str] = field(default_factory=list)
    tool_parts: list[dict[str, Any]] = field(default_factory=list)
    cost_usd: float | None = None
    usage: UsageUpdate = field(default_factory=UsageUpdate)
    outcome: SubagentOutcome = "succeeded"
    # True once a `SubagentDone` has been folded in. Stop/disconnect uses this to
    # distinguish finished workers from ones that were still in flight when the
    # pump was cancelled (orchestrator may have enqueued SubagentDone(stopped)
    # on its internal queue, but those events never reach the handler).
    terminal: bool = False
    substitution: SubstitutionReasonCode | None = None
    substituted_provider: str | None = None
    substituted_model: str | None = None
    substituted_display_label: str | None = None
    # Per-worker web-search status/sources (FE-001).
    latest_status: tuple[str, str] | None = None
    search_items: list[Any] = field(default_factory=list)
    saw_sources: bool = False
    # FL-37: per-subagent reasoning wall-clock (monotonic start, closed seconds).
    reasoning_started_at: float | None = None
    reasoning_duration_sec: float | None = None


def mark_unfinished_subagents_stopped(
    subagents: dict[str, _SubagentAccumulator],
) -> None:
    """Rewrite in-flight subagent outcomes to ``stopped`` on stop/disconnect.

    Pump cancel acloses the orchestrator before worker ``SubagentDone(stopped)``
    events can be yielded onto the handler queue. Accumulators that never
    received a Done would otherwise persist with the default ``succeeded``.
    """
    for acc in subagents.values():
        if not acc.terminal:
            acc.outcome = "stopped"


def mark_unfinished_subagents_paused(
    subagents: dict[str, _SubagentAccumulator],
) -> None:
    """Mark non-terminal accumulators on HITL pause (B15).

    Uses ``stopped`` (already in ``SubagentOutcome`` / FE) rather than a new
    literal: unknown wire values fall through to a green check on the FE today.
    ``stopped`` renders as a non-success cancelled state.
    """
    mark_unfinished_subagents_stopped(subagents)


def build_agentic_run_summary_part(ev: RunCost) -> AgenticRunSummaryPart:
    """Fold a ``RunCost`` into the persisted receipt (FL-33-a).

    Every receipt persists, including a plan pause and a worker-HITL pause: the
    old gate (``phase == "final" or partial or budget_halted or
    failed_worker_count > 0``) dropped a paused run's receipt entirely, so reload
    re-derived a meter that both showed a different number and claimed
    exact/final while the plan card above it still said "(estimate)".

    A non-final phase is by definition not a finished run, so it folds to
    ``partial`` regardless of the flags — a resumable pause must never read as a
    completed receipt. The live and drain gates both call this so they cannot
    drift (F2 DoD 6).
    """
    return AgenticRunSummaryPart(
        outcome=(
            "partial"
            if (
                ev.partial
                or ev.budget_halted
                or ev.failed_worker_count > 0
                or ev.phase != "final"
            )
            else "complete"
        ),
        budget_halted=ev.budget_halted,
        failed_workers=ev.failed_worker_count,
        subtotal_usd=ev.subtotal_usd,
        cap_usd=ev.cap_usd,
        cost_confidence=ev.confidence,
        cost_phase=ev.phase,
    )


def tool_results_from_message_parts(
    parts: list[dict[str, Any]] | None,
    *,
    exclude_tool_call_ids: Collection[str] | None = None,
) -> list[ToolResult]:
    """Collect durable ``tool_result`` parts for single-mode resume seeding (B7).

    Mirrors worker continuation seeding from ``tool_transcript``: already-executed
    same-round results must be fed back as ``initial_tool_results`` alongside the
    settled gated approval result.
    """
    if not parts:
        return []
    exclude = set(exclude_tool_call_ids or ())
    out: list[ToolResult] = []
    for part in parts:
        if not isinstance(part, dict) or part.get("type") != "tool_result":
            continue
        call_id = str(part.get("toolCallId") or part.get("tool_call_id") or "")
        if not call_id or call_id in exclude:
            continue
        status_raw = part.get("status")
        status: Literal[
            "running", "succeeded", "failed", "cancelled", "awaiting_approval"
        ] = (
            status_raw
            if status_raw
            in ("running", "succeeded", "failed", "cancelled", "awaiting_approval")
            else "succeeded"
        )
        approval_raw = part.get("approvalState") or part.get("approval_state")
        approval_state: Literal[
            "not_required", "pending", "approved", "rejected"
        ] = (
            approval_raw
            if approval_raw in ("not_required", "pending", "approved", "rejected")
            else "not_required"
        )
        out.append(
            ToolResult(
                tool_call_id=call_id,
                name=str(part.get("name") or ""),
                label=str(part["label"]) if isinstance(part.get("label"), str) else None,
                status=status,
                approval_state=approval_state,
                summary=(
                    str(part["summary"]) if isinstance(part.get("summary"), str) else None
                ),
                output=dict(part.get("output") or {})
                if isinstance(part.get("output"), dict)
                else {},
                error=str(part["error"]) if isinstance(part.get("error"), str) else None,
            )
        )
    return out


# Bound the provider→consumer queue so a slow SSE client cannot buffer an
# unbounded number of deltas in process memory (B23). ``put`` applies
# backpressure; 256 ≈ a few seconds of high-frequency token deltas.
_PROVIDER_QUEUE_MAXSIZE = 256

# Heartbeat ``stream.updated_at`` well below the reaper TTL (default 900s) so
# long agentic runs are not mistaken for crash orphans (B10).
_STREAM_HEARTBEAT_INTERVAL_S = 60.0


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
    return is_retryable_provider_error(exc)


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
        title_result = await provider.complete(
            model_id=binding.model_id,
            history=[],
            user_text=_TITLE_AUTOGEN_PROMPT + user_text,
            api_key=api_key,
        )
        # Strip surrounding whitespace/quotes/trailing period defensively —
        # providers sometimes ignore "no quotes" instructions.
        cleaned = title_result.text.strip().strip('"').strip("'").rstrip(".")
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
        reply_result = await provider.complete(
            model_id=model_id,
            history=[],
            user_text=_MEMORY_EXTRACTION_PROMPT + transcript,
            api_key=api_key,
        )
        facts = _parse_extracted_facts(reply_result.text)
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
    agentic_mode: Literal["single", "deep_research"] | None = None,
    budget_headroom_usd: float | None = None,
    requested_agentic_mode: Literal["single", "deep_research"] | None = None,
    agentic_coercion_reason: Literal["entitlement"] | None = None,
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
            requested_agentic_mode=requested_agentic_mode,
            effective_agentic_mode=agentic_mode,
            agentic_coercion_reason=agentic_coercion_reason,
        )
    )
    turn_started_at = time.monotonic()
    first_answer_ms: int | None = None

    # Accumulators for parts + usage.
    reasoning_buf: list[str] = []
    answer_buf: list[str] = []
    final_usage = UsageUpdate()
    emitted_reasoning_done = False
    # FL-37: reasoning wall-clock for the untagged stream, measured on the same
    # monotonic base as `first_answer_ms` and persisted as ReasoningPart
    # `durationSec` so "Thought for Ns" survives a reload.
    reasoning_started_at: float | None = None
    reasoning_duration_sec: float | None = None
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
    # H-012: continuation blobs keyed by tool_call_id — written to
    # Message.server_state, never into client-visible tool_call.input.
    pending_server_continuations: dict[str, dict[str, Any]] = {}
    # B4/B5: pause-turn run-cap ledger seeds for Message.server_state (not parts).
    pending_planner_cost_usd: float = 0.0
    pending_planner_usage: UsageUpdate | None = None
    pending_prior_run_cost_usd: float = 0.0
    pending_prior_run_usage: UsageUpdate | None = None
    # FL-28: orchestration mode stamped onto the pause row so resume pins it.
    pending_orchestration_mode: str | None = None
    # Captured once so the per-turn tools gate + agent-loop wrapping read a
    # stable value (and tests can override via a settings cache flush).
    handler_settings = get_settings()
    tools_active = handler_settings.tools_enabled
    # Agentic mode (T1 seam): route into the orchestrator ONLY when the flag is
    # on, tools are on (the orchestrator builds on the tool seam), AND a non-None
    # mode was requested. Any one of these false ⇒ the existing single-stream
    # path runs unchanged, so a flag-off turn — and an agentic-off turn that still
    # carries `agenticMode` — is byte-for-byte identical to a pre-agentic build.
    #
    # H-002 / O-003: a durable worker continuation pins orchestration mode. When
    # the client omits/changes agenticMode on resume, derive mode from the
    # checkpoint so the continuation cannot be silently bypassed after settle.
    if (
        resume_seed is not None
        and resume_seed.agentic_continuation is not None
        and getattr(resume_seed.agentic_continuation, "orchestration_mode", None)
        in ("single", "deep_research")
    ):
        agentic_mode = resume_seed.agentic_continuation.orchestration_mode
    elif (
        resume_seed is not None
        and resume_seed.agentic_continuation is not None
        and agentic_mode is None
    ):
        # Legacy continuations without an explicit pin default to deep_research.
        agentic_mode = "deep_research"
    agentic_active = (
        tools_active and handler_settings.agentic_enabled and agentic_mode is not None
    )
    # Plan-approval resume (T6): a `toolApproval` resume that targets the plan
    # pseudo-tool carries the human decision back into the orchestrator as
    # `plan_approved` (re-run + fan out / decline) — it does NOT emit a seeded
    # `tool_result` the way a real-tool resume does. None on every other path.
    plan_resume = resume_seed is not None and resume_seed.is_plan
    plan_approved: bool | None = (
        (resume_seed.decision == "approve") if plan_resume and resume_seed is not None else None
    )
    approved_plan: list[str] | None = (
        list(resume_seed.approved_plan)
        if plan_resume and resume_seed is not None and resume_seed.approved_plan is not None
        else None
    )
    # Clarify-before-plan resume (plan 02): same pattern as plan approval.
    # Plan-approval resume also carries prior clarifications (if any) so a
    # clarify → plan-approval dual HITL keeps answers across the second pause.
    clarify_resume = resume_seed is not None and resume_seed.is_clarify
    clarify_answered: bool | None
    clarify_answers: list[str] | None
    clarify_records: list[ClarificationRecord] | None

    def _records_from_seed(seed: ResumeToolSeed) -> list[ClarificationRecord] | None:
        if seed.clarify_records is not None:
            return list(seed.clarify_records)
        if seed.clarify_answers is not None:
            # Legacy answer-only seed — questions unknown.
            return parse_clarification_records(
                [
                    {"questionId": str(i), "question": "", "answer": a}
                    for i, a in enumerate(seed.clarify_answers)
                ]
            )
        return None

    if plan_resume and resume_seed is not None:
        # Past the clarify gate; re-attach any clarifications stored on the plan
        # tool input so workers/synthesis still see them.
        clarify_answered = True
        clarify_records = _records_from_seed(resume_seed)
        clarify_answers = (
            nonblank_answers(clarify_records) if clarify_records is not None else []
        )
    elif clarify_resume and resume_seed is not None:
        clarify_answered = resume_seed.decision == "approve"
        clarify_records = _records_from_seed(resume_seed)
        clarify_answers = (
            list(r.answer for r in clarify_records)
            if clarify_records is not None
            else None
        )
    else:
        clarify_answered = None
        clarify_answers = None
        clarify_records = None
    # Per-subagent accumulation for an agentic turn (T3). Ordered by first-seen
    # `SubagentStarted` so the persisted transcript groups subagents in emission
    # order. Empty (and unused) on every non-agentic turn.
    agentic_order: list[str] = []
    agentic_subagents: dict[str, _SubagentAccumulator] = {}
    # Populated from the final `RunCost(partial=...)` tick for persistence (FE-015).
    agentic_run_summary: AgenticRunSummaryPart | None = None

    def _sub(subagent_id: str) -> _SubagentAccumulator:
        """Fetch (or defensively create) the accumulator for `subagent_id`.

        `SubagentStarted` always precedes a subagent's tagged content events, so
        the create-on-miss branch is defensive only.
        """
        acc = agentic_subagents.get(subagent_id)
        if acc is None:
            acc = _SubagentAccumulator(label=subagent_id, role="subagent")
            agentic_subagents[subagent_id] = acc
            agentic_order.append(subagent_id)
        return acc

    def _open_reasoning_clock(subagent_id: str | None) -> None:
        """FL-37: start the reasoning clock on the first delta for this scope."""
        nonlocal reasoning_started_at
        if agentic_active and subagent_id is not None:
            acc = _sub(subagent_id)
            if acc.reasoning_started_at is None:
                acc.reasoning_started_at = time.monotonic()
            return
        if reasoning_started_at is None:
            reasoning_started_at = time.monotonic()

    def _close_reasoning_clock(subagent_id: str | None) -> None:
        """FL-37: close the reasoning clock at ReasoningDone / first AnswerDelta.

        Scoped per subagent on agentic turns, where several reasoning blocks
        interleave. Idempotent, and a no-op when the scope emitted no reasoning,
        so a turn without reasoning persists no duration at all.
        """
        nonlocal reasoning_duration_sec
        now = time.monotonic()
        if agentic_active and subagent_id is not None:
            # `get`, not `_sub`: a stray tagged done must not open a section.
            acc = agentic_subagents.get(subagent_id)
            if (
                acc is not None
                and acc.reasoning_started_at is not None
                and acc.reasoning_duration_sec is None
            ):
                acc.reasoning_duration_sec = max(0.0, now - acc.reasoning_started_at)
            return
        if reasoning_started_at is not None and reasoning_duration_sec is None:
            reasoning_duration_sec = max(0.0, now - reasoning_started_at)

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
    # Empty-reply retry analytics (§9 / amendment A): read off the internal,
    # non-wire `Complete.empty_retry` / `empty_retry_recovered` markers set by
    # the agent loop / plain-chat wrapper. `recovered` is taken straight from the
    # marker — NOT re-derived from post-inject resolved text, which would always
    # read True once the static fallback lands. Logged in `turn.done`.
    empty_retry_seen = False
    empty_retry_recovered_seen = False

    # Build ONE raw provider stream for the current working route + optional
    # agent-loop tool feedback. `tool_feedback` carries the results the agent
    # loop accumulated across rounds, appended to `history` as synthetic turns
    # (the `Provider.stream` Protocol intentionally has no tool params). Empty on
    # round 1 / the non-tool path, so the provider stream is byte-for-byte
    # unchanged there.
    # System prefix (current UTC datetime + custom instructions + long-term
    # memory) and the clean per-turn user text, assembled once via
    # `prompt_assembly` (T20). Hoisting memory + instructions into the system
    # prefix (instead of wrapping them into the user turn) keeps the user turn
    # clean. The datetime block always leads, so `turn_system_prefix` is always
    # a non-None string and every real-provider turn carries a system role.
    turn_system_prefix = build_system_prefix(custom_instructions, memory_facts or [])
    turn_user_text = build_user_turn(user_text)

    # Native tool advertisement for REAL providers (agent loop). When tools are
    # enabled we hand the provider the PROD-SAFE tool schemas so it can advertise
    # them and parse the model's calls into structured `ToolCall` events; the
    # fake provider ignores this and uses its deterministic markers. Only
    # `advertised_tool_specs()` (prod_safe=True) is offered, so a real model is
    # never shown a stub like `calendar_create_event` that resolves to nothing —
    # the fake provider/e2e still exercises that tool's approval gate via its
    # `TOOL_APPROVE:` marker. None when tools are off ⇒ no tools advertised,
    # provider stream unchanged. Worker streams further filter via
    # `allowed_tools` (empty ⇒ advertise nothing).
    def _tool_definitions_for(
        allowed_tools: Collection[str] | None = None,
    ) -> list[ToolDefinition] | None:
        if not tools_active:
            return None
        specs = advertised_tool_specs(allowed_names=allowed_tools)
        if not specs:
            return None
        return [
            ToolDefinition(name=spec.name, label=spec.label, parameters=spec.schema)
            for spec in specs
        ]

    turn_tool_definitions = _tool_definitions_for()

    def _build_raw_stream(
        tool_feedback: list[ToolResult],
        suppress_tools: bool = False,
        user_text_override: str | None = None,
        *,
        tool_definitions: list[ToolDefinition] | None = None,
        web_search_override: bool | None = None,
        answer_nudge: bool = False,
    ) -> AsyncIterator[ProviderEvent]:
        advertised = (
            None
            if suppress_tools
            else (turn_tool_definitions if tool_definitions is None else tool_definitions)
        )
        round_history = history + tool_feedback_to_history(tool_feedback)
        effective_web_search = (
            web_search if web_search_override is None else web_search_override
        )
        # Empty-reply retry nudge (response-format aware): appended to the system
        # preamble ONLY on an empty-retry pass so the model is told its prior
        # attempt produced no answer and must answer now without tools. The
        # plain-prose clause is dropped when structured output was requested.
        effective_system_prefix = turn_system_prefix
        if answer_nudge:
            effective_system_prefix = (
                f"{turn_system_prefix}\n\n"
                + empty_reply_retry_nudge(
                    response_format_requested=response_format is not None
                )
            )
        return active_provider.stream(
            model_id=binding.model_id,
            history=round_history,
            user_text=turn_user_text if user_text_override is None else user_text_override,
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
            # Sources. Phase factories (planner / quiet aggregator) may force
            # False via web_search_override.
            web_search=effective_web_search,
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
            # System preamble (UTC datetime + custom instructions + memory).
            # Always non-None — the datetime block is always present. Carries the
            # empty-reply retry nudge appended when `answer_nudge` is set.
            system_prefix=effective_system_prefix,
            # Agent-loop tools advertised to a real provider (None when tools are
            # off or the caller scoped an empty allowlist). The fake provider
            # ignores this; the OpenAI/Anthropic adapters advertise them natively
            # and emit `ToolCall`s the agent loop fulfils. On the loop's compelled
            # final pass (`suppress_tools=True`) we advertise NO tools so a greedy
            # provider is forced to answer instead of requesting yet another tool
            # and returning a blank turn.
            tools=advertised,
        )

    def _agentic_fresh_make_stream(
        worker_user_text: str,
        *,
        allowed_tools: Collection[str] | None = None,
        system_prefix: str | None = None,
        response_format: ResponseFormat | None = None,
        web_search: bool = False,
    ) -> MakeStream:
        """Fresh-context `MakeStream` for the verifier judge (agentic only).

        Industry / plan 02 fresh-context means an empty judge session: no
        conversation history, memory, attachments, or turn web_search — only the
        rubric (``system_prefix``) + DATA prompt the orchestrator passes as
        ``user_text``. ``allowed_tools`` still scopes advertise (verifier passes
        empty). ``response_format`` requests structured JSON when the verifier
        supplies a schema. ``web_search`` is accepted for signature parity and
        always forced False.
        """
        _ = web_search
        scoped_tools = (
            _tool_definitions_for(allowed_tools)
            if allowed_tools is not None
            else None
        )
        judge_response_format = response_format
        judge_system_prefix = system_prefix

        def _make(
            tool_feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            # `answer_nudge` accepted for `MakeStream` conformance but IGNORED:
            # the verifier fresh-context judge stays pristine (no empty retry runs
            # for workers/verifier), so no nudge is ever appended here.
            _ = answer_nudge
            # Tool-feedback rounds (if any) stay isolated — never splice chat
            # history into the judge session.
            round_history = tool_feedback_to_history(tool_feedback)
            return active_provider.stream(
                model_id=binding.model_id,
                history=round_history,
                user_text=worker_user_text,
                attachments=None,
                api_key=active_api_key,
                thinking=(
                    thinking_override
                    if thinking_override is not None
                    else binding.thinking
                ),
                reasoning_effort=(
                    reasoning_effort_override
                    if reasoning_effort_override is not None
                    else binding.reasoning_effort
                ),
                web_search=False,
                response_format=judge_response_format,
                supports_vision=binding.supports_vision,
                system_prefix=judge_system_prefix,
                tools=None if suppress_tools else scoped_tools,
            )

        return _make

    def _agentic_make_stream(
        worker_user_text: str,
        *,
        allowed_tools: Collection[str] | None = None,
        web_search: bool | None = None,
        system_prefix: str | None = None,
        response_format: ResponseFormat | None = None,
    ) -> MakeStream:
        """Build a per-subagent `MakeStream` over the active route (agentic only).

        Captures the same route/binding/history/hints `_build_raw_stream` uses;
        only the user text varies per subagent (the orchestrator hands each worker
        its sub-question prompt). ``allowed_tools`` scopes both advertise and
        (via the orchestrator) execute for workers — empty ⇒ no registry tools.
        ``web_search`` overrides the turn flag when set (planner/quiet aggregator
        force False). ``system_prefix`` / ``response_format`` are accepted for
        factory signature parity with the fresh judge; ignored here (workers use
        the turn preamble).
        """
        _ = (system_prefix, response_format)
        scoped_tools = (
            _tool_definitions_for(allowed_tools)
            if allowed_tools is not None
            else turn_tool_definitions
        )
        phase_web_search = web_search  # None → inherit turn flag

        def _make(
            tool_feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            return _build_raw_stream(
                tool_feedback,
                suppress_tools,
                worker_user_text,
                tool_definitions=scoped_tools,
                web_search_override=phase_web_search,
                answer_nudge=answer_nudge,
            )

        return _make

    _cached_fb_provider: list[Provider | None] = [None]

    def _agentic_fallback_make_stream(
        worker_user_text: str,
        *,
        allowed_tools: Collection[str] | None = None,
    ) -> MakeStream:
        """Per-subagent stream factory over the fallback route (agentic only)."""
        assert fallback_binding is not None
        if _cached_fb_provider[0] is None:
            _cached_fb_provider[0] = build_provider(
                get_settings(),
                provider_id=fallback_provider_id or fallback_binding.provider_id,
                api_key=fallback_api_key,
            )
        fb_binding = fallback_binding
        fb_provider = _cached_fb_provider[0]
        assert fb_provider is not None
        fb_api_key = fallback_api_key
        scoped_tools = (
            _tool_definitions_for(allowed_tools)
            if allowed_tools is not None
            else turn_tool_definitions
        )

        def _make(
            tool_feedback: list[ToolResult],
            suppress_tools: bool = False,
            *,
            answer_nudge: bool = False,
        ) -> AsyncIterator[ProviderEvent]:
            round_history = history + tool_feedback_to_history(tool_feedback)
            fb_system_prefix = turn_system_prefix
            if answer_nudge:
                fb_system_prefix = (
                    f"{turn_system_prefix}\n\n"
                    + empty_reply_retry_nudge(
                        response_format_requested=response_format is not None
                    )
                )
            return fb_provider.stream(
                model_id=fb_binding.model_id,
                history=round_history,
                user_text=worker_user_text,
                attachments=attachments,
                api_key=fb_api_key,
                thinking=(
                    thinking_override if thinking_override is not None else fb_binding.thinking
                ),
                reasoning_effort=(
                    reasoning_effort_override
                    if reasoning_effort_override is not None
                    else fb_binding.reasoning_effort
                ),
                web_search=web_search,
                response_format=response_format,
                supports_vision=fb_binding.supports_vision,
                system_prefix=fb_system_prefix,
                tools=None if suppress_tools else scoped_tools,
            )

        return _make

    def _phase_image_count(subagent_id: str | None, role: str | None) -> int:
        """Charging follows transport: a phase pays for what its stream sends.

        `image_token_formula` folds estimated image tokens into the input bucket,
        so a phase is charged the turn's `image_attachment_count` if and only if
        that phase's stream factory actually attaches the images. Every factory
        — `_build_raw_stream` (single primary, and the planner / worker /
        aggregator phases via `_agentic_make_stream`) and
        `_agentic_fallback_make_stream` — passes `attachments=attachments`
        unconditionally, so those prompts are NOT text-only and the provider
        re-charges the images on each of those calls.

        The verifier is the sole genuinely text-only phase:
        `_agentic_fresh_make_stream` passes `attachments=None` for its
        fresh-context judge session, so it never pays for the turn's images.

        (Supersedes FL-36, whose premise that planner / worker / aggregator
        prompts are text-only was false and made every deep_research turn with
        attachments under-bill the whole image component.)
        """
        _ = subagent_id
        if role == "verifier":
            return 0
        return image_attachment_count

    def _cost_for_usage(usage: UsageUpdate) -> float:
        """Price an accumulated usage for the active binding (agentic only).

        FL-34-b: `subtotal_usd` **is** the total — `session_surcharge_usd` is a
        disclosure field describing part of it, so adding it double-charges the
        long-context surcharge.
        Image tokens are charged on every phase this prices, because every
        non-verifier stream factory sends the turn's attachments (see
        `_phase_image_count`). The verifier is priced by
        `_verifier_cost_for_usage` instead.
        """
        breakdown = compute_cost_breakdown(
            usage=usage,
            binding=binding,
            image_count=image_attachment_count,
        )
        return breakdown.subtotal_usd

    def _verifier_cost_for_usage(usage: UsageUpdate) -> float:
        """Phase pricer for the fresh-context judge (V-011).

        The verifier sends ``attachments=None``; never inherit the turn's image
        attachment count into judge pricing.
        """
        breakdown = compute_cost_breakdown(
            usage=usage,
            binding=binding,
            image_count=0,
        )
        return breakdown.subtotal_usd

    def _fallback_cost_for_usage(usage: UsageUpdate) -> float:
        """Price usage against the fallback binding (FE-009).

        `_agentic_fallback_make_stream` sends the turn's attachments too, so the
        fallback route is charged the image component exactly like the primary.
        """
        assert fallback_binding is not None
        breakdown = compute_cost_breakdown(
            usage=usage,
            binding=fallback_binding,
            image_count=image_attachment_count,
        )
        return breakdown.subtotal_usd

    def _estimate_run_cost(sub_question_count: int) -> float:
        """Worst-case run-cost estimate for pre-spawn admission (agentic only).

        Called module-qualified so the budget methodology stays in one place
        (and stays test-overridable). Reads the working `binding` at call time so
        a fallback rebuild re-estimates against the fallback route.
        """
        return budget.estimate_run_cost(
            sub_question_count=sub_question_count,
            binding=binding,
            settings=handler_settings,
            image_count=image_attachment_count,
        )

    # The current provider iterator. Rebuilt on a fallback retry so the pump
    # drains the alternate route. When agentic mode is active the stream is the
    # multi-agent orchestrator (which itself drives the agent loop per subagent);
    # else when tools are enabled the raw stream is wrapped in the bounded agent
    # loop (which intercepts `ToolCall`s, runs the registry, and emits the HITL
    # `AwaitingApproval` pause); otherwise it is the raw provider stream —
    # byte-for-byte the pre-tools path. The fallback rebuild path calls this
    # again, so a fallback route is wrapped identically.

    # H-007: claim/execute/settle AFTER SSE ownership (this generator has started)
    # so stop/disconnect can cancel and settlement cleanup can terminalize the
    # claim. Route-level prepare only validates and defers settlement here.
    # Poll stop/disconnect while execute runs so a mid-execute stop cancels the
    # executor task (settlement catches CancelledError and terminalizes).
    async def _release_stream_after_approval_stop() -> None:
        """Close durable stream bookkeeping after stop around deferred settle.

        SSE has already started, so raising ``AppError(STREAM_STOPPED)`` would
        hit "response already started". Mirror the hard-cancel path: mark the
        stream terminal and clear the live stop signal, then return from the
        generator without a provider pass.

        Mark on the request ``db`` session (not only a fresh one) so ``get_db``'s
        final commit cannot resurrect the in-memory ``active`` identity from
        ``create_stream``.
        """
        if stream_id is not None:
            with contextlib.suppress(Exception):
                await streams_repo.mark_status(
                    db,
                    stream_id=stream_id,
                    status="stopped",
                    release_active_guard=True,
                )
                await usage_repo.release_platform_budget(db, stream_id=stream_id)
                await db.commit()
            with contextlib.suppress(Exception):
                await clear_stop_async(stream_id)
        _struct_log.warning(
            "turn.stopped",
            status="stopped",
            conversation_id=str(conversation_id) if conversation_id else None,
            turn_ms=int((time.monotonic() - turn_started_at) * 1000),
            prompt_tokens=0,
            completion_tokens=0,
            reasoning_tokens=0,
            cost_usd=0.0,
            cost_confidence="estimate",
            is_byok=False,
            tier_id=binding.tier.id,
            provider_id=binding.provider_id,
            reason="approval_settle_stopped",
        )

    if (
        resume_seed is not None
        and resume_seed.pending_settle
        and resume_seed.paused_message_id is not None
        and resume_seed.settled_result is None
        and not resume_seed.is_plan
        and not resume_seed.is_clarify
    ):
        if (
            stream_id is not None and await is_stop_requested_async(stream_id)
        ) or await request.is_disconnected():
            await _release_stream_after_approval_stop()
            return
        paused_row = await db.get(Message, resume_seed.paused_message_id)
        if paused_row is None:
            raise AppError(
                ErrorEnvelope(
                    code="NOTHING_TO_RESUME",
                    severity="error",
                    title="Nothing to resume",
                    body="The paused approval message is no longer available.",
                ),
                status_code=400,
            )

        async def _settle() -> Any:
            return await claim_and_settle_approval_outcome(
                db,
                paused_message=paused_row,
                tool_call_id=resume_seed.tool_call_id,
                decision=resume_seed.decision,
                effective_input=dict(resume_seed.input or {}),
                label=resume_seed.label,
            )

        async def _watch_stop() -> str:
            while True:
                if (
                    stream_id is not None and await is_stop_requested_async(stream_id)
                ) or await request.is_disconnected():
                    return "stop"
                await asyncio.sleep(0.05)

        settle_task = asyncio.create_task(_settle())
        watch_task = asyncio.create_task(_watch_stop())
        try:
            done, _pending = await asyncio.wait(
                {settle_task, watch_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if watch_task in done and settle_task not in done:
                settle_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await settle_task
                await _release_stream_after_approval_stop()
                return
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch_task
            try:
                outcome = settle_task.result()
            except ApprovalDecisionConflict as exc:
                raise AppError(
                    ErrorEnvelope(
                        code="APPROVAL_DECISION_CONFLICT",
                        severity="error",
                        title="Approval decision conflict",
                        body=str(exc),
                    ),
                    status_code=409,
                ) from exc
            except ApprovalSettlementIncomplete as exc:
                # A live claim elsewhere still owns the side effect: 409 so the
                # client retries instead of resuming on a guessed result.
                raise AppError(
                    ErrorEnvelope(
                        code="APPROVAL_SETTLEMENT_INCOMPLETE",
                        severity="error",
                        title="Approval settlement incomplete",
                        body=str(exc),
                    ),
                    status_code=409,
                ) from exc
        except ApprovalDecisionConflict as exc:
            raise AppError(
                ErrorEnvelope(
                    code="APPROVAL_DECISION_CONFLICT",
                    severity="error",
                    title="Approval decision conflict",
                    body=str(exc),
                ),
                status_code=409,
            ) from exc
        except ApprovalSettlementIncomplete as exc:
            raise AppError(
                ErrorEnvelope(
                    code="APPROVAL_SETTLEMENT_INCOMPLETE",
                    severity="error",
                    title="Approval settlement incomplete",
                    body=str(exc),
                ),
                status_code=409,
            ) from exc
        resume_seed.settled_result = outcome.result
        resume_seed.decision = outcome.decision
        resume_seed.pending_settle = False

    async def _prior_tool_results_for_resume() -> list[ToolResult]:
        """B7: same-round tool_results already on the paused message."""
        if (
            resume_seed is None
            or resume_seed.is_plan
            or resume_seed.is_clarify
            or resume_seed.paused_message_id is None
        ):
            return []
        paused = await db.get(Message, resume_seed.paused_message_id)
        if paused is None:
            return []
        parts = paused.parts if isinstance(paused.parts, list) else []
        settled_id = None
        if resume_seed.settled_result is not None:
            settled_id = getattr(
                resume_seed.settled_result, "tool_call_id", resume_seed.tool_call_id
            )
        elif resume_seed.tool_call_id:
            settled_id = resume_seed.tool_call_id
        # Include every durable tool_result; the settled gated result is usually
        # already on the row after claim/settle. Deduplicate by call id below.
        prior = tool_results_from_message_parts(
            [p for p in parts if isinstance(p, dict)],
        )
        if (
            settled_id
            and resume_seed.settled_result is not None
            and all(r.tool_call_id != settled_id for r in prior)
        ):
            settled = resume_seed.settled_result
            prior.append(
                ToolResult(
                    tool_call_id=settled_id,
                    name=getattr(settled, "name", resume_seed.name),
                    label=resume_seed.label,
                    status=getattr(settled, "status", "succeeded"),
                    approval_state=getattr(settled, "approval_state", "approved"),
                    summary=getattr(settled, "summary", None),
                    output=getattr(settled, "output", None) or None,
                    error=getattr(settled, "error", None),
                )
            )
        return prior

    # Wrap the provider iteration in a Task so we can cancel on disconnect.
    # B7 needs an async peek at paused-message parts before the pump starts, so
    # build the iterator here (after settlement) rather than inside a sync factory.
    _cached_prior_results: list[ToolResult] | None = None

    def _settled_as_tool_result(seed: ResumeToolSeed) -> ToolResult | None:
        settled = seed.settled_result
        if settled is None:
            return None
        return ToolResult(
            tool_call_id=getattr(settled, "tool_call_id", seed.tool_call_id),
            name=getattr(settled, "name", seed.name),
            label=seed.label,
            status=getattr(settled, "status", "succeeded"),
            approval_state=getattr(settled, "approval_state", "approved"),
            summary=getattr(settled, "summary", None),
            output=getattr(settled, "output", None) or None,
            error=getattr(settled, "error", None),
        )

    async def _resolve_provider_iter() -> AsyncIterator[ProviderEvent]:
        """Build the provider / orchestrator iterator for this turn (B7).

        Single function — the former sync ``_build_provider_iter`` tools/single
        resume branches were unreachable once this async peek owned settlement.
        """
        nonlocal _cached_prior_results
        if _cached_prior_results is None:
            _cached_prior_results = await _prior_tool_results_for_resume()
        prior = _cached_prior_results

        # B5: agentic single-mode HITL resume — direct run_single with ledger seeds.
        if agentic_active and agentic_mode == "single":
            assert agentic_mode is not None
            if (
                resume_seed is not None
                and not resume_seed.is_plan
                and not resume_seed.is_clarify
                and resume_seed.agentic_continuation is None
                and (prior or resume_seed.settled_result is not None)
            ):
                initial = list(prior)
                if not initial:
                    settled_tr = _settled_as_tool_result(resume_seed)
                    if settled_tr is not None:
                        initial = [settled_tr]
                return run_single(
                    make_stream_for=_agentic_make_stream,
                    settings=handler_settings,
                    user_text=(
                        resume_seed.resume_user_text
                        if resume_seed.resume_user_text
                        else turn_user_text
                    ),
                    cost_for_usage=_cost_for_usage,
                    budget_headroom_usd=budget_headroom_usd,
                    server_approved_call_ids=set(),
                    initial_tool_results=initial or None,
                    prior_run_cost_usd=resume_seed.prior_run_cost_usd,
                    prior_run_usage=resume_seed.prior_run_usage,
                )

        # Non-agentic tools resume (settled result + same-round priors).
        if tools_active and not agentic_active:
            approved_ids: set[str] | None = None
            initial_results: list[ToolResult] | None = None
            if (
                resume_seed is not None
                and not resume_seed.is_plan
                and not resume_seed.is_clarify
                and resume_seed.settled_result is not None
            ):
                initial_results = list(prior) if prior else None
                if not initial_results:
                    settled_tr = _settled_as_tool_result(resume_seed)
                    if settled_tr is not None:
                        initial_results = [settled_tr]
                approved_ids = set()
            return run_agent_loop(
                make_stream=_build_raw_stream,
                settings=handler_settings,
                server_approved_call_ids=approved_ids,
                initial_tool_results=initial_results,
            )

        if agentic_active:
            assert agentic_mode is not None
            orch_user_text = turn_user_text
            orch_continuation = None
            orch_resume_result: ToolResult | None = None
            orch_approved_ids: set[str] | None = None
            prior_planner_cost = 0.0
            prior_planner_usage: UsageUpdate | None = None
            prior_run_cost = 0.0
            prior_run_usage: UsageUpdate | None = None
            if resume_seed is not None:
                prior_planner_cost = resume_seed.prior_planner_cost_usd
                prior_planner_usage = resume_seed.prior_planner_usage
                prior_run_cost = resume_seed.prior_run_cost_usd
                prior_run_usage = resume_seed.prior_run_usage
            if resume_seed is not None and resume_seed.agentic_continuation is not None:
                orch_continuation = resume_seed.agentic_continuation
                if resume_seed.resume_user_text:
                    orch_user_text = resume_seed.resume_user_text
                orch_resume_result = _settled_as_tool_result(resume_seed)
                orch_approved_ids = set()
            return run_orchestrator(
                make_stream_for=_agentic_make_stream,
                verifier_make_stream_for=_agentic_fresh_make_stream,
                settings=handler_settings,
                mode=agentic_mode,
                user_text=orch_user_text,
                cost_for_usage=_cost_for_usage,
                verifier_cost_for_usage=_verifier_cost_for_usage,
                estimate_cost=_estimate_run_cost,
                budget_headroom_usd=budget_headroom_usd,
                plan_approved=plan_approved,
                approved_plan=approved_plan,
                clarify_answered=clarify_answered,
                clarify_answers=clarify_answers,
                clarify_records=clarify_records,
                agentic_continuation=orch_continuation,
                resume_tool_result=orch_resume_result,
                server_approved_call_ids=orch_approved_ids,
                fallback_make_stream_for=(
                    _agentic_fallback_make_stream if fallback_binding is not None else None
                ),
                fallback_cost_for_usage=(
                    _fallback_cost_for_usage if fallback_binding is not None else None
                ),
                fallback_provider_id=(
                    (fallback_provider_id or fallback_binding.provider_id)
                    if fallback_binding is not None
                    else None
                ),
                fallback_model_id=(
                    fallback_binding.model_id if fallback_binding is not None else None
                ),
                fallback_display_label=(
                    (fallback_binding.model_label or fallback_binding.model_id)
                    if fallback_binding is not None
                    else None
                ),
                is_retryable=_is_retryable,
                prior_planner_cost_usd=prior_planner_cost,
                prior_planner_usage=prior_planner_usage,
                prior_run_cost_usd=prior_run_cost,
                prior_run_usage=prior_run_usage,
            )

        # Plain chat (non-tools, non-agentic). Wrap the raw stream in the
        # empty-reply retry loop when the kill-switch is on; when off, pass the
        # raw stream straight through so behavior is byte-for-byte identical to a
        # pre-retry build. The wrapper folds usage across attempts and emits no
        # static text — the handler injector stays the last resort.
        if handler_settings.empty_reply_retry_enabled:
            return run_chat_with_empty_retry(_build_raw_stream, handler_settings)
        return _build_raw_stream([])

    provider_iter = await _resolve_provider_iter()

    queue: asyncio.Queue[ProviderEvent | _PumpError | None] = asyncio.Queue(
        maxsize=_PROVIDER_QUEUE_MAXSIZE
    )

    async def _pump(iterator: AsyncIterator[ProviderEvent]) -> None:
        """Drain the provider iterator into the queue.

        A provider exception is forwarded to the consumer as a `_PumpError`
        sentinel so the consumer can re-raise it (→ `error` frame, no
        persistence). `CancelledError` (disconnect/cleanup cancel) is NOT
        forwarded — it just ends the pump. The terminal `None` always closes
        the queue so the consumer never blocks.

        The queue is bounded (B23); ``await put`` applies backpressure. The
        terminal sentinel is cancellation-safe: if the consumer is gone and the
        queue is full we drop oldest events until ``None`` fits.
        """
        try:
            async for ev in iterator:
                await queue.put(ev)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await queue.put(_PumpError(exc))
        finally:
            # AR-003: on natural completion await the sentinel so we never drop
            # valid events just to make room. Drop-oldest only if we are being
            # cancelled and must still unblock the consumer.
            try:
                await queue.put(None)
            except asyncio.CancelledError:
                while True:
                    try:
                        queue.put_nowait(None)
                        break
                    except asyncio.QueueFull:
                        with contextlib.suppress(asyncio.QueueEmpty):
                            queue.get_nowait()

    pump_task = asyncio.create_task(_pump(provider_iter))

    last_stream_heartbeat_at = time.monotonic()

    async def _maybe_heartbeat_stream() -> None:
        """B10: keep ``stream.updated_at`` fresh so the reaper spares live runs."""
        nonlocal last_stream_heartbeat_at
        if stream_id is None:
            return
        now = time.monotonic()
        if now - last_stream_heartbeat_at < _STREAM_HEARTBEAT_INTERVAL_S:
            return
        last_stream_heartbeat_at = now
        try:
            factory = get_session_factory()
            async with factory() as hb_db:
                await streams_repo.heartbeat(hb_db, stream_id=stream_id)
                await hb_db.commit()
        except Exception as hb_exc:  # pragma: no cover - defensive
            log.warning("stream.heartbeat.failed", exc_info=hb_exc)

    async def _release_budget_reservation(session: AsyncSession | None = None) -> None:
        """B9: drop the platform headroom hold for this stream (idempotent)."""
        if stream_id is None or user_id is None:
            return
        try:
            if session is not None:
                await usage_repo.release_platform_budget(session, stream_id=stream_id)
                return
            factory = get_session_factory()
            async with factory() as rel_db:
                await usage_repo.release_platform_budget(rel_db, stream_id=stream_id)
                await rel_db.commit()
        except Exception as rel_exc:  # pragma: no cover - defensive
            log.warning("budget.reservation_release.failed", exc_info=rel_exc)

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

    def _agentic_main_answer_ids() -> list[str]:
        """Subagent ids whose text lands in the main bubble (mirror FE).

        Mirrors `isMainAnswerSubagent` (`web/src/lib/agentic-layout.ts`): id in
        {primary, aggregator} OR role in {primary, aggregator}. Preferring the
        accumulators' own role metadata keeps the injected fallback
        main-answer-classified even under custom-id tagging. Ordered
        aggregator-first (the synthesized final bubble), then primary.
        """

        def _kind(subagent_id: str, acc: _SubagentAccumulator) -> int:
            return 0 if subagent_id == "aggregator" or acc.role == "aggregator" else 1

        main = [
            (subagent_id, acc)
            for subagent_id, acc in agentic_subagents.items()
            if subagent_id in ("primary", "aggregator")
            or acc.role in ("primary", "aggregator")
        ]
        main.sort(key=lambda pair: (_kind(*pair), pair[0]))
        return [subagent_id for subagent_id, _ in main]

    def _resolved_main_answer_text() -> str:
        """Main answer text for the done-path empty-reply guard.

        Emptiness is decided by the shared markup-aware `main_answer_is_empty`
        so leaked tool-call markup (e.g. the unsanitized Anthropic path) is
        treated as no answer — matching what the FE renders.
        """
        if agentic_active:
            for subagent_id in _agentic_main_answer_ids():
                text = "".join(agentic_subagents[subagent_id].answer)
                if not main_answer_is_empty(text):
                    return text.strip()
            return ""
        text = "".join(answer_buf)
        return "" if main_answer_is_empty(text) else text.strip()

    def _inject_empty_reply_fallback_if_needed() -> tuple[bool, str | None]:
        """Inject fallback main text when a done turn would persist blank.

        Returns `(injected, subagent_id)` where `subagent_id` tags the live
        `answer_delta` for agentic turns and is None on non-agentic turns.

        REPLACES rather than appends: the inject only runs when
        `_resolved_main_answer_text()` is already empty, i.e. the buffer strips
        to nothing (whitespace or leaked tool-call markup). Appending would
        leave `RAW_MARKUP + EMPTY_REPLY_FALLBACK` in the persisted text, and the
        FE `stripToolMarkup` truncates from the first marker (index 0) — wiping
        the fallback too. Clearing first guarantees the persisted main text is
        the fallback alone, so it survives the FE strip on reload / share.
        """
        if _resolved_main_answer_text():
            return False, None
        target_subagent: str | None = None
        if agentic_active:
            main_ids = _agentic_main_answer_ids()
            if main_ids:
                target_subagent = main_ids[0]
        if target_subagent is not None:
            acc = agentic_subagents[target_subagent]
            acc.answer.clear()
            acc.answer.append(EMPTY_REPLY_FALLBACK)
        else:
            answer_buf.clear()
            answer_buf.append(EMPTY_REPLY_FALLBACK)
        return True, target_subagent

    def _agentic_sum_cost_usd() -> float:
        """Monetary run total = sum of per-subagent receipts (BE-022 / BE-028).

        Prefer each accumulator's ``cost_usd`` from ``SubagentDone``. For an
        in-flight subagent that reported usage but not yet Done (stop drain),
        price the latest usage against the binding that served it.
        """
        total = 0.0
        for acc in agentic_subagents.values():
            if acc.cost_usd is not None:
                total += acc.cost_usd
                continue
            has_tokens = bool(
                acc.usage.input_tokens
                or acc.usage.output_tokens
                or acc.usage.reasoning_tokens
                or acc.usage.cached_input_tokens
            )
            if not has_tokens:
                continue
            if acc.substitution is not None and fallback_binding is not None:
                total += _fallback_cost_for_usage(acc.usage)
            else:
                total += _cost_for_usage(acc.usage)
        return total

    def _billable_cost_delta(logical_cost: float) -> float:
        """AR-002: charge only spend not already billed on a prior pause turn.

        Orchestrator SubagentDone receipts are cumulative (pre-pause + new) for
        cap/UI honesty. The usage rollup must not re-increment pre-pause dollars
        that the pause terminal already wrote via ``increment_for_period``.
        """
        if resume_seed is None or not agentic_active:
            return float(logical_cost)
        already = float(resume_seed.prior_run_cost_usd or 0.0)
        cont = resume_seed.agentic_continuation
        if cont is not None:
            already += float(getattr(cont, "paused_worker_cost_usd", 0.0) or 0.0)
        return max(0.0, float(logical_cost) - already)

    def _build_parts() -> list[dict[str, Any]]:
        """Assemble the persisted assistant parts in canonical order.

        Order for a web-search turn: [reasoning?] [tool transcript*]
        [status(done)] [text] [sources]. The status part is appended only if a
        `StatusUpdate` was seen (recording the FINAL line — `state="done"` for
        a completed search). The sources part is appended whenever web search
        was EFFECTIVE for the turn (`web_search`) — carrying the resolved items
        plus `requested=True` — so the grounded list AND the ungrounded
        (`items=[]`, `requested=True`) state both persist. On a non-web-search
        turn none of those enrichment parts are present, so the part SEQUENCE is
        exactly [reasoning?] [text] as before — the regression-critical no-op
        invariant is the sequence, not byte-identical part payloads. FL-37 added
        `durationSec` to the reasoning part, which is purely additive and is
        omitted entirely when the wall-clock was never measured
        (`model_dump(exclude_none=True)`).
        Shared by the terminal-success and stop-path persist sites so they can
        never drift.

        Agentic turns delegate to `_build_agentic_parts` (subagent-grouped); the
        untagged single-stream layout below preserves that sequence invariant
        when NOT agentic, preserving the flag-off behaviour.
        """
        if agentic_active:
            return _build_agentic_parts()
        parts: list[dict[str, Any]] = []
        if reasoning_buf:
            # FL-37: carry the measured wall-clock so the reloaded panel keeps
            # the "Thought for Ns" line (omitted when it was never measured).
            parts.append(
                ReasoningPart(
                    text="".join(reasoning_buf),
                    duration_sec=reasoning_duration_sec,
                ).model_dump(by_alias=True, exclude_none=True)
            )
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
            subagent_id=ev.subagent_id,
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
            subagent_id=ev.subagent_id,
        )

    def _build_agentic_parts() -> list[dict[str, Any]]:
        """Assemble persisted parts for an agentic turn, grouped by subagent (T3).

        For each subagent in first-seen order: a `subagent` marker part (carrying
        its role + per-subagent cost + outcome), then its reasoning (if any), its
        tool transcript, status/sources (FE-001), and its answer text — every
        part tagged with `subagentId`. Optionally appends an
        `agentic_run_summary` when the run was partial (FE-015).
        """
        parts: list[dict[str, Any]] = []
        for subagent_id in agentic_order:
            acc = agentic_subagents[subagent_id]
            part_attribution: ModelAttribution | None = None
            if acc.usage.input_tokens or acc.usage.output_tokens or acc.cost_usd:
                # Price/attribute on the binding that actually served (FE-009).
                attr_binding = binding
                if (
                    acc.substitution is not None
                    and fallback_binding is not None
                ):
                    attr_binding = fallback_binding
                # Verifier is fresh-context (no attachments); never inherit turn
                # image pricing. Every other phase does send them, so it is
                # charged for them. Prefer SubagentDone.cost_usd when present.
                attr_image_count = _phase_image_count(subagent_id, acc.role)
                breakdown = compute_cost_breakdown(
                    usage=acc.usage,
                    binding=attr_binding,
                    image_count=attr_image_count,
                )
                if acc.role == "verifier" and acc.cost_usd is not None:
                    breakdown = breakdown.model_copy(
                        update={
                            "subtotal_usd": float(acc.cost_usd),
                            "session_surcharge_usd": 0.0,
                        }
                    )
                part_attribution = build_attribution(
                    requested_tier_id=requested_tier_id,
                    binding=attr_binding,
                    breakdown=breakdown,
                    cost_confidence="exact",
                    is_byok=is_byok_turn,
                    substitution=acc.substitution,
                    substituted_provider=acc.substituted_provider,
                    substituted_model=acc.substituted_model,
                    substituted_display_label=acc.substituted_display_label,
                )
            parts.append(
                SubagentPart(
                    subagent_id=subagent_id,
                    label=acc.label,
                    role=acc.role,
                    cost_usd=acc.cost_usd,
                    attribution=part_attribution,
                    outcome=acc.outcome,
                ).model_dump(by_alias=True, exclude_none=True)
            )
            if acc.reasoning:
                parts.append(
                    ReasoningPart(
                        text="".join(acc.reasoning),
                        duration_sec=acc.reasoning_duration_sec,
                        subagent_id=subagent_id,
                    ).model_dump(by_alias=True, exclude_none=True)
                )
            parts.extend(acc.tool_parts)
            if acc.latest_status is not None:
                status_label, _status_state = acc.latest_status
                parts.append(
                    StatusPart(
                        label=status_label,
                        state="done",
                        subagent_id=subagent_id,
                    ).model_dump(by_alias=True, exclude_none=True)
                )
            if acc.saw_sources or (web_search and acc.search_items):
                parts.append(
                    SourcesPart(
                        items=list(acc.search_items),
                        requested=web_search or acc.saw_sources,
                        subagent_id=subagent_id,
                    ).model_dump(by_alias=True, exclude_none=True)
                )
            parts.append(
                TextPart(
                    text="".join(acc.answer), subagent_id=subagent_id
                ).model_dump(by_alias=True, exclude_none=True)
            )
        if agentic_run_summary is not None:
            parts.append(
                agentic_run_summary.model_dump(by_alias=True, exclude_none=True)
            )
        return parts

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
        parts = sanitize_message_parts_for_api(_build_parts())
        # Stop-path uses a fresh session (passed via `session=`); terminal-success
        # reuses the request-scoped `db`. Asymmetry: at disconnect the request
        # lifecycle is winding down and the route's get_db cleanup may
        # double-commit, so we decouple by opening a new session for stopped.
        target_session = session if session is not None else db
        server_state: dict[str, Any] | None = None
        if pending_server_continuations:
            server_state = {}
            for call_id, blob in pending_server_continuations.items():
                server_state = put_continuation_in_server_state(
                    server_state, call_id, blob
                )
        # B4/B5: ledger seeds beside continuations (sanitize strips tool-input).
        if (
            pending_planner_cost_usd > 0.0
            or pending_planner_usage is not None
            or pending_prior_run_cost_usd > 0.0
            or pending_prior_run_usage is not None
            or pending_orchestration_mode is not None
        ):
            server_state = put_run_ledger_in_server_state(
                server_state,
                planner_cost_usd=pending_planner_cost_usd or None,
                planner_usage=pending_planner_usage,
                prior_run_cost_usd=pending_prior_run_cost_usd or None,
                prior_run_usage=pending_prior_run_usage,
                orchestration_mode=pending_orchestration_mode,
            )
        row = await messages_repo.create_assistant_message(
            db=target_session,
            conversation_id=conversation_id,
            parts=parts,
            status=status,
            attribution=attribution.model_dump(by_alias=True, exclude_none=True),
            responds_to_message_id=user_message_id,
            cost_usd=cost_usd,
            server_state=server_state,
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

        Used to drain any remaining events after cancelling the pump on
        disconnect/stop, so persisted parts + usage reflect work already queued
        (BE-027). Agentic drains use the same subagent-aware fold as the live
        path so queued partials are not dropped into flat buffers.
        """
        nonlocal final_usage, first_answer_ms, sub_code, sub_provider, sub_model, sub_label
        nonlocal latest_status, search_items, saw_sources_event, agentic_run_summary

        if isinstance(ev, ReasoningDone):
            # FL-37: close the reasoning clock on the drain path too, for both
            # the tagged and untagged scope.
            _close_reasoning_clock(ev.subagent_id)
            return

        if agentic_active:
            if isinstance(ev, SubagentStarted):
                if ev.subagent_id not in agentic_subagents:
                    agentic_subagents[ev.subagent_id] = _SubagentAccumulator(
                        label=ev.label or ev.subagent_id,
                        role=ev.role or "subagent",
                    )
                    agentic_order.append(ev.subagent_id)
                return
            if isinstance(ev, SubagentDone):
                done_acc = agentic_subagents.get(ev.subagent_id)
                if done_acc is None:
                    done_acc = _SubagentAccumulator(
                        label=ev.label or ev.subagent_id,
                        role=ev.role or "subagent",
                    )
                    agentic_subagents[ev.subagent_id] = done_acc
                    agentic_order.append(ev.subagent_id)
                done_acc.cost_usd = ev.cost_usd
                done_acc.usage = ev.usage
                done_acc.outcome = ev.outcome
                done_acc.terminal = True
                done_acc.substitution = ev.substitution
                done_acc.substituted_provider = ev.substituted_provider
                done_acc.substituted_model = ev.substituted_model
                done_acc.substituted_display_label = ev.substituted_display_label
                return
            if isinstance(ev, RunCost):
                # FL-33-a: drain twin of the live gate — shared builder.
                agentic_run_summary = build_agentic_run_summary_part(ev)
                return
            sid = getattr(ev, "subagent_id", None)
            if isinstance(ev, ReasoningDelta) and sid is not None:
                _open_reasoning_clock(sid)
                _sub(sid).reasoning.append(ev.text)
                return
            if isinstance(ev, AnswerDelta) and sid is not None:
                _close_reasoning_clock(sid)
                if first_answer_ms is None:
                    first_answer_ms = int((time.monotonic() - turn_started_at) * 1000)
                _sub(sid).answer.append(ev.text)
                return
            if isinstance(ev, StatusUpdate) and sid is not None:
                _sub(sid).latest_status = (ev.label, ev.state)
                return
            if isinstance(ev, Sources) and sid is not None:
                # FL-35: drain twin — fold the turn-level flag identically.
                saw_sources_event = True
                acc = _sub(sid)
                acc.search_items = list(ev.items)
                acc.saw_sources = True
                return
            if isinstance(ev, ToolCall) and sid is not None:
                _sub(sid).tool_parts.append(
                    _tool_call_part(ev).model_dump(by_alias=True, exclude_none=True)
                )
                return
            if isinstance(ev, ToolResult) and sid is not None:
                target = _sub(sid).tool_parts
                for part in target:
                    if part.get("type") == "tool_call" and part.get("id") == ev.tool_call_id:
                        part["status"] = ev.status
                        break
                target.append(
                    _tool_result_part(ev).model_dump(by_alias=True, exclude_none=True)
                )
                return
            if isinstance(ev, UsageUpdate):
                if sid is not None:
                    _sub(sid).usage = ev
                else:
                    final_usage = ev
                return
            if isinstance(ev, Complete):
                if sid is not None:
                    _sub(sid).usage = ev.usage
                else:
                    final_usage = ev.usage
                    sub_code, sub_provider, sub_model, sub_label = _fold_complete_substitution(
                        ev, (sub_code, sub_provider, sub_model, sub_label)
                    )
                return
            # Untagged agentic content (rare): fall through to flat buffers.

        if isinstance(ev, ReasoningDelta):
            _open_reasoning_clock(None)
            reasoning_buf.append(ev.text)
        elif isinstance(ev, AnswerDelta):
            _close_reasoning_clock(None)
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
            for part in tool_parts:
                if part.get("type") == "tool_call" and part.get("id") == ev.tool_call_id:
                    part["status"] = ev.status
                    break
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
    if resume_seed is not None and not resume_seed.is_plan and not resume_seed.is_clarify:
        # BE-007: prefer the route's settled result (already claimed/executed).
        if resume_seed.settled_result is not None:
            settled = resume_seed.settled_result
            seeded_result = ToolResult(
                tool_call_id=getattr(settled, "tool_call_id", resume_seed.tool_call_id),
                name=getattr(settled, "name", resume_seed.name),
                label=resume_seed.label,
                status=getattr(settled, "status", "succeeded"),
                approval_state=getattr(settled, "approval_state", "approved"),
                summary=getattr(settled, "summary", None),
                output=getattr(settled, "output", None) or None,
                error=getattr(settled, "error", None),
            )
        elif resume_seed.decision == "approve":
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
                # Pump cancel acloses the orchestrator before in-flight workers'
                # SubagentDone(stopped) can be yielded onto this queue. Mark any
                # accumulator that never received Done as stopped so persist does
                # not default them to succeeded.
                if agentic_active:
                    mark_unfinished_subagents_stopped(agentic_subagents)
                # Flush accumulators, persist with status=stopped + estimate.
                # Agentic: sum completed/partial subagent receipts (BE-022 /
                # BE-028) rather than repricing an arbitrary last UsageUpdate.
                if agentic_active and agentic_subagents:
                    turn_cost = _agentic_sum_cost_usd()
                    breakdown = compute_cost_breakdown(
                        usage=final_usage,
                        binding=binding,
                        image_count=image_attachment_count,
                    )
                    breakdown = breakdown.model_copy(
                        update={"subtotal_usd": turn_cost, "session_surcharge_usd": 0.0}
                    )
                else:
                    breakdown = compute_cost_breakdown(
                        usage=final_usage,
                        binding=binding,
                        image_count=image_attachment_count,
                    )
                    # Per-turn cost: matches what build_attribution exposes as
                    # `attribution.costUsd` (pricing.py) so the ledger and the
                    # wire stay consistent. FL-34-b: `subtotal_usd` is the total;
                    # re-adding the surcharge charged it twice.
                    turn_cost = breakdown.subtotal_usd
                billable_cost = _billable_cost_delta(turn_cost)
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
                        cost_usd=billable_cost,
                    )
                    # Stopped turn still cost partial tokens -- bump the meter.
                    # `is_temporary` already gates persistence; only increment
                    # if we actually have a real user / conversation.
                    if not is_temporary and conversation_id is not None and user_id is not None:
                        await usage_repo.increment_for_period(
                            fresh_db,
                            user_id=user_id,
                            cost_usd_delta=billable_cost,
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
                                cost_usd=billable_cost,
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
                await _maybe_heartbeat_stream()
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
                    provider_iter = await _resolve_provider_iter()
                    pump_task = asyncio.create_task(_pump(provider_iter))
                    continue
                raise ev.exc

            if isinstance(ev, ReasoningDelta):
                _open_reasoning_clock(ev.subagent_id)
                if agentic_active and ev.subagent_id is not None:
                    _sub(ev.subagent_id).reasoning.append(ev.text)
                else:
                    reasoning_buf.append(ev.text)
                yield encode_reasoning_delta(
                    ReasoningDeltaEvent(text=ev.text, subagent_id=ev.subagent_id)
                )
            elif isinstance(ev, ReasoningDone):
                _close_reasoning_clock(ev.subagent_id)
                # Agentic turns interleave multiple subagents, each with its own
                # reasoning block, so the single-shot global gate doesn't apply —
                # relay every `reasoning_done` (tagged with subagent_id when set).
                # The non-agentic path keeps the exactly-one invariant.
                if agentic_active:
                    yield encode_reasoning_done(
                        ReasoningDoneEvent(subagent_id=ev.subagent_id)
                    )
                elif not emitted_reasoning_done:
                    yield encode_reasoning_done(
                        ReasoningDoneEvent(subagent_id=ev.subagent_id)
                    )
                    emitted_reasoning_done = True
            elif isinstance(ev, StatusUpdate):
                # Web-search status line (reuses the existing `status` SSE
                # event). Emit live and remember the latest (label, state) so
                # the persisted `status` part records the final, `done` line.
                # Agentic: stash per-subagent when tagged (FE-001).
                if agentic_active and ev.subagent_id is not None:
                    _sub(ev.subagent_id).latest_status = (ev.label, ev.state)
                else:
                    latest_status = (ev.label, ev.state)
                yield encode_status(
                    StatusEvent(label=ev.label, state=ev.state, subagent_id=ev.subagent_id)
                )
            elif isinstance(ev, Sources):
                # Resolved citation list. Emit the `sources` SSE event and stash
                # the items for the persisted `sources` part (appended after the
                # text part at the persist sites). `requested` mirrors whether
                # web search was effective for the turn (it is, here) so the FE
                # can tell grounded from ungrounded on the live stream.
                # FL-35: the turn is grounded whoever produced the sources. The
                # flag used to be set only in the untagged arm, so a fully
                # subagent-tagged agentic turn still emitted the final
                # "ungrounded" `sources` frame (empty items, `requested=True`)
                # below — a wire-contract violation on a cited turn.
                saw_sources_event = True
                if agentic_active and ev.subagent_id is not None:
                    acc = _sub(ev.subagent_id)
                    acc.search_items = list(ev.items)
                    acc.saw_sources = True
                else:
                    search_items = list(ev.items)
                yield encode_sources(
                    SourcesEvent(
                        items=list(ev.items),
                        requested=web_search,
                        subagent_id=ev.subagent_id,
                    )
                )
            elif isinstance(ev, ToolCall):
                call_part = _tool_call_part(ev)
                # B4: harvest planner spend from reserved tool-input before
                # sanitize-on-persist strips RESERVED_CONTROL_KEYS from parts.
                raw_input = ev.input if isinstance(ev.input, dict) else None
                if raw_input is not None:
                    stamped_cost = raw_input.get("plannerCostUsd")
                    if stamped_cost is None:
                        stamped_cost = raw_input.get("planner_cost_usd")
                    if stamped_cost is not None:
                        try:
                            cost_val = float(stamped_cost)
                        except (TypeError, ValueError):
                            cost_val = 0.0
                        if cost_val > pending_planner_cost_usd:
                            pending_planner_cost_usd = cost_val
                    stamped_usage = raw_input.get("plannerUsage")
                    if stamped_usage is None:
                        stamped_usage = raw_input.get("planner_usage")
                    if isinstance(stamped_usage, dict):
                        pending_planner_usage = usage_from_wire(stamped_usage)
                target_tool_parts = (
                    _sub(ev.subagent_id).tool_parts
                    if agentic_active and ev.subagent_id is not None
                    else tool_parts
                )
                target_tool_parts.append(call_part.model_dump(by_alias=True, exclude_none=True))
                yield encode_tool_call(
                    ToolCallEvent.model_validate(
                        call_part.model_dump(by_alias=True, exclude_none=True)
                    )
                )
            elif isinstance(ev, ToolResult):
                result_part = _tool_result_part(ev)
                target_tool_parts = (
                    _sub(ev.subagent_id).tool_parts
                    if agentic_active and ev.subagent_id is not None
                    else tool_parts
                )
                for part in target_tool_parts:
                    if part.get("type") == "tool_call" and part.get("id") == ev.tool_call_id:
                        # Keep tool_call approvalState in sync with the result
                        # (H-003: sibling cancels must flip pending → rejected,
                        # not leave pending+cancelled).
                        part["status"] = ev.status
                        if ev.approval_state is not None:
                            part["approvalState"] = ev.approval_state
                        break
                target_tool_parts.append(
                    result_part.model_dump(by_alias=True, exclude_none=True)
                )
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
                # H-012: store continuation in server_state (not tool input).
                if ev.continuation is not None:
                    # H-002 / AR-006: pin *served* route identity onto the durable
                    # checkpoint (not just the requested tier). Fallback workers
                    # pin the fallback binding so resume cannot silently switch.
                    #
                    # FL-32: these are truthiness checks, not `setdefault`.
                    # `serialize_continuation` emits `orchestrationMode` /
                    # `tierId` / `providerId` / `modelId` unconditionally as
                    # `None`, so the key is always present and `setdefault` never
                    # fired — the whole AR-006 pin (and its three route guards)
                    # was inert.
                    cont_blob = dict(ev.continuation)
                    if agentic_mode is not None and not cont_blob.get("orchestrationMode"):
                        cont_blob["orchestrationMode"] = agentic_mode
                    used_fb = bool(
                        cont_blob.get("pausedWorkerUsedFallback")
                        or cont_blob.get("paused_worker_used_fallback")
                    )
                    if used_fb and fallback_binding is not None:
                        cont_blob["tierId"] = fallback_binding.tier.id
                        cont_blob["providerId"] = (
                            fallback_provider_id or fallback_binding.provider_id
                        )
                        cont_blob["modelId"] = fallback_binding.model_id
                        # FL-30: a live pause must stay non-terminal (B15), so it
                        # never gets a `SubagentDone` to carry the served route.
                        # Stamp the substitution onto the accumulator instead —
                        # `_agentic_sum_cost_usd` then prices this worker with the
                        # fallback pricer (matching the orchestrator's
                        # `pausedWorkerCostUsd`, so nothing is left unbilled) and
                        # `_build_agentic_parts` attributes it to the model that
                        # actually served.
                        if agentic_active and ev.subagent_id is not None:
                            paused_acc = _sub(ev.subagent_id)
                            paused_acc.substitution = (
                                fallback_substitution or "provider_fallback"
                            )
                            paused_acc.substituted_provider = (
                                fallback_provider_id or fallback_binding.provider_id
                            )
                            paused_acc.substituted_model = fallback_binding.model_id
                            paused_acc.substituted_display_label = (
                                fallback_binding.model_label
                                or fallback_binding.model_id
                            )
                    else:
                        if not cont_blob.get("tierId"):
                            cont_blob["tierId"] = binding.tier.id
                        if not cont_blob.get("providerId"):
                            cont_blob["providerId"] = provider_id or binding.provider_id
                        if not cont_blob.get("modelId"):
                            cont_blob["modelId"] = binding.model_id
                    pending_server_continuations[ev.tool_call_id] = cont_blob
                    # Strip any legacy embedding from in-memory tool parts.
                    target_parts = (
                        _sub(ev.subagent_id).tool_parts
                        if agentic_active and ev.subagent_id is not None
                        else tool_parts
                    )
                    for part in target_parts:
                        if (
                            part.get("type") == "tool_call"
                            and part.get("id") == ev.tool_call_id
                        ):
                            inp = dict(part.get("input") or {})
                            inp.pop(CONTINUATION_INPUT_KEY, None)
                            part["input"] = strip_reserved_keys(inp)
                            break
                paused = True
                paused_tool_call_id = ev.tool_call_id
                break
            elif isinstance(ev, AnswerDelta):
                # Invariant: emit ReasoningDone before the first AnswerDelta,
                # if any reasoning_delta has been seen but done hasn't fired.
                # (Skipped for agentic turns — each subagent emits its own
                # `reasoning_done`.)
                if not agentic_active and reasoning_buf and not emitted_reasoning_done:
                    yield encode_reasoning_done(ReasoningDoneEvent())
                    emitted_reasoning_done = True
                # FL-37: a provider that jumps straight to prose without a
                # ReasoningDone still ends the reasoning block here.
                _close_reasoning_clock(ev.subagent_id)
                if first_answer_ms is None:
                    first_answer_ms = int((time.monotonic() - turn_started_at) * 1000)
                if agentic_active and ev.subagent_id is not None:
                    _sub(ev.subagent_id).answer.append(ev.text)
                else:
                    answer_buf.append(ev.text)
                yield encode_answer_delta(
                    AnswerDeltaEvent(text=ev.text, subagent_id=ev.subagent_id)
                )
            elif isinstance(ev, SubagentStarted):
                # Open a transcript section for this subagent. Recorded in
                # first-seen order so the persisted parts group deterministically.
                if ev.subagent_id not in agentic_subagents:
                    agentic_subagents[ev.subagent_id] = _SubagentAccumulator(
                        label=ev.label, role=ev.role
                    )
                    agentic_order.append(ev.subagent_id)
                yield encode_subagent_started(
                    SubagentStartedEvent(
                        subagent_id=ev.subagent_id, label=ev.label, role=ev.role
                    )
                )
            elif isinstance(ev, SubagentDone):
                done_acc = agentic_subagents.get(ev.subagent_id)
                done_attribution: ModelAttribution | None = None
                if done_acc is not None:
                    done_acc.cost_usd = ev.cost_usd
                    done_acc.usage = ev.usage
                    done_acc.outcome = ev.outcome
                    done_acc.terminal = True
                    done_acc.substitution = ev.substitution
                    done_acc.substituted_provider = ev.substituted_provider
                    done_acc.substituted_model = ev.substituted_model
                    done_acc.substituted_display_label = ev.substituted_display_label
                    if (
                        ev.usage.input_tokens
                        or ev.usage.output_tokens
                        or (ev.cost_usd is not None and ev.cost_usd > 0)
                    ):
                        attr_binding = binding
                        if (
                            ev.substitution is not None
                            and fallback_binding is not None
                        ):
                            attr_binding = fallback_binding
                        # Verifier is fresh-context (no attachments); never
                        # inherit turn image pricing. Every other phase does
                        # send them, so it is charged for them. Prefer
                        # authoritative SubagentDone.cost_usd when present.
                        attr_image_count = _phase_image_count(ev.subagent_id, ev.role)
                        breakdown = compute_cost_breakdown(
                            usage=ev.usage,
                            binding=attr_binding,
                            image_count=attr_image_count,
                        )
                        if ev.role == "verifier" and ev.cost_usd is not None:
                            breakdown = breakdown.model_copy(
                                update={
                                    "subtotal_usd": float(ev.cost_usd),
                                    "session_surcharge_usd": 0.0,
                                }
                            )
                        done_attribution = build_attribution(
                            requested_tier_id=requested_tier_id,
                            binding=attr_binding,
                            breakdown=breakdown,
                            cost_confidence="exact",
                            is_byok=is_byok_turn,
                            substitution=ev.substitution,
                            substituted_provider=ev.substituted_provider,
                            substituted_model=ev.substituted_model,
                            substituted_display_label=ev.substituted_display_label,
                        )
                yield encode_subagent_done(
                    SubagentDoneEvent(
                        subagent_id=ev.subagent_id,
                        label=ev.label,
                        role=ev.role,
                        cost_usd=ev.cost_usd,
                        outcome=ev.outcome,
                        attribution=done_attribution,
                        substitution=ev.substitution,
                        substituted_provider=ev.substituted_provider,
                        substituted_model=ev.substituted_model,
                        substituted_display_label=ev.substituted_display_label,
                    )
                )
            elif isinstance(ev, RunCost):
                # Running run-cost subtotal vs the configured cap (M3 scaffold).
                # AR-012: always persist a terminal receipt so reload matches live.
                # FL-33-a: a plan / progress pause receipt persists too, with the
                # confidence + phase the backend actually emitted.
                agentic_run_summary = build_agentic_run_summary_part(ev)
                yield encode_run_cost(
                    RunCostEvent(
                        subtotal_usd=ev.subtotal_usd,
                        cap_usd=ev.cap_usd,
                        confidence=ev.confidence,
                        phase=ev.phase,
                        partial=ev.partial,
                        budget_halted=ev.budget_halted,
                        failed_worker_count=ev.failed_worker_count,
                    )
                )
            elif isinstance(ev, UsageUpdate):
                if agentic_active and ev.subagent_id is not None:
                    _sub(ev.subagent_id).usage = ev
                else:
                    final_usage = ev
            elif isinstance(ev, Complete):
                empty_retry_seen = empty_retry_seen or ev.empty_retry
                empty_retry_recovered_seen = (
                    empty_retry_recovered_seen or ev.empty_retry_recovered
                )
                if agentic_active and ev.subagent_id is not None:
                    _sub(ev.subagent_id).usage = ev.usage
                else:
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
            # FL-28: record the mode this run paused in so the resume POST cannot
            # be talked into a different orchestration mode. Plan-approval,
            # clarify and single-mode pauses carry no continuation blob, so the
            # pin has to live in server_state beside the ledger seeds.
            if agentic_active and agentic_mode is not None:
                pending_orchestration_mode = agentic_mode
            if agentic_active and agentic_subagents:
                mark_unfinished_subagents_paused(agentic_subagents)
            breakdown = compute_cost_breakdown(
                usage=final_usage,
                binding=binding,
                image_count=image_attachment_count,
            )
            if agentic_active and agentic_subagents:
                turn_cost = _agentic_sum_cost_usd()
                breakdown = breakdown.model_copy(
                    update={"subtotal_usd": turn_cost, "session_surcharge_usd": 0.0}
                )
            else:
                # FL-34-b: charge the subtotal alone (surcharge is disclosure).
                turn_cost = breakdown.subtotal_usd
            # B4: if tool-input stamp was missing, fall back to planner accumulator.
            if pending_planner_cost_usd <= 0.0 and agentic_active:
                planner_acc = agentic_subagents.get("planner")
                if planner_acc is not None:
                    if planner_acc.cost_usd is not None and planner_acc.cost_usd > 0:
                        pending_planner_cost_usd = float(planner_acc.cost_usd)
                    if (
                        pending_planner_usage is None
                        and (
                            planner_acc.usage.input_tokens
                            or planner_acc.usage.output_tokens
                            or planner_acc.usage.reasoning_tokens
                            or planner_acc.usage.cached_input_tokens
                        )
                    ):
                        pending_planner_usage = planner_acc.usage
            # B5: single-mode pause ledger for resume seeding.
            # Accumulate across repeated pause cycles — a second pause must not
            # discard the prior_run_* already seeded into this resume turn.
            if agentic_active and agentic_mode == "single":
                primary_acc = agentic_subagents.get("primary")
                pause_usage = (
                    primary_acc.usage
                    if primary_acc is not None
                    and (
                        primary_acc.usage.input_tokens
                        or primary_acc.usage.output_tokens
                        or primary_acc.usage.reasoning_tokens
                        or primary_acc.usage.cached_input_tokens
                    )
                    else final_usage
                )
                prior_seed_cost = (
                    float(resume_seed.prior_run_cost_usd)
                    if resume_seed is not None
                    else 0.0
                )
                pending_prior_run_cost_usd = prior_seed_cost + float(turn_cost or 0.0)
                usage_parts: list[UsageUpdate] = []
                if resume_seed is not None and resume_seed.prior_run_usage is not None:
                    usage_parts.append(resume_seed.prior_run_usage)
                if (
                    pause_usage.input_tokens
                    or pause_usage.output_tokens
                    or pause_usage.reasoning_tokens
                    or pause_usage.cached_input_tokens
                ):
                    usage_parts.append(pause_usage)
                if usage_parts:
                    pending_prior_run_usage = UsageUpdate(
                        input_tokens=sum(u.input_tokens for u in usage_parts),
                        output_tokens=sum(u.output_tokens for u in usage_parts),
                        reasoning_tokens=sum(u.reasoning_tokens for u in usage_parts),
                        cached_input_tokens=sum(
                            u.cached_input_tokens for u in usage_parts
                        ),
                    )
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
        # wire attribution agree. Agentic heterogeneous routes (BE-022): sum
        # per-subagent monetary costs rather than repricing the summed tokens
        # once against the original binding.
        if agentic_active and agentic_subagents:
            turn_cost = _agentic_sum_cost_usd()
            # Keep breakdown for structure, but override the displayed total.
            breakdown = breakdown.model_copy(
                update={"subtotal_usd": turn_cost, "session_surcharge_usd": 0.0}
            )
        else:
            # FL-34-b: charge the subtotal alone (surcharge is disclosure).
            turn_cost = breakdown.subtotal_usd
        # AR-002: rollup/message cost charge only the unbilled delta on resume.
        billable_cost = _billable_cost_delta(turn_cost)
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
        fallback_injected, fallback_subagent_id = _inject_empty_reply_fallback_if_needed()
        if fallback_injected:
            if not agentic_active and reasoning_buf and not emitted_reasoning_done:
                yield encode_reasoning_done(ReasoningDoneEvent())
                emitted_reasoning_done = True
            if first_answer_ms is None:
                first_answer_ms = int((time.monotonic() - turn_started_at) * 1000)
            yield encode_answer_delta(
                AnswerDeltaEvent(
                    text=EMPTY_REPLY_FALLBACK,
                    subagent_id=fallback_subagent_id,
                )
            )
        resolved_answer_text = _resolved_main_answer_text()
        # Structured-output boundary validation. No-op unless a `response_format`
        # was requested; then it sets `output_format` and validates the
        # accumulated answer text (JSON parse + optional JSON Schema check),
        # surfacing `output_valid` WITHOUT failing the turn.
        _apply_structured_output(
            attribution,
            response_format=response_format,
            answer_text=resolved_answer_text,
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
                cost_usd=billable_cost,
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
                    cost_usd_delta=billable_cost,
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
                        answer_text=resolved_answer_text,
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
            empty_reply_retry=empty_retry_seen,
            empty_reply_retry_recovered=empty_retry_recovered_seen,
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
            # exception text to the client. AR-013: still capture the stack for
            # operators (structured logs / Sentry when configured).
            _struct_log.error(
                "turn.provider_unexpected",
                exc_info=exc,
                conversation_id=str(conversation_id) if conversation_id else None,
                stream_id=str(stream_id) if stream_id is not None else None,
                agentic_mode=agentic_mode,
            )
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
        await _release_budget_reservation()


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
    agentic_mode: Literal["single", "deep_research"] | None = None,
    budget_headroom_usd: float | None = None,
    requested_agentic_mode: Literal["single", "deep_research"] | None = None,
    agentic_coercion_reason: Literal["entitlement"] | None = None,
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
                agentic_mode=agentic_mode,
                budget_headroom_usd=budget_headroom_usd,
                requested_agentic_mode=requested_agentic_mode,
                agentic_coercion_reason=agentic_coercion_reason,
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

"""Conversation routes.

M0: `GET /api/conversations/:id`.
M1: `POST /api/conversations` (create), `POST /api/conversations/:id/messages`
    (the streaming endpoint).
M2: `PATCH/DELETE /api/conversations/:id`; `regenerate` and `editMessageId`
    paths in `send_message`; title autogen via fire-and-forget asyncio task.

Temporary chats are tracked in a module-level `_TEMP_IDS` dict keyed by user.
This is in-process state — multi-worker prod will need Redis or a signed-
cookie token (M2+). Documented as M1-only.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.auth.dependency import current_user
from app.config import Settings, get_settings
from app.db.models import Message, User
from app.db.repositories import analytics as analytics_repo
from app.db.repositories import api_keys as api_keys_repo
from app.db.repositories import audit_events as audit_events_repo
from app.db.repositories import billing as billing_repo
from app.db.repositories import conversations as conversations_repo
from app.db.repositories import memory_facts as memory_repo
from app.db.repositories import messages as messages_repo
from app.db.repositories import preferences as preferences_repo
from app.db.repositories import streams as streams_repo
from app.db.repositories import usage as usage_repo
from app.db.repositories.usage import _effective_quota_usd
from app.db.session import get_db
from app.errors import AppError, ErrorAction, ErrorEnvelope, not_found
from app.middleware.ratelimit import limiter
from app.providers.factory import build_provider
from app.providers.protocol import (
    AttachmentPayload,
    ResponseFormat,
)
from app.providers.protocol import (
    ChatMessage as ProviderChatMessage,
)
from app.providers.router import route_auto
from app.providers.tiers import (
    TierBinding,
    available_provider_backend_ids,
    get_binding,
    get_provider_route,
    is_known_tier,
    platform_provider_usable,
    route_adapter_available,
    tier_requires_pro,
    web_search_available_for_binding,
)
from app.safety import SafetyDecision, check_user_turn
from app.schemas.common import ModelTierId, ReasoningEffortId, SubstitutionReasonCode
from app.schemas.conversation import (
    BranchConversationRequest,
    ConversationSearchResult,
    CreateConversationRequest,
    PatchConversationRequest,
    SendMessageRequest,
    ToolApprovalDecision,
)
from app.schemas.conversation import Conversation as ConversationSchema
from app.schemas.message import AttachmentPart, ModelAttribution
from app.schemas.share import ShareLinkResponse
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
from app.streaming import replay_registry
from app.streaming.handler import (
    ResumeToolSeed,
    _derive_session_factory,
    spawn_detached_producer,
    stream_and_persist,
)
from app.streaming.replay_registry import ReplayLogBuffer, ReplayLogTruncatedError
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
from app.streaming.stop_registry import request_stop_async
from app.tools.builtin import TOOL_REGISTRY, ToolInputError, validate_tool_input
from app.uploads import extract_attachment_text, is_supported_attachment_type

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# Continuation instruction appended to the provider history when continuing a
# stopped turn. The prior (partial) assistant text is replayed as the trailing
# assistant turn, then THIS instruction is sent as the new user turn so the
# model extends its own response instead of restarting it. The fake provider
# detects this exact constant to emit a deterministic continuation (see
# app/providers/fake.py).
_CONTINUE_INSTRUCTION = (
    "Continue your previous response from exactly where it left off. "
    "Do not repeat or re-introduce anything already written."
)

# Continuation instructions sent as the new user turn when RESUMING a turn that
# paused on an approval-gated tool. They carry the human's decision so the model
# (and the deterministic fake provider) produces the post-tool answer. The
# handler emits the seeded `tool_result` BEFORE this turn streams. The phrases
# "Tool approved:" / "Tool denied:" are detected by the fake provider.
_RESUME_APPROVE_INSTRUCTION = (
    "Tool approved: the requested tool has been executed. Use its result to "
    "complete your response."
)
_RESUME_DENY_INSTRUCTION = (
    "Tool denied: the user declined the requested tool. Do not perform the "
    "action; briefly acknowledge and continue."
)


# Multi-worker note: this dict only lives in one process. Behind multiple
# uvicorn workers, a temporary chat created on worker A and posted to from
# worker B will 404. M2 may swap this for Redis or a signed-cookie token.
_TEMP_IDS: dict[UUID, set[UUID]] = defaultdict(set)


async def _enforce_retention(db: AsyncSession, user_id: UUID) -> None:
    """Apply the caller's finite retention preference before reading history."""
    prefs = await preferences_repo.get_or_default(db, user_id)
    if prefs.retention_days is None:
        return
    cutoff = datetime.now(UTC) - timedelta(days=prefs.retention_days)
    await conversations_repo.delete_older_than_for_user(
        db,
        user_id=user_id,
        cutoff=cutoff,
    )


def _eventsource_response(*args: Any, **kwargs: Any) -> EventSourceResponse:
    """Construct an EventSourceResponse with `no-store` (not `no-cache`).

    sse-starlette ships a default `Cache-Control: no-cache` header and some
    versions do not let the constructor `headers=` arg override it cleanly.
    Post-mutating `response.headers` after construction is reliable.
    """
    r = EventSourceResponse(*args, **kwargs)
    r.headers["Cache-Control"] = "no-store"
    r.headers["X-Accel-Buffering"] = "no"
    return r


def _invalid_input(code: str, body: str) -> AppError:
    return AppError(
        ErrorEnvelope(
            code=code,
            severity="error",
            title="Invalid input",
            body=body,
        ),
        status.HTTP_400_BAD_REQUEST,
    )


def _invalid_provider(provider_id: str) -> AppError:
    return _invalid_input("INVALID_PROVIDER", f"Unknown provider id {provider_id!r}.")


def _provider_unavailable(provider_id: str) -> AppError:
    return _invalid_input(
        "PROVIDER_UNAVAILABLE",
        f"Provider {provider_id!r} is not available for message routing.",
    )


def _validate_provider_id(provider_id: str | None, settings: Settings) -> None:
    if provider_id is None:
        return
    route = get_provider_route(provider_id)
    if route is None:
        raise _invalid_provider(provider_id)
    if not route_adapter_available(provider_id, settings):
        raise _provider_unavailable(provider_id)


def _resolve_binding(
    tier_id: ModelTierId,
    provider_id: str | None,
    settings: Settings,
) -> TierBinding:
    _validate_provider_id(provider_id, settings)
    binding = get_binding(
        tier_id,
        settings=settings,
        provider_id=provider_id,
    )
    if binding is not None:
        return binding
    if not is_known_tier(tier_id):
        raise _invalid_input("INVALID_TIER", f"Unknown tier id {tier_id!r}.")
    selected_provider = provider_id or get_settings().provider_backend
    raise _provider_unavailable(selected_provider)


def _selected_provider_id(provider_id: str | None, settings: Settings) -> str:
    return provider_id or settings.provider_backend


def _ensure_provider_usable(
    *,
    provider_id: str,
    settings: Settings,
    api_key: str | None,
) -> None:
    if provider_id == "fake":
        if not platform_provider_usable(provider_id, settings):
            raise _provider_unavailable(provider_id)
        return
    if api_key is not None:
        return
    if not platform_provider_usable(provider_id, settings):
        raise _provider_unavailable(provider_id)


def _map_reasoning_effort(
    effort: ReasoningEffortId | None,
    binding: TierBinding,
) -> tuple[str | None, bool | None]:
    """Map a per-turn reasoning-effort hint to provider call overrides.

    Returns `(reasoning_effort_override, thinking_override)` — each None means
    "use the binding default unchanged" at the provider call:

    - `auto` / None  -> `(binding.reasoning_effort, None)`: unchanged behavior.
    - `minimal`      -> `(None, False)`: force thinking OFF for a real latency
      win (and omit any effort level).
    - `standard`     -> `("medium", None)`.
    - `extended`     -> `("high", None)`.

    Providers that don't support effort hints ignore them, so this is always a
    safe, graceful hint — it NEVER raises for an unsupported effort.
    """
    if effort is None or effort == "auto":
        return binding.reasoning_effort, None
    if effort == "minimal":
        return None, False
    if effort == "standard":
        return "medium", None
    # "extended"
    return "high", None


async def _select_fallback_route(
    tier_id: ModelTierId,
    primary_provider_id: str,
    settings: Settings,
    *,
    user: User,
    db: AsyncSession,
    resolved_api_key: str | None,
) -> tuple[TierBinding, str, str | None] | None:
    """Pick a single alternate provider route to retry on a provider fallback.

    Policy (ALL routing decisions live here; the handler stays dumb):

    - Candidates = real adapter backends (`available_provider_backend_ids`)
      MINUS the primary, that are usable either on the platform key
      (`platform_provider_usable`) OR via a stored BYOK key for the caller, and
      whose adapter is allowed in this runtime (`route_adapter_available`).
    - Iterate a FIXED safe order (deepseek, anthropic, openai, fake) and pick the
      first candidate with a non-None `get_binding(tier_id, provider_id=cand)`.
    - Resolve that candidate's BYOK key (mirrors the primary BYOK lookup).

    Returns `(binding, provider_id, api_key)` or None when no alternate exists.

    The `fake` backend is included so the dev/test path can exercise the retry:
    when the active backend is `fake`, the fallback binding's `model_id` is
    switched to `"fake-fallback"` so the fake provider streams normally on the
    retry (it only raises pre-token on the primary `model_id`).
    """
    # Fixed safe order. `fake` last so real providers always win when present.
    preferred_order = ("deepseek", "anthropic", "openai", "fake")
    available = set(available_provider_backend_ids())
    for candidate in preferred_order:
        if candidate not in available:
            continue
        # Skip the primary route — EXCEPT the `fake` dev/test backend, which may
        # serve as its own fallback: the `model_id="fake-fallback"` swap below
        # makes it a genuinely distinct route that streams instead of re-raising.
        # Real providers never self-fall-back (a single usable provider correctly
        # yields no alternate and the error surfaces), and `fake` is gated out of
        # production entirely by `route_adapter_available`/`platform_provider_usable`,
        # so prod is unchanged — this only lights up the dev/test retry seam.
        if candidate == primary_provider_id and candidate != "fake":
            continue
        if not route_adapter_available(candidate, settings):
            continue
        # Resolve a BYOK key for the candidate (non-anonymous users only).
        candidate_key: str | None = None
        if not user.is_anonymous:
            candidate_key = await api_keys_repo.get_decrypted_for_user(
                db, user_id=user.id, provider=candidate
            )
        # Usable iff the platform can call it OR the caller has a BYOK key.
        if not (platform_provider_usable(candidate, settings) or candidate_key is not None):
            continue
        candidate_binding = get_binding(tier_id, settings=settings, provider_id=candidate)
        if candidate_binding is None:
            continue
        if candidate == "fake":
            # Distinct model id so the fake provider streams (doesn't re-raise)
            # on the retry — see providers/fake.py FORCE_FALLBACK_RETRY marker.
            from dataclasses import replace as _replace

            candidate_binding = _replace(candidate_binding, model_id="fake-fallback")
        return candidate_binding, candidate, candidate_key
    return None


def _stream_in_progress() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="STREAM_IN_PROGRESS",
            severity="error",
            title="A response is still streaming",
            body="This conversation already has a response in progress. "
            "Wait for it to finish or stop it before sending again.",
        ),
        status.HTTP_409_CONFLICT,
    )


def _duplicate_in_flight() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="DUPLICATE_IN_FLIGHT",
            severity="error",
            title="Duplicate request",
            body="A prior submission with this clientMessageId is still in flight.",
        ),
        status.HTTP_409_CONFLICT,
    )


def _stream_replay_truncated_envelope() -> ErrorEnvelope:
    return ErrorEnvelope(
        code="STREAM_REPLAY_TRUNCATED",
        severity="error",
        title="Stream replay expired",
        body=(
            "This stream's replay buffer no longer has the full event history. "
            "Start a new message to continue."
        ),
    )


def _stream_replay_truncated() -> AppError:
    return AppError(
        _stream_replay_truncated_envelope(),
        status.HTTP_410_GONE,
    )


def _stream_replay_unavailable_envelope() -> ErrorEnvelope:
    return ErrorEnvelope(
        code="STREAM_REPLAY_UNAVAILABLE",
        severity="error",
        title="Stream replay unavailable",
        body=(
            "The prior message is still in flight, but its live replay buffer "
            "is not available. Try reconnecting in a moment."
        ),
    )


def _idempotency_mismatch() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="IDEMPOTENCY_MISMATCH",
            severity="error",
            title="Conflicting duplicate request",
            body=(
                "A prior submission used this clientMessageId with different "
                "request parameters. Send a new clientMessageId for the changed request."
            ),
        ),
        status.HTTP_409_CONFLICT,
    )


def _nothing_to_continue() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="NOTHING_TO_CONTINUE",
            severity="warning",
            title="Nothing to continue",
            body="This conversation has no stopped response to continue. "
            "Send a new message or regenerate instead.",
        ),
        status.HTTP_400_BAD_REQUEST,
    )


def _nothing_to_resume() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="NOTHING_TO_RESUME",
            severity="warning",
            title="Nothing to resume",
            body="This conversation has no tool awaiting approval. "
            "Send a new message instead.",
        ),
        status.HTTP_400_BAD_REQUEST,
    )


def _attachments_unsupported() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="ATTACHMENTS_UNSUPPORTED",
            severity="warning",
            title="Attachments are not supported by this model",
            body="Choose a model tier that supports attachments, or remove the files "
            "and send the message again.",
        ),
        status.HTTP_400_BAD_REQUEST,
    )


def _vision_unsupported() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="VISION_UNSUPPORTED",
            severity="warning",
            title="This model can't read images",
            body="Switch to a vision-capable model or remove the image, then send "
            "the message again.",
        ),
        status.HTTP_400_BAD_REQUEST,
    )


def _safety_blocked(decision: SafetyDecision) -> AppError:
    return AppError(
        ErrorEnvelope(
            code="SAFETY_BLOCKED",
            severity="warning",
            title="Message blocked",
            body="The message could not be sent because it matched a configured safety rule.",
            meta={
                "reasonCode": decision.reason_code,
                "source": decision.source,
            },
        ),
        status.HTTP_400_BAD_REQUEST,
    )


async def _record_moderation_blocked(
    db: AsyncSession,
    *,
    user: User,
    decision: SafetyDecision,
    conversation_id: UUID,
) -> None:
    """Persist a `moderation.blocked` audit event for a blocked turn.

    Uses an INDEPENDENT session (mirroring the `budget.exceeded` analytics
    write) so the record survives the request rollback that the subsequent
    `_safety_blocked` AppError triggers, while staying bound to the same engine
    as `db` (so tests observe it on their per-test SQLite file). Content-free:
    only the reason code, source, and conversation id are stored.
    """
    details: dict[str, str] = {"conversationId": str(conversation_id)}
    if decision.reason_code:
        details["reasonCode"] = decision.reason_code
    if decision.source:
        details["source"] = decision.source
    async with _derive_session_factory(db)() as event_db:
        await audit_events_repo.record(
            event_db,
            user_id=user.id,
            event_type="moderation.blocked",
            details=details,
        )
        await event_db.commit()


def _request_fingerprint(
    body: SendMessageRequest,
    *,
    provider_id: str,
) -> dict[str, object]:
    """Stable replay guard for a normal user-message submission.

    Store only a digest: the message text already lives in `parts`, and raw
    attachment payload bytes must never be duplicated in an idempotency column.
    """
    payload_hashes = [_attachment_payload_sha256(attachment) for attachment in body.attachments]
    payload = {
        "tierId": body.tier_id,
        "providerId": provider_id,
        "text": body.text,
        "webSearch": bool(body.web_search),
        "regenerate": bool(body.regenerate),
        "continueTurn": bool(body.continue_turn),
        "editMessageId": body.edit_message_id,
        "attachments": [
            {
                "id": attachment.id,
                "name": attachment.name,
                "mediaType": attachment.media_type,
                "mimeType": attachment.mime_type,
                "sizeBytes": attachment.size_bytes,
            }
            for attachment in body.attachments
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        "v": 1,
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        **(
            {"attachmentPayloadSha256": payload_hashes}
            if any(payload_hash is not None for payload_hash in payload_hashes)
            else {}
        ),
    }


def _attachment_payload_sha256(attachment: AttachmentPart) -> str | None:
    encoded: str | None
    if attachment.data_url is not None:
        encoded = (
            attachment.data_url.split(",", 1)[1]
            if attachment.data_url.startswith("data:") and "," in attachment.data_url
            else attachment.data_url
        )
    else:
        encoded = attachment.content_base64
    if encoded is None:
        return None
    try:
        material = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error):
        material = encoded.encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(material).hexdigest()


def _request_fingerprints_match(
    stored: dict[str, object],
    incoming: dict[str, object],
) -> bool:
    if stored == incoming:
        return True
    if stored.get("v") != incoming.get("v") or stored.get("sha256") != incoming.get("sha256"):
        return False

    stored_hashes = stored.get("attachmentPayloadSha256")
    incoming_hashes = incoming.get("attachmentPayloadSha256")
    if not isinstance(stored_hashes, list) or not isinstance(incoming_hashes, list):
        # Metadata-only retries omit transient payloads, and legacy stored
        # fingerprints have no payload digest. The metadata digest above still
        # has to match exactly.
        return True
    if len(stored_hashes) != len(incoming_hashes):
        return False
    for stored_hash, incoming_hash in zip(stored_hashes, incoming_hashes, strict=True):
        if (
            isinstance(stored_hash, str)
            and isinstance(incoming_hash, str)
            and stored_hash != incoming_hash
        ):
            return False
    return True


async def _replay_buffer_events(
    *,
    request: Request | None,
    buffer: ReplayLogBuffer,
    expected_user_message_id: UUID | None = None,
) -> AsyncIterator[ServerSentEvent]:
    """Replay one live buffer and surface truncation as an SSE error frame."""
    try:
        subscription = await buffer.subscribe()
        first_event = True
        async for sse_event in subscription.events():
            if first_event and expected_user_message_id is not None:
                first_event = False
                if _submitted_message_id(sse_event) != expected_user_message_id:
                    yield encode_error(_stream_replay_unavailable_envelope())
                    return
            if request is not None and await request.is_disconnected():
                return
            yield sse_event
    except ReplayLogTruncatedError:
        yield encode_error(_stream_replay_truncated_envelope())


def _submitted_message_id(event: ServerSentEvent) -> UUID | None:
    if event.event != "submitted" or not isinstance(event.data, str):
        return None
    try:
        payload = json.loads(event.data)
        raw_message_id = payload.get("messageId")
        return UUID(raw_message_id) if isinstance(raw_message_id, str) else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _attachment_invalid(body: str) -> AppError:
    return _invalid_input("INVALID_ATTACHMENT", body)


def _decode_base64(value: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise _attachment_invalid("Attachment payload must be valid base64.") from exc


def _decode_attachment_payloads(
    attachments: list[AttachmentPart],
    *,
    max_count: int,
    max_bytes: int,
) -> list[AttachmentPayload]:
    """Validate request attachments and return transient provider payloads."""
    if not attachments:
        return []
    if max_count < 0 or max_bytes < 1:
        raise _attachment_invalid("Attachment limits are misconfigured.")
    if len(attachments) > max_count:
        raise _attachment_invalid(f"Attach at most {max_count} files.")

    payloads: list[AttachmentPayload] = []
    for attachment in attachments:
        if not is_supported_attachment_type(attachment.media_type, attachment.mime_type):
            raise _attachment_invalid("Attachment type is not supported.")
        if attachment.size_bytes <= 0:
            raise _attachment_invalid("Attachment payload cannot be empty.")
        if attachment.size_bytes > max_bytes:
            raise _attachment_invalid(f"Each attachment must be {max_bytes} bytes or smaller.")
        if attachment.data_url is not None and attachment.content_base64 is not None:
            raise _attachment_invalid(
                "Send either dataUrl or contentBase64 for an attachment, not both."
            )

        encoded: str
        if attachment.data_url is not None:
            if not attachment.data_url.startswith("data:") or "," not in attachment.data_url:
                raise _attachment_invalid("Attachment dataUrl must be a base64 data URL.")
            header, encoded = attachment.data_url.split(",", 1)
            metadata = header[5:].split(";")
            data_url_mime = metadata[0] if metadata else ""
            if data_url_mime != attachment.mime_type:
                raise _attachment_invalid("Attachment dataUrl MIME type must match mimeType.")
            if "base64" not in metadata[1:]:
                raise _attachment_invalid("Attachment dataUrl must be base64 encoded.")
        elif attachment.content_base64 is not None:
            encoded = attachment.content_base64
        else:
            raise _attachment_invalid("Attachment payload is required.")

        data = _decode_base64(encoded)
        if len(data) != attachment.size_bytes:
            raise _attachment_invalid("Attachment sizeBytes must match payload size.")
        if len(data) > max_bytes:
            raise _attachment_invalid(f"Each attachment must be {max_bytes} bytes or smaller.")
        extracted_text = extract_attachment_text(
            media_type=attachment.media_type,
            mime_type=attachment.mime_type,
            data=data,
        )
        if attachment.media_type == "text" and extracted_text is None:
            raise _attachment_invalid("Text attachment could not be decoded.")
        payloads.append(
            AttachmentPayload(
                id=attachment.id,
                name=attachment.name,
                media_type=attachment.media_type,
                mime_type=attachment.mime_type,
                size_bytes=attachment.size_bytes,
                data=data,
                extracted_text=extracted_text,
            )
        )
    return payloads


def _attachment_payloads_from_parts(parts: object) -> list[AttachmentPayload]:
    """Recover metadata-only provider payloads from a persisted user message."""
    if not isinstance(parts, list):
        return []
    payloads: list[AttachmentPayload] = []
    for part in parts:
        if not isinstance(part, dict) or part.get("type") != "attachment":
            continue
        raw_media_type = part.get("mediaType")
        if raw_media_type not in ("image", "pdf", "text"):
            continue
        media_type = cast(Literal["image", "pdf", "text"], raw_media_type)
        name = str(part.get("name") or "attachment")
        mime_type = str(part.get("mimeType") or "")
        size_raw = part.get("sizeBytes")
        size_bytes = int(size_raw) if isinstance(size_raw, int) else 0
        payloads.append(
            AttachmentPayload(
                id=str(part.get("id") or ""),
                name=name,
                media_type=media_type,
                mime_type=mime_type,
                size_bytes=size_bytes,
                data=None,
            )
        )
    return payloads


def _text_from_parts(parts: object) -> str:
    """Recover concatenated text parts from a persisted message payload."""
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            chunks.append(str(part.get("text", "")))
    return "".join(chunks)


def _ms_until_next_month(now: datetime | None = None) -> int:
    """Milliseconds from `now` until the next calendar-month UTC start.

    Drives `retry_after_ms` on the budget envelope: the cost ledger resets when
    the period rolls over, so the FE can surface "try again next month". Clamped
    to >= 0 defensively (clock skew should never make this negative).
    """
    ref = now if now is not None else datetime.now(UTC)
    if ref.month == 12:
        nxt = ref.replace(
            year=ref.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    else:
        nxt = ref.replace(month=ref.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return max(0, int((nxt - ref).total_seconds() * 1000))


def _budget_exceeded() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="PLATFORM_BUDGET_EXCEEDED",
            severity="warning",
            title="Usage limit reached",
            body="You've reached your usage budget for this period.",
            retry_after_ms=_ms_until_next_month(),
            actions=[ErrorAction(label="View usage", kind="open_settings")],
        ),
        status.HTTP_429_TOO_MANY_REQUESTS,
    )


def _conversation_budget_exceeded() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="CONVERSATION_BUDGET_EXCEEDED",
            severity="warning",
            title="Conversation limit reached",
            body="This conversation has reached the per-conversation spend cap "
            "you set. Raise or clear the cap in settings, or start a new chat.",
            actions=[ErrorAction(label="View usage", kind="open_settings")],
        ),
        status.HTTP_429_TOO_MANY_REQUESTS,
    )


def _pro_required() -> AppError:
    return AppError(
        ErrorEnvelope(
            code="PRO_REQUIRED",
            severity="warning",
            title="Upgrade required",
            body=(
                "This platform-paid route requires Pro. Bring your own key or upgrade to continue."
            ),
            actions=[ErrorAction(label="View billing", kind="open_settings")],
        ),
        status.HTTP_402_PAYMENT_REQUIRED,
    )


async def _enforce_platform_entitlement(
    db: AsyncSession,
    *,
    user: User,
    tier_id: ModelTierId,
    api_key: str | None,
) -> None:
    if api_key is not None or not tier_requires_pro(tier_id):
        return
    if await _has_platform_pro_access(db, user=user, api_key=api_key):
        return
    raise _pro_required()


async def _has_platform_pro_access(
    db: AsyncSession,
    *,
    user: User,
    api_key: str | None,
) -> bool:
    if api_key is not None:
        return True
    return await billing_repo.has_active_pro_entitlement(db, user_id=user.id)


@router.get("/search", response_model=list[ConversationSearchResult])
@limiter.limit(lambda: get_settings().rate_limit_search)
async def search_conversations(
    q: Annotated[str, Query(min_length=1, max_length=100)],
    request: Request,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationSearchResult]:
    await _enforce_retention(db, user.id)
    return await conversations_repo.search_for_user(
        db,
        user.id,
        query=q,
        limit=limit,
    )


@router.get("/{conversation_id}", response_model=ConversationSchema)
async def get_conversation(
    conversation_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSchema:
    await _enforce_retention(db, user.id)
    convo = await conversations_repo.get_for_user(db, conversation_id, user.id)
    if convo is None:
        raise not_found("conversation")
    return convo


@router.post(
    "",
    response_model=ConversationSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    body: CreateConversationRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSchema:
    settings = get_settings()
    selected_provider_id = _selected_provider_id(body.provider_id, settings)
    binding = _resolve_binding(body.selected_tier_id, body.provider_id, settings)
    resolved_api_key: str | None = None
    if not user.is_anonymous:
        resolved_api_key = await api_keys_repo.get_decrypted_for_user(
            db, user_id=user.id, provider=binding.provider_id
        )
    _ensure_provider_usable(
        provider_id=selected_provider_id,
        settings=settings,
        api_key=resolved_api_key,
    )
    await _enforce_platform_entitlement(
        db,
        user=user,
        tier_id=body.selected_tier_id,
        api_key=resolved_api_key,
    )

    if body.is_temporary:
        synthetic_id = uuid4()
        _TEMP_IDS[user.id].add(synthetic_id)
        return ConversationSchema(
            id=str(synthetic_id),
            title="New chat",
            messages=[],
            selected_tier_id=body.selected_tier_id,
            is_temporary=True,
        )

    convo = await conversations_repo.create_for_user(
        db,
        user_id=user.id,
        selected_tier_id=body.selected_tier_id,
    )
    return ConversationSchema(
        id=str(convo.id),
        title=convo.title,
        messages=[],
        selected_tier_id=body.selected_tier_id,
        is_temporary=False,
    )


@router.post(
    "/{conversation_id}/branch",
    response_model=ConversationSchema,
    status_code=status.HTTP_201_CREATED,
)
async def branch_conversation(
    conversation_id: UUID,
    body: BranchConversationRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSchema:
    """Create a new owned conversation copied through `messageId`.

    The source remains unchanged. The repository copies message content and
    attribution only; usage rollups are not touched and copied messages do not
    carry `message.cost_usd`, so branching cannot re-bill historical turns.
    """
    try:
        message_id = UUID(body.message_id)
    except ValueError as exc:
        raise _invalid_input("INVALID_INPUT", "messageId must be a UUID.") from exc

    branched = await conversations_repo.branch_for_user(
        db,
        source_conversation_id=conversation_id,
        user_id=user.id,
        through_message_id=message_id,
    )
    if branched is None:
        raise not_found("conversation")
    return branched


@router.patch("/{conversation_id}", response_model=ConversationSchema)
async def patch_conversation(
    conversation_id: UUID,
    body: PatchConversationRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSchema:
    """Rename and/or pin the conversation. Returns the full updated body so the
    FE avoids a follow-up GET.

    Empty patch (`{}` or all-nulls) -> 400 INVALID_INPUT. Not-owned -> 404.
    """
    patch_dict = body.model_dump(exclude_unset=True)
    # Reject `{}` AND `{"title": null, "pinned": null}` — both are no-ops.
    # `exclude_unset` keeps explicit nulls in the dict (they ARE "set"), so a
    # plain truthiness check would let `{title: null, pinned: null}` slip
    # through to `update_for_user`, which would only bump `updated_at`.
    if not any(v is not None for v in patch_dict.values()):
        raise _invalid_input(
            "INVALID_INPUT", "PATCH body must include at least one of: title, pinned."
        )
    updated_row = await conversations_repo.update_for_user(
        db,
        conversation_id,
        user.id,
        title=body.title,
        pinned=body.pinned,
    )
    if updated_row is None:
        raise not_found("conversation")
    # Re-fetch with messages — keeps response shape identical to GET. The patch
    # itself was just a header/pin/title change; messages list won't churn.
    convo = await conversations_repo.get_for_user(db, conversation_id, user.id)
    if convo is None:  # pragma: no cover — would only fire on a concurrent DELETE
        raise not_found("conversation")
    return convo


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete the conversation. Idempotent.

    Idempotency choice: DELETE on a missing (or not-owned) id still returns 204.
    This matches the plan's "Idempotent." wording and lets the FE delete twice
    without surfacing a spurious "not found" toast on the second call. The
    cascade (`message` -> `vote`) is enforced by the FK in the migration.

    Note: anonymous + temporary conversations live in an in-process set; they
    don't have DB rows, but the FE still calls DELETE on them when the user
    drops a temp chat. We silently treat that as 204 — `_TEMP_IDS.discard()`
    cleans up the synthetic id if it was ours.
    """
    if _is_temp_for_user(user.id, conversation_id):
        _TEMP_IDS[user.id].discard(conversation_id)
        return None
    await conversations_repo.delete_for_user(db, conversation_id, user.id)
    return None


@router.post("/{conversation_id}/share", response_model=ShareLinkResponse)
async def create_share_link(
    conversation_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ShareLinkResponse:
    """Mint (or return the existing) public-by-link share token for the convo.

    Public-by-link is the explicit exception to cost transparency: a holder of
    the token reads the conversation + model attribution but NEVER per-message
    cost (see `GET /api/share/{token}` and `app.schemas.share`).

    - Ownership-checked: 404 (not 403) if the caller doesn't own the
      conversation, so the route never leaks that the id exists.
    - Idempotent: re-minting an already-shared conversation returns the SAME
      token (no rotation), so previously distributed links keep working.
    - Anonymous owners can share too — sharing is an ownership affordance, not a
      BYOK-gated one, so there's no `is_anonymous` gate here.
    - Temporary chats have no DB row, so they cannot be shared (treated as not
      owned -> 404).
    """
    if _is_temp_for_user(user.id, conversation_id):
        raise not_found("conversation")
    token = await conversations_repo.mint_share_token(db, conversation_id, user.id)
    if token is None:
        raise not_found("conversation")
    await audit_events_repo.record(
        db,
        user_id=user.id,
        event_type="share.mint",
        details={"conversationId": str(conversation_id)},
    )
    return ShareLinkResponse(share_token=token, share_path=f"/share/{token}")


@router.delete("/{conversation_id}/share", status_code=status.HTTP_204_NO_CONTENT)
async def delete_share_link(
    conversation_id: UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke the conversation's share token. Ownership-checked, idempotent.

    Clears `share_token` back to NULL so the previously minted public link
    404s. Revoking an unshared (or already-revoked) conversation is a 204 no-op.
    Not owned / missing (incl. temporary chats) -> 404, mirroring the rest of
    this router.
    """
    if _is_temp_for_user(user.id, conversation_id):
        raise not_found("conversation")
    revoked = await conversations_repo.revoke_share_token(db, conversation_id, user.id)
    if not revoked:
        raise not_found("conversation")
    await audit_events_repo.record(
        db,
        user_id=user.id,
        event_type="share.revoke",
        details={"conversationId": str(conversation_id)},
    )
    return None


def _is_temp_for_user(user_id: UUID, conversation_id: UUID) -> bool:
    return conversation_id in _TEMP_IDS.get(user_id, set())


async def _maybe_replay(
    db: AsyncSession,
    conversation_id: UUID,
    client_uuid: UUID,
    request_fingerprint: dict[str, object] | None = None,
    request: Request | None = None,
) -> EventSourceResponse | None:
    """If a prior user message + completed assistant row exist, return a replay.

    Returns the SSE replay response when the prior turn's assistant row is
    `status in ("done", "stopped")`. Returns None when no prior user message
    exists at all (so the caller can proceed to INSERT). Raises
    DUPLICATE_IN_FLIGHT (409) if the user row exists but no assistant row has
    landed yet (in-flight on a concurrent worker or crashed before persist).

    Resolution strategy (post-M4):
    1. Column lookup via `responds_to_message_id` — an indexed seek that
       returns the assistant row whose explicit pointer matches the prior
       user message. Cheap and unambiguous.
    2. Pair-by-index fallback — for rows pre-dating the column (legacy data
       with `responds_to_message_id IS NULL`). Pairs the i-th user message
       with the i-th assistant by `(created_at, id)` ordering. M1 invariant
       of "one assistant per user message" still holds for legacy data, so
       the fallback is reliable for those rows.
    """
    prior_user_msg = await messages_repo.get_by_client_message_id(
        db,
        conversation_id,
        client_uuid,
    )
    if prior_user_msg is None:
        return None
    if (
        request_fingerprint is not None
        and prior_user_msg.request_fingerprint is not None
        and not _request_fingerprints_match(
            prior_user_msg.request_fingerprint,
            request_fingerprint,
        )
    ):
        raise _idempotency_mismatch()

    # Primary path: column-based lookup. Indexed; O(log n).
    assistant_row = await messages_repo.get_assistant_for_user_message(db, prior_user_msg.id)

    # Fallback for legacy rows whose responds_to_message_id is NULL (data
    # written before the 0005 migration). Pair-by-index on the i-th user/i-th
    # assistant by (created_at, id) ordering.
    if assistant_row is None:
        all_stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        all_msgs = (await db.execute(all_stmt)).scalars().all()
        user_msgs = [m for m in all_msgs if m.role == "user"]
        # Only consider legacy (NULL pointer) assistants for the fallback so a
        # mixed conversation (some rows migrated, some not) doesn't double-
        # count an assistant we already failed to match above.
        asst_msgs = [
            m for m in all_msgs if m.role == "assistant" and m.responds_to_message_id is None
        ]
        user_index = next(
            (i for i, m in enumerate(user_msgs) if m.id == prior_user_msg.id),
            None,
        )
        assistant_row = (
            asst_msgs[user_index]
            if user_index is not None and user_index < len(asst_msgs)
            else None
        )

    # Gate replay on `status` rather than `attribution is not None`. A
    # `status="stopped"` row also has attribution (an estimate), but the
    # original turn never emitted `terminal`. We replay both done and stopped —
    # for stopped, the client sees the same partial text + a terminal carrying
    # the stored `costConfidence="estimate"` attribution. From the wire's
    # perspective this is a regular replay; the FE does not currently render
    # the done/stopped distinction.
    if assistant_row is not None and assistant_row.status in ("done", "stopped"):
        # Defensive: `attribution` is a nullable column. A done/stopped row with
        # `attribution IS NULL` (manually-seeded or partially-migrated) would
        # raise inside `_replay_response`'s `ModelAttribution.model_validate(...)`
        # → generic 500. Fall through to a fresh insert instead of replaying.
        if assistant_row.attribution is None:
            return None
        # Replay path. Reconstruct prior answer text + any web-search frames
        # (status / sources) from the persisted parts, so a reconnecting client
        # sees the SAME sequence the original turn streamed: a grounded turn
        # replays its `status` and `sources` frames, not just the answer.
        reasoning_texts: list[str] = []
        texts: list[str] = []
        status_part: dict[str, object] | None = None
        sources_items: list[dict[str, object]] = []
        # Whether a `sources` part was persisted at all, and whether it marked
        # web search as effective. An empty `items` with `requested=True` is the
        # ungrounded turn, which must still replay its `sources` frame so a
        # reconnecting client renders "Answered without live sources".
        sources_requested = False
        tool_parts: list[dict[str, object]] = []
        for part in cast(list[dict[str, object]], assistant_row.parts or []):
            ptype = part.get("type")
            if ptype == "reasoning":
                reasoning_texts.append(str(part.get("text", "")))
            elif ptype == "text":
                texts.append(str(part.get("text", "")))
            elif ptype == "status":
                status_part = part
            elif ptype == "sources":
                sources_items = cast(list[dict[str, object]], part.get("items", []) or [])
                sources_requested = bool(part.get("requested", False))
            elif ptype in ("tool_call", "tool_result"):
                tool_parts.append(part)
        return _replay_response(
            user_message_id=prior_user_msg.id,
            assistant_message_id=assistant_row.id,
            reasoning_text="".join(reasoning_texts),
            answer_text="".join(texts),
            attribution_dict=cast(dict[str, object], assistant_row.attribution),
            status_part=status_part,
            sources_items=sources_items,
            sources_requested=sources_requested,
            tool_parts=tool_parts,
        )
    # User message exists but no completed assistant row: prior is in flight
    # (or crashed before persisting). With resumable streams enabled, an
    # idempotent retry can rejoin the active stream instead of receiving a
    # stream-id-less 409. This is intentionally keyed through the durable active
    # stream row: there can be at most one per conversation, and it corresponds
    # to the in-flight user message protected by this idempotency check.
    settings = get_settings()
    if settings.resumable_streams_enabled:
        latest_user_msg = await messages_repo.get_last_user_message(db, conversation_id)
        active_stream = await streams_repo.get_active_for_conversation(
            db, conversation_id=conversation_id
        )
        if (
            active_stream is not None
            and latest_user_msg is not None
            and latest_user_msg.id == prior_user_msg.id
        ):
            active_stream_id = active_stream.id
            prior_user_msg_id = prior_user_msg.id
            try:
                buffer = await replay_registry.get_async(
                    active_stream_id,
                    ttl_seconds=settings.resumable_buffer_ttl_seconds,
                )
            except ReplayLogTruncatedError as exc:
                raise _stream_replay_truncated() from exc
            if buffer is not None:
                return _eventsource_response(
                    _replay_buffer_events(
                        request=request,
                        buffer=buffer,
                        expected_user_message_id=prior_user_msg_id,
                    ),
                    media_type="text/event-stream",
                )

            async def _unavailable_stream() -> AsyncIterator[ServerSentEvent]:
                yield encode_submitted(
                    SubmittedEvent(
                        message_id=str(prior_user_msg_id),
                        stream_id=str(active_stream_id),
                    )
                )
                yield encode_error(_stream_replay_unavailable_envelope())

            return _eventsource_response(
                _unavailable_stream(),
                media_type="text/event-stream",
            )

    # No resumable reattach path is available. Reject as duplicate.
    raise _duplicate_in_flight()


@router.post("/{conversation_id}/messages")
@limiter.limit(lambda: get_settings().rate_limit_messages)
async def send_message(
    conversation_id: UUID,
    body: SendMessageRequest,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """Stream a turn. SSE response.

    Implementation notes:
    - `regenerate=true`: drop the trailing assistant turn(s), keep the
      existing user message, re-stream against an unchanged history. New
      `clientMessageId` is required (FE generates a fresh one); the
      `submitted` event echoes the EXISTING user message's id so the FE
      keeps the same user bubble.
    - `editMessageId=<uuid>`: truncate at that message (exclusive of nothing
      — the user message at that id is deleted along with everything after).
      Insert a new user message with the request body's `text` +
      `clientMessageId` at the truncation point, then re-stream.
    - Idempotency: if a prior assistant message exists for this
      `(conversation_id, client_message_id)`, replay it as one frame.
      Regenerate / edit by definition use a NEW clientMessageId so this
      branch should never hit on those paths.
    - Ownership: 404 if the conversation isn't owned by the caller (and isn't
      a known temporary id for them).
    - Unknown tier: 400.
    - Mutual exclusion: `regenerate=true` AND `editMessageId` set in the same
      body is 400 INVALID_INPUT (semantically incoherent).
    """
    settings = get_settings()
    user_prefs = await preferences_repo.get_or_default(db, user.id)
    # Effective monthly cap = min of the operator quota and the user's own
    # budget (whichever positive caps exist; 0.0 = no cap). Computed once here so
    # the budget gate AND the handler's credit-debit math use the same value.
    effective_quota_usd = _effective_quota_usd(
        settings.usage_budget_usd, user_prefs.monthly_budget_usd
    )
    selected_provider_id = _selected_provider_id(body.provider_id, settings)
    # Tier/provider validation.
    binding = _resolve_binding(body.tier_id, body.provider_id, settings)
    request_fingerprint = _request_fingerprint(
        body,
        provider_id=selected_provider_id,
    )

    # client_message_id must be a UUID.
    try:
        client_uuid = UUID(body.client_message_id)
    except ValueError as exc:
        raise _invalid_input("INVALID_INPUT", "clientMessageId must be a UUID.") from exc

    # regenerate / editMessageId / continueTurn / toolApproval are mutually
    # exclusive — each is a distinct recovery / resume mode, and combining them is
    # semantically incoherent.
    mode_flags = sum(
        (
            bool(body.regenerate),
            body.edit_message_id is not None,
            bool(body.continue_turn),
            body.tool_approval is not None,
        )
    )
    if mode_flags > 1:
        raise _invalid_input(
            "INVALID_INPUT",
            "regenerate, editMessageId, continueTurn, and toolApproval are mutually exclusive.",
        )

    is_temp = body.is_temporary or _is_temp_for_user(user.id, conversation_id)

    # Regenerate / edit / continue / toolApproval are not meaningful for temporary
    # chats (no prior rows to drop / truncate / continue / resume). Reject so the
    # FE doesn't silently degrade.
    if is_temp and (
        body.regenerate
        or body.edit_message_id is not None
        or body.continue_turn
        or body.tool_approval is not None
    ):
        raise _invalid_input(
            "INVALID_INPUT",
            "regenerate / editMessageId / continueTurn / toolApproval are not supported "
            "on temporary chats.",
        )

    # BYOK resolution + budget gate. Resolved here (before any user-message
    # insert / branch logic) so the cost-based budget gate can tell whether
    # this is a platform-key turn (counts against the cap) or a BYOK turn (the
    # user pays their own provider, so it is exempt). The resolved value is
    # threaded through to `stream_and_persist` unchanged.
    #
    # BYOK: pull the user's encrypted key for the bound provider
    # (`binding.provider_id` — e.g. "anthropic" or "openai" depending on the
    # active backend). Anonymous users never have keys; decryption failure
    # inside the repo returns None (logged), so this is silently safe and the
    # call falls back to the platform key.
    resolved_api_key: str | None = None
    if not user.is_anonymous:
        resolved_api_key = await api_keys_repo.get_decrypted_for_user(
            db, user_id=user.id, provider=binding.provider_id
        )

    # Ownership / existence check.
    if not is_temp:
        await _enforce_retention(db, user.id)
        owner_row = await conversations_repo.owned_by(db, conversation_id, user.id)
        if owner_row is None:
            raise not_found("conversation")

        # Idempotency: prior user message for this client_message_id?
        # Regenerate / continue / toolApproval reuse an existing user row and the
        # FE mints a fresh id, so they have no persisted client_message_id row to
        # replay. Normal sends and edits both insert a user row; exact fingerprint
        # matches can safely replay before budget/provider gates, while
        # mismatches get a 409.
        if not body.regenerate and not body.continue_turn and body.tool_approval is None:
            replay = await _maybe_replay(
                db,
                conversation_id,
                client_uuid,
                request_fingerprint,
                request,
            )
            if replay is not None:
                return replay

        # Cost-based budget enforcement. Only platform-key turns count against
        # the cap (BYOK turns are exempt — the user pays their own provider).
        # A positive credit balance extends the monthly quota; once quota is
        # consumed, terminal platform-key turns debit credits post-hoc.
        # `usage_budget_usd <= 0` disables the cap entirely (the default), so
        # existing behavior is unchanged. The cap is read against the current
        # period's accumulated cost ledger; reaching it refuses the next turn.
        #
        # This gate is BEST-EFFORT / POST-HOC, not a hard ceiling at MVP: it
        # checks the already-accumulated cost before starting a turn, so the
        # current turn's own cost is unbounded by it (a single expensive turn
        # can push the period total past the cap before the NEXT turn is
        # refused), and concurrent in-flight turns can each pass the check then
        # accumulate, overshooting the cap (bounded by concurrency).
        _ensure_provider_usable(
            provider_id=selected_provider_id,
            settings=settings,
            api_key=resolved_api_key,
        )
        await _enforce_platform_entitlement(
            db,
            user=user,
            tier_id=body.tier_id,
            api_key=resolved_api_key,
        )

        # Effective cap (min of operator quota + user's own budget) was computed
        # once at the top of this handler; gate the platform-key turn against it.
        if effective_quota_usd > 0 and resolved_api_key is None:
            has_allowance = await usage_repo.has_platform_allowance(
                db,
                user_id=user.id,
                monthly_quota_usd=effective_quota_usd,
            )
            if not has_allowance:
                async with _derive_session_factory(db)() as event_db:
                    await analytics_repo.record(
                        event_db,
                        user_id=user.id,
                        event_type="budget.exceeded",
                        properties={
                            "conversationId": str(conversation_id),
                            "requestedTierId": body.tier_id,
                            "providerId": selected_provider_id,
                        },
                    )
                    await event_db.commit()
                raise _budget_exceeded()

        # Per-conversation budget cap (D27). Layered OVER the monthly gate and
        # independent of it: platform-key turns only (BYOK pays their own
        # provider), non-temporary only (temp chats have no persisted cost
        # ledger), and only when the user set a positive cap. Reaching the
        # conversation's accumulated surviving-assistant cost refuses the next
        # turn — same best-effort/post-hoc semantics as the monthly gate.
        per_conversation_cap = user_prefs.per_conversation_budget_usd or 0.0
        if per_conversation_cap > 0 and resolved_api_key is None and not is_temp:
            conversation_cost = await usage_repo.get_conversation_cost(
                db, conversation_id
            )
            if conversation_cost >= per_conversation_cap:
                async with _derive_session_factory(db)() as event_db:
                    await analytics_repo.record(
                        event_db,
                        user_id=user.id,
                        event_type="budget.exceeded",
                        properties={
                            "conversationId": str(conversation_id),
                            "requestedTierId": body.tier_id,
                            "providerId": selected_provider_id,
                            "scope": "conversation",
                        },
                    )
                    await event_db.commit()
                raise _conversation_budget_exceeded()
    else:
        _ensure_provider_usable(
            provider_id=selected_provider_id,
            settings=settings,
            api_key=resolved_api_key,
        )
        await _enforce_platform_entitlement(
            db,
            user=user,
            tier_id=body.tier_id,
            api_key=resolved_api_key,
        )

    provider_attachments: list[AttachmentPayload] = []
    # Regenerate / continue / toolApproval all reuse the existing trailing user
    # message (no new user turn is inserted), so the request body's attachments /
    # text are ignored and safety is re-checked against the persisted user
    # message.
    reuses_existing_user_message = (
        body.regenerate or body.continue_turn or body.tool_approval is not None
    )
    if not reuses_existing_user_message:
        if body.attachments and not binding.supports_attachments:
            raise _attachments_unsupported()
        provider_attachments = _decode_attachment_payloads(
            body.attachments,
            max_count=settings.attachment_max_count,
            max_bytes=settings.attachment_max_bytes,
        )
        # Defense-in-depth: images require a vision-capable binding. A binding
        # may accept attachments (text/PDF as transcript) without being
        # multimodal (e.g. DeepSeek), so reject images cleanly here instead of
        # letting the provider error on a payload it can't interpret.
        if not binding.supports_vision and any(
            payload.media_type == "image" for payload in provider_attachments
        ):
            raise _vision_unsupported()
        safety_decision = check_user_turn(
            settings,
            text=body.text,
            attachments=provider_attachments,
            custom_instructions=user_prefs.custom_instructions,
        )
        if not safety_decision.allowed:
            await _record_moderation_blocked(
                db, user=user, decision=safety_decision, conversation_id=conversation_id
            )
            raise _safety_blocked(safety_decision)
    elif (body.regenerate or body.continue_turn or body.tool_approval is not None) and not is_temp:
        # Regenerate / continue / toolApproval all re-stream against the persisted
        # trailing user message; re-check it against the safety policy (it may have
        # tightened since the original send). Edited tool inputs get an additional
        # safety pass inside `_prepare_resume_tool`.
        last_user = await messages_repo.get_last_user_message(db, conversation_id)
        if last_user is not None:
            safety_decision = check_user_turn(
                settings,
                text=_text_from_parts(last_user.parts),
                attachments=_attachment_payloads_from_parts(last_user.parts),
                custom_instructions=user_prefs.custom_instructions,
            )
            if not safety_decision.allowed:
                await _record_moderation_blocked(
                    db, user=user, decision=safety_decision, conversation_id=conversation_id
                )
                raise _safety_blocked(safety_decision)

    provider = build_provider(
        settings,
        provider_id=body.provider_id,
        api_key=resolved_api_key,
    )

    # Claim the single active stream BEFORE mutating message history. The row is
    # still in the current transaction, so later validation/insert failures roll
    # it back; successful non-temporary branches commit it together with the user
    # message/history mutation below.
    stream_id: UUID | None = None
    if not is_temp:
        existing_active = await streams_repo.get_active_for_conversation(
            db, conversation_id=conversation_id
        )
        if existing_active is not None:
            raise _stream_in_progress()
        try:
            stream_row = await streams_repo.create_stream(db, conversation_id=conversation_id)
        except streams_repo.ActiveStreamExistsError as exc:
            await db.rollback()
            if not body.regenerate:
                replay = await _maybe_replay(
                    db,
                    conversation_id,
                    client_uuid,
                    request_fingerprint,
                    request,
                )
                if replay is not None:
                    return replay
            raise _stream_in_progress() from exc
        stream_id = stream_row.id

    # Branch by mode:
    #   regenerate -> drop trailing assistant(s), reuse existing user message
    #   continueTurn -> keep the stopped partial assistant, reuse its user
    #                   message, replay the partial as the trailing assistant
    #                   turn and send the continuation instruction as the turn
    #   editMessageId -> truncate from that user message inclusive, insert new
    #   default -> existing M1 path
    user_message_id: UUID
    history: list[ProviderChatMessage]
    provider_user_text: str
    # Resume seed for an approval-gated tool (HITL). None on every non-resume
    # path; set by `_prepare_resume_tool` so the handler emits the seeded
    # `tool_result` before the post-approval provider pass.
    resume_seed: ResumeToolSeed | None = None

    if body.regenerate:
        (
            user_message_id,
            history,
            provider_user_text,
            provider_attachments,
        ) = await _prepare_regenerate(
            db=db,
            conversation_id=conversation_id,
            supports_attachments=binding.supports_attachments,
            supports_vision=binding.supports_vision,
        )
    elif body.continue_turn:
        (
            user_message_id,
            history,
            provider_user_text,
            provider_attachments,
        ) = await _prepare_continue(
            db=db,
            conversation_id=conversation_id,
            supports_attachments=binding.supports_attachments,
            supports_vision=binding.supports_vision,
        )
    elif body.tool_approval is not None:
        (
            user_message_id,
            history,
            provider_user_text,
            provider_attachments,
            resume_seed,
        ) = await _prepare_resume_tool(
            db=db,
            user=user,
            conversation_id=conversation_id,
            decision=body.tool_approval,
            settings=settings,
            custom_instructions=user_prefs.custom_instructions,
            supports_attachments=binding.supports_attachments,
            supports_vision=binding.supports_vision,
        )
    elif body.edit_message_id is not None:
        user_message_id, history, provider_user_text = await _prepare_edit(
            db=db,
            conversation_id=conversation_id,
            edit_message_id_str=body.edit_message_id,
            client_uuid=client_uuid,
            new_text=body.text,
            attachments=body.attachments,
            request_fingerprint=request_fingerprint,
        )
    elif is_temp:
        user_message_id = uuid4()
        history = []
        provider_user_text = body.text
    else:
        history = await messages_repo.load_history(db, conversation_id)
        try:
            user_msg_row = await messages_repo.create_user_message(
                db=db,
                conversation_id=conversation_id,
                client_message_id=client_uuid,
                text=body.text,
                attachments=body.attachments,
                request_fingerprint=request_fingerprint,
            )
            # A new turn was accepted — bump the conversation so it rises in
            # the sidebar. Same session/transaction as the user message, so it
            # commits atomically with the turn below (not on idempotent replay,
            # which returns earlier without reaching this insert).
            await conversations_repo.touch_updated_at(db, conversation_id)
            # Commit so the user message is durable before we stream — the
            # EventSourceResponse will reuse this session, so flush+commit now.
            await db.commit()
        except IntegrityError:
            # Concurrent POSTs with the same clientMessageId can both pass the
            # idempotency check above and race on INSERT; one will lose to the
            # `message_client_msg_uniq` unique constraint. Roll back and retry
            # the replay path — if the winner has already produced an assistant
            # row, we replay it; otherwise return 409 DUPLICATE_IN_FLIGHT.
            await db.rollback()
            replay = await _maybe_replay(
                db,
                conversation_id,
                client_uuid,
                request_fingerprint,
                request,
            )
            if replay is not None:
                return replay
            raise _duplicate_in_flight() from None
        user_message_id = user_msg_row.id
        provider_user_text = body.text

    # Auto-tier routing. When the user picked `auto`, run the v0 complexity
    # heuristic (providers/router.py) to choose the concrete tier that actually
    # serves + bills this turn. We rebind `binding` to the routed tier so:
    #   - pricing bills the model actually served (compute_cost_breakdown reads
    #     `binding`), and
    #   - `resolve_served_tier(binding)` surfaces a concrete served tier on the
    #     wire (the routed binding is fast/smart/pro, never `auto`).
    # `requested_tier_id` stays `auto` (threaded separately), so the FE still
    # shows the user requested Auto.
    #
    # Honest surfacing: when the routed tier is CHEAPER than the auto baseline
    # (`smart`), we set a router-side `auto_downgrade` substitution so the
    # downgrade is visible on the wire — never silent (PRD §2.2.4 / §7.4).
    # `auto_downgrade` is the only auto-routing reason code the FE renders
    # (web/src/lib/types.ts::SubstitutionReasonCode). Routing to baseline or
    # escalating above it emits no substitution. The router-side reason is the
    # SEED; a real provider fallback overwrites it inside the handler (provider
    # fallback wins precedence).
    router_substitution: SubstitutionReasonCode | None = None
    settings_for_routing = settings
    if body.tier_id == "auto" and settings_for_routing.auto_routing_enabled:
        routed = route_auto(provider_user_text, history)
        routed_tier_id = routed.tier_id
        if routed_tier_id == "pro" and not await _has_platform_pro_access(
            db,
            user=user,
            api_key=resolved_api_key,
        ):
            routed_tier_id = "smart"
        routed_binding = get_binding(
            routed_tier_id,
            settings=settings_for_routing,
            provider_id=body.provider_id,
        )
        # Defensive: a known concrete tier always has a binding; fall back to the
        # original `auto` binding rather than 500 if the registry ever diverges.
        if routed_binding is not None:
            binding = routed_binding
        if routed.is_downgrade and routed_tier_id == routed.tier_id:
            router_substitution = "auto_downgrade"

    # The `binding` is now FINALIZED (provider override + auto-route rebind both
    # applied). Compute the per-turn reasoning-effort overrides and the
    # provider-fallback route off the final binding/provider.

    # Feature 1: per-turn reasoning-effort override. Maps the hint to provider
    # call overrides; None means "use the binding default" for that hint.
    reasoning_effort_override, thinking_override = _map_reasoning_effort(
        body.reasoning_effort, binding
    )

    # Phase 2: pick a single alternate route to retry ONCE if the primary
    # provider raises a retryable error before emitting any token. None when no
    # alternate is usable — the error then surfaces as today. All routing policy
    # lives in `_select_fallback_route`; the handler stays dumb.
    fallback_route = await _select_fallback_route(
        binding.tier.id,
        binding.provider_id,
        settings,
        user=user,
        db=db,
        resolved_api_key=resolved_api_key,
    )
    fallback_binding: TierBinding | None = None
    fallback_provider_id: str | None = None
    fallback_api_key: str | None = None
    if fallback_route is not None:
        fallback_binding, fallback_provider_id, fallback_api_key = fallback_route

    # Durable stream lifecycle (PRD 04 §5.1). The active row was claimed before
    # message-history mutation and committed by the accepted branch above. The id
    # is threaded into `stream_and_persist`, which transitions it to done /
    # stopped / error and links the assistant `message_id`.

    # `resolved_api_key` was resolved earlier (before the budget gate) so the
    # cost cap could distinguish platform-key vs BYOK turns; it is threaded
    # through to the stream call below unchanged.

    # Title autogen must not re-fire when a regen / edit-of-first-turn deletes
    # the prior assistant(s) and leaves count_assistant_messages at 0. Gate it
    # explicitly on "this is a fresh send" so the handler can require BOTH
    # conditions before scheduling the detached autogen task.
    is_initial = (
        not body.regenerate
        and not body.continue_turn
        and body.edit_message_id is None
        and body.tool_approval is None
    )

    # Effective web-search opt-in for this turn. Unsupported provider/config
    # combinations degrade silently: the turn still answers, just ungrounded.
    effective_web_search = body.web_search and web_search_available_for_binding(
        binding,
        settings=settings,
    )
    # Structured-output (JSON mode) opt-in. Build the provider protocol object
    # from the request (None when absent) and thread it down the identical path
    # as `web_search`. Every adapter degrades gracefully, so there's no
    # binding-capability gate here — JSON mode always applies when requested.
    effective_response_format = (
        ResponseFormat(
            type=body.response_format.type,
            schema=body.response_format.schema_,
        )
        if body.response_format is not None
        else None
    )
    if not is_temp:
        event_props = {
            "conversationId": str(conversation_id),
            "requestedTierId": body.tier_id,
            "servedTierId": binding.tier.id,
            "providerId": selected_provider_id,
        }
        if body.regenerate:
            await analytics_repo.record(
                db,
                user_id=user.id,
                event_type="message.regenerated",
                properties=event_props,
            )
        if body.continue_turn:
            await analytics_repo.record(
                db,
                user_id=user.id,
                event_type="message.continued",
                properties=event_props,
            )
        if body.tool_approval is not None:
            await analytics_repo.record(
                db,
                user_id=user.id,
                event_type=(
                    "tool.approved"
                    if body.tool_approval.decision == "approve"
                    else "tool.denied"
                ),
                properties={
                    **event_props,
                    "toolCallId": body.tool_approval.tool_call_id,
                },
            )
        if body.edit_message_id is not None:
            await analytics_repo.record(
                db,
                user_id=user.id,
                event_type="message.edited",
                properties=event_props,
            )
        if effective_web_search:
            await analytics_repo.record(
                db,
                user_id=user.id,
                event_type="search.used",
                properties=event_props,
            )
        if effective_response_format is not None:
            await analytics_repo.record(
                db,
                user_id=user.id,
                event_type="structured_output.used",
                properties={
                    **event_props,
                    "outputFormat": effective_response_format.type,
                },
            )
        if provider_attachments:
            await analytics_repo.record(
                db,
                user_id=user.id,
                event_type="attachments.used",
                properties={
                    **event_props,
                    "attachmentCount": len(provider_attachments),
                    "imageCount": sum(
                        1 for attachment in provider_attachments if attachment.media_type == "image"
                    ),
                    "pdfCount": sum(
                        1 for attachment in provider_attachments if attachment.media_type == "pdf"
                    ),
                    "textCount": sum(
                        1 for attachment in provider_attachments if attachment.media_type == "text"
                    ),
                },
            )

    # Transparent long-term memory (D19): load the caller's saved facts to inject
    # ONLY when memory is opt-in enabled AND the turn is not temporary. Temporary
    # chats skip persistence (handler.py) and must skip injection too — they are
    # the user's escape hatch from memory. The handler folds these into the user
    # turn (`_apply_memory`) and surfaces the injected count on the attribution.
    memory_facts: list[str] = []
    if user_prefs.memory_enabled and not is_temp:
        memory_facts = await memory_repo.list_for_injection(db, user.id)

    # Resumable-stream replay (flag ON, non-temporary turns only). Spawn the
    # provider pump as a DETACHED producer that survives this connection and
    # appends every wire event to an in-process ReplayBuffer; this POST then
    # SUBSCRIBES and tails the buffer. A client disconnect stops the tailing but
    # NOT the producer (the semantics inversion). Reconnects re-subscribe via
    # `GET .../stream/{stream_id}`. Temporary chats (no `stream_id`, nothing
    # persisted, nothing to reconnect to) always take the legacy inline path,
    # even with the flag on.
    if settings.resumable_streams_enabled and not is_temp and stream_id is not None:
        ttl = settings.resumable_buffer_ttl_seconds
        buffer = await replay_registry.create_async(stream_id, ttl_seconds=ttl)
        # The detached producer owns a FRESH session derived from THIS request's
        # engine (the request session closes when the POST returns). Using
        # `_derive_session_factory(db)` keeps tests bound to the per-test SQLite
        # file rather than the process-wide env DATABASE_URL factory.
        spawn_detached_producer(
            buffer=buffer,
            session_factory=_derive_session_factory(db),
            provider=provider,
            binding=binding,
            requested_tier_id=body.tier_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            user_text=provider_user_text,
            history=history,
            is_temporary=is_temp,
            is_initial=is_initial,
            user_id=user.id,
            api_key=resolved_api_key,
            provider_id=selected_provider_id,
            stream_id=stream_id,
            router_substitution=router_substitution,
            web_search=effective_web_search,
            response_format=effective_response_format,
            attachments=provider_attachments,
            custom_instructions=user_prefs.custom_instructions,
            memory_facts=memory_facts,
            reasoning_effort_override=reasoning_effort_override,
            thinking_override=thinking_override,
            monthly_quota_usd_override=effective_quota_usd,
            fallback_binding=fallback_binding,
            fallback_provider_id=fallback_provider_id,
            fallback_api_key=fallback_api_key,
            fallback_substitution="provider_fallback",
            tool_approval=body.tool_approval,
            resume_seed=resume_seed,
        )

        async def _subscriber_stream() -> AsyncIterator[ServerSentEvent]:
            # Subscribe at offset 0 and tail. On client disconnect we simply
            # stop iterating (the generator is GC'd / aclosed) — the producer
            # keeps running and persisting. Subscribers NEVER persist.
            async for sse_event in _replay_buffer_events(
                request=request,
                buffer=buffer,
                expected_user_message_id=user_message_id,
            ):
                yield sse_event

        return _eventsource_response(
            _subscriber_stream(),
            media_type="text/event-stream",
        )

    async def _event_stream() -> AsyncIterator[ServerSentEvent]:
        async for sse_event in stream_and_persist(
            request=request,
            db=db,
            provider=provider,
            binding=binding,
            requested_tier_id=body.tier_id,
            conversation_id=None if is_temp else conversation_id,
            user_message_id=user_message_id,
            user_text=provider_user_text,
            history=history,
            is_temporary=is_temp,
            is_initial=is_initial,
            user_id=user.id,
            api_key=resolved_api_key,
            provider_id=selected_provider_id,
            stream_id=stream_id,
            router_substitution=router_substitution,
            web_search=effective_web_search,
            response_format=effective_response_format,
            attachments=provider_attachments,
            custom_instructions=user_prefs.custom_instructions,
            memory_facts=memory_facts,
            reasoning_effort_override=reasoning_effort_override,
            thinking_override=thinking_override,
            monthly_quota_usd_override=effective_quota_usd,
            fallback_binding=fallback_binding,
            fallback_provider_id=fallback_provider_id,
            fallback_api_key=fallback_api_key,
            fallback_substitution="provider_fallback",
            tool_approval=body.tool_approval,
            resume_seed=resume_seed,
        ):
            yield sse_event

    return _eventsource_response(
        _event_stream(),
        media_type="text/event-stream",
    )


@router.get("/{conversation_id}/stream/{stream_id}")
@limiter.limit(lambda: get_settings().rate_limit_messages)
async def reconnect_stream(
    conversation_id: UUID,
    stream_id: UUID,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """Re-attach to a live (or just-finished) resumable stream (PRD 04 §5.1 P1).

    Same-device replay: subscribe to the in-process ReplayBuffer for
    `stream_id`, replay every buffered event from the start, then tail live
    until the detached producer is `done`. If the stream already terminated but
    its buffer is still within TTL, replay the full final sequence then close.

    Gated behind `resumable_streams_enabled` — when the flag is OFF the feature
    is not exposed, so this 404s (feature disabled), matching the rest of the
    router's "never reveal that the id exists" stance.

    Ownership / IDOR (404, never 403):
    - Conversation not owned by the caller (or missing / temporary) → 404.
    - Stream row missing, or belonging to a DIFFERENT conversation → 404.
    - No live/within-TTL buffer for the stream (never started on this worker,
      or evicted past TTL) → 404. Multi-worker: a reconnect that lands on a
      different worker than the producer finds no buffer → 404 (see the
      `replay_registry` module + `resumable_streams_enabled` config caveat).
    """
    settings = get_settings()
    if not settings.resumable_streams_enabled:
        # Feature disabled — do not expose new behavior. 404, not 403.
        raise not_found("stream")

    # Ownership: the conversation must be owned by the caller. Temporary chats
    # have no DB row / stream and are not resumable, so they fall through to 404.
    if _is_temp_for_user(user.id, conversation_id):
        raise not_found("stream")
    owner_row = await conversations_repo.owned_by(db, conversation_id, user.id)
    if owner_row is None:
        raise not_found("stream")

    # The stream must exist AND belong to THIS conversation (block cross-convo
    # IDOR: a valid stream id from another of the user's conversations must not
    # leak here either).
    stream_row = await streams_repo.get_by_id(db, stream_id=stream_id)
    if stream_row is None or stream_row.conversation_id != conversation_id:
        raise not_found("stream")

    # Live (or within-TTL done) buffer for this stream on this worker?
    try:
        buffer = await replay_registry.get_async(
            stream_id, ttl_seconds=settings.resumable_buffer_ttl_seconds
        )
    except ReplayLogTruncatedError as exc:
        raise _stream_replay_truncated() from exc
    if buffer is None:
        raise not_found("stream")

    async def _replay_stream() -> AsyncIterator[ServerSentEvent]:
        # Replay from offset 0 then tail. Disconnect just stops tailing; the
        # producer (and any other subscribers) are unaffected. This subscriber
        # NEVER persists.
        async for sse_event in _replay_buffer_events(request=request, buffer=buffer):
            yield sse_event

    return _eventsource_response(
        _replay_stream(),
        media_type="text/event-stream",
    )


@router.post("/{conversation_id}/stop", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(lambda: get_settings().rate_limit_messages)
async def stop_stream(
    conversation_id: UUID,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Dedicated server-side stop for an in-flight streaming turn (PRD 04 §5.1).

    P0 foundation for the P1 dedicated-stop / resumable-stream semantics. Today
    "stop" is implicit (the client closing the SSE socket -> the handler's
    `request.is_disconnected()` check); this endpoint makes it explicit and
    durable so a stop survives independent of the streaming connection.

    Mechanism (two halves, both best-effort):
    - Durable intent: touch the conversation's active `stream` row so the stop
      intent is observable without releasing the single-active-stream guard.
    - Live cancel: set the in-process stop signal (`request_stop`) so the
      running generator tears the turn down at its next poll. Single-worker
      only — behind multiple uvicorn workers a stop on worker A won't reach a
      stream running on worker B (same caveat as `_TEMP_IDS`). The actual
      generator cancellation is therefore best-effort.

    Idempotent 204:
    - No active stream (already finished / never started) -> 204, no-op.
    - Temporary conversations have no DB row and no stream row; treated as a
      204 no-op (nothing to stop, nothing persisted).
    - Not owned (or missing) -> 404, mirroring the rest of this router.
    """
    # Temporary chats: nothing persisted, nothing to stop. Idempotent 204.
    if _is_temp_for_user(user.id, conversation_id):
        return None

    owner_row = await conversations_repo.owned_by(db, conversation_id, user.id)
    if owner_row is None:
        raise not_found("conversation")

    active = await streams_repo.get_active_for_conversation(db, conversation_id=conversation_id)
    if active is not None:
        # Keep the durable row `active` until the producer actually observes the
        # stop signal and persists the partial assistant. If we marked it stopped
        # here, the active-stream guard would allow a second turn to start while
        # the old producer was still winding down. The repository call below
        # records stop intent by bumping `updated_at` without releasing that guard.
        await request_stop_async(active.id)
        await streams_repo.mark_status(db, stream_id=active.id, status="stopped")
    return None


async def _prepare_regenerate(
    *,
    db: AsyncSession,
    conversation_id: UUID,
    supports_attachments: bool,
    supports_vision: bool,
) -> tuple[UUID, list[ProviderChatMessage], str, list[AttachmentPayload]]:
    """Drop trailing assistant(s) and reuse the existing trailing user message.

    Returns `(user_message_id, history, user_text, attachments)` for the stream
    call. The returned `user_message_id` is the EXISTING trailing user message's
    id — `submitted` will echo it, the FE keeps the same user bubble.
    `user_text` is the original user message text (the body's `text` is ignored
    on regenerate per plan §"Behavior - Regenerate": user message not re-sent).
    """
    # Must have a trailing user message to regenerate against.
    last_user = await messages_repo.get_last_user_message(db, conversation_id)
    if last_user is None:
        raise _invalid_input(
            "INVALID_INPUT",
            "Cannot regenerate: no prior user message in this conversation.",
        )
    attachments = _attachment_payloads_from_parts(last_user.parts)
    if attachments and not supports_attachments:
        raise _attachments_unsupported()
    if not supports_vision and any(
        attachment.media_type == "image" for attachment in attachments
    ):
        raise _vision_unsupported()
    # Drop trailing assistant(s). Returns 0 if the last message is already a
    # user message (no assistant to drop) — that's still a valid regen (e.g.
    # a prior turn was stopped mid-stream and never persisted assistant).
    await messages_repo.delete_trailing_assistants(db, conversation_id=conversation_id)
    # Regenerate accepts a new turn (reusing the existing user message), so
    # bump the conversation to the top of the sidebar. Same session as the
    # trailing-assistant delete; commits atomically with the turn below.
    await conversations_repo.touch_updated_at(db, conversation_id)
    await db.commit()
    # Load history with the trailing assistant(s) gone, then strip the
    # trailing user message — the provider receives prior turns only, plus
    # `user_text` as the current submission.
    full_history = await messages_repo.load_history(db, conversation_id)
    # Trailing user message lives at the end of full_history now; pop it.
    user_text = ""
    if full_history and full_history[-1].role == "user":
        user_text = full_history[-1].text
        full_history = full_history[:-1]
    # Fallback: trust the persisted parts if history flattening lost data.
    if not user_text:
        user_text = _text_from_parts(last_user.parts)
    return last_user.id, full_history, user_text, attachments


async def _prepare_continue(
    *,
    db: AsyncSession,
    conversation_id: UUID,
    supports_attachments: bool,
    supports_vision: bool,
) -> tuple[UUID, list[ProviderChatMessage], str, list[AttachmentPayload]]:
    """Continue a previously-Stopped turn WITHOUT discarding the partial.

    Unlike `_prepare_regenerate`, this does NOT call `delete_trailing_assistants`
    — the stopped partial row stays in place. The continuation streams as a NEW
    assistant message linked to the SAME user message the stopped turn responded
    to (the returned `user_message_id`), so `submitted` echoes that user id and
    `stream_and_persist` sets `responds_to_message_id` to it.

    History building: `load_history` already flattens every turn including the
    stopped partial, so the returned `history` ends with
    `[…prior turns, the user message, the partial assistant message]`. The
    continuation instruction (`_CONTINUE_INSTRUCTION`) is returned as the
    `user_text` — sent as the new user turn so the model EXTENDS its own prior
    (partial) answer rather than restarting. The fake provider detects this
    exact constant to emit a deterministic continuation.

    Returns `(user_message_id, history, user_text, attachments)`. `attachments`
    is empty: the continuation instruction carries no files; the original user
    attachments already live in the replayed history. Validation still rejects a
    conversation whose persisted user attachments are incompatible with the
    served binding, matching the regenerate guard.
    """
    # Must have a trailing assistant turn, and it must be `status="stopped"` —
    # only a stopped (interrupted) turn can be continued. A `done` / `error`
    # trailing turn has nothing partial to extend.
    last_assistant = await messages_repo.get_last_assistant_message(db, conversation_id)
    if last_assistant is None or last_assistant.status != "stopped":
        raise _nothing_to_continue()

    # The continuation links to the SAME user message the stopped turn answered.
    # Fall back to the trailing user message if the legacy row predates the
    # `responds_to_message_id` column (NULL) — same pair-by-tail assumption the
    # rest of the router makes.
    user_message_id = last_assistant.responds_to_message_id
    if user_message_id is None:
        last_user = await messages_repo.get_last_user_message(db, conversation_id)
        if last_user is None:
            raise _nothing_to_continue()
        user_message_id = last_user.id

    user_row = await messages_repo.get_by_id(db, user_message_id)
    if user_row is None:
        raise _nothing_to_continue()

    # Re-validate the persisted user attachments against the served binding (the
    # served tier may differ from the stopped turn's). Mirrors regenerate.
    attachments = _attachment_payloads_from_parts(user_row.parts)
    if attachments and not supports_attachments:
        raise _attachments_unsupported()
    if not supports_vision and any(
        attachment.media_type == "image" for attachment in attachments
    ):
        raise _vision_unsupported()

    # History already includes the stopped partial as the trailing assistant
    # turn (load_history does not filter by status). The continuation
    # instruction goes out as the new user turn.
    history = await messages_repo.load_history(db, conversation_id)
    # No history mutation happens on continue, but bump the conversation so it
    # rises in the sidebar like any other accepted turn.
    await conversations_repo.touch_updated_at(db, conversation_id)
    await db.commit()
    return user_message_id, history, _CONTINUE_INSTRUCTION, []


def _find_pending_tool_call(
    parts: object,
    tool_call_id: str,
) -> dict[str, object] | None:
    """Find a pending, approval-awaiting `tool_call` part by id in a parts list."""
    if not isinstance(parts, list):
        return None
    for part in parts:
        if (
            isinstance(part, dict)
            and part.get("type") == "tool_call"
            and part.get("id") == tool_call_id
            and part.get("status") == "awaiting_approval"
            and part.get("approvalState") == "pending"
        ):
            return part
    return None


async def _prepare_resume_tool(
    *,
    db: AsyncSession,
    user: User,
    conversation_id: UUID,
    decision: ToolApprovalDecision,
    settings: Settings,
    custom_instructions: str | None,
    supports_attachments: bool,
    supports_vision: bool,
) -> tuple[UUID, list[ProviderChatMessage], str, list[AttachmentPayload], ResumeToolSeed]:
    """Resolve + RE-VALIDATE a human-in-the-loop tool approval, return the seed.

    Models `_prepare_continue`: the paused assistant row stays in place (NOT
    deleted), and the continuation streams as a NEW assistant row linked to the
    SAME user message the paused turn answered.

    SECURITY — the approval gate is the trust boundary, so NOTHING from the client
    is trusted on its own:
    - The trailing assistant MUST be `status="awaiting_approval"`, else 400
      NOTHING_TO_RESUME.
    - The decision's `tool_call_id` MUST match a pending `tool_call` part on that
      row, else 400 INVALID_INPUT (a forged id can't execute anything).
    - The named tool MUST exist in `TOOL_REGISTRY` AND genuinely
      `needs_approval`, else 400 INVALID_INPUT — a forged approve for an
      unknown / non-gated tool must never run.
    - Any client `edited_input` is re-validated against the tool's allowlist
      (400 INVALID_INPUT on violation) and re-run through the safety preflight.

    Returns `(user_message_id, history, provider_user_text, attachments, seed)`.
    `provider_user_text` is the approve/deny continuation instruction; the handler
    emits the seeded `tool_result` before that turn streams. `attachments` is
    empty (the original user attachments already live in the replayed history).
    """
    last_assistant = await messages_repo.get_last_assistant_message(db, conversation_id)
    if last_assistant is None or last_assistant.status != "awaiting_approval":
        raise _nothing_to_resume()

    pending = _find_pending_tool_call(last_assistant.parts, decision.tool_call_id)
    if pending is None:
        raise _invalid_input(
            "INVALID_INPUT",
            "toolApproval.toolCallId does not match a tool awaiting approval.",
        )

    tool_name = str(pending.get("name") or "")
    spec = TOOL_REGISTRY.get(tool_name)
    # Re-assert the gate server-side: the tool must exist AND genuinely require
    # approval. A forged approve for an unknown / non-gated tool is refused.
    if spec is None or not spec.needs_approval:
        raise _invalid_input(
            "INVALID_INPUT",
            "Approved tool is not an approval-gated tool.",
        )

    # Effective input: a validated `edited_input` overrides the originally
    # requested input; otherwise reuse the pending part's input.
    raw_input = pending.get("input")
    effective_input: dict[str, object] = (
        raw_input if isinstance(raw_input, dict) else {}
    )
    if decision.edited_input is not None:
        try:
            effective_input = validate_tool_input(tool_name, decision.edited_input)
        except ToolInputError as exc:
            raise _invalid_input("INVALID_INPUT", str(exc)) from exc
        # Re-run the safety preflight on the edited input — it is fresh
        # user-influenced content and the policy may have tightened.
        edited_text = " ".join(
            str(value) for value in effective_input.values() if isinstance(value, str)
        )
        if edited_text:
            safety_decision = check_user_turn(
                settings,
                text=edited_text,
                attachments=[],
                custom_instructions=custom_instructions,
            )
            if not safety_decision.allowed:
                await _record_moderation_blocked(
                    db, user=user, decision=safety_decision, conversation_id=conversation_id
                )
                raise _safety_blocked(safety_decision)

    # Link to the SAME user message the paused turn answered (fallback to the
    # trailing user message for legacy rows with a NULL pointer).
    user_message_id = last_assistant.responds_to_message_id
    if user_message_id is None:
        last_user = await messages_repo.get_last_user_message(db, conversation_id)
        if last_user is None:
            raise _nothing_to_resume()
        user_message_id = last_user.id

    user_row = await messages_repo.get_by_id(db, user_message_id)
    if user_row is None:
        raise _nothing_to_resume()

    # Re-validate the persisted user attachments against the served binding,
    # mirroring regenerate / continue.
    attachments = _attachment_payloads_from_parts(user_row.parts)
    if attachments and not supports_attachments:
        raise _attachments_unsupported()
    if not supports_vision and any(
        attachment.media_type == "image" for attachment in attachments
    ):
        raise _vision_unsupported()

    history = await messages_repo.load_history(db, conversation_id)
    await conversations_repo.touch_updated_at(db, conversation_id)
    await db.commit()

    label = pending.get("label")
    seed = ResumeToolSeed(
        tool_call_id=decision.tool_call_id,
        name=tool_name,
        label=str(label) if isinstance(label, str) else None,
        decision=decision.decision,
        input=dict(effective_input),
    )
    instruction = (
        _RESUME_APPROVE_INSTRUCTION
        if decision.decision == "approve"
        else _RESUME_DENY_INSTRUCTION
    )
    return user_message_id, history, instruction, [], seed


async def _prepare_edit(
    *,
    db: AsyncSession,
    conversation_id: UUID,
    edit_message_id_str: str,
    client_uuid: UUID,
    new_text: str,
    attachments: list[AttachmentPart] | None = None,
    request_fingerprint: dict[str, object] | None = None,
) -> tuple[UUID, list[ProviderChatMessage], str]:
    """Truncate at the edit target and insert a replacement user message.

    Returns `(new_user_message_id, history, user_text)` for the stream call.
    Validates that `editMessageId` parses as a UUID, exists in this
    conversation, and has `role="user"`. Truncation deletes the target row
    AND every row after it; the new user row is inserted with the request's
    `clientMessageId` + `text`.
    """
    try:
        edit_uuid = UUID(edit_message_id_str)
    except ValueError as exc:
        raise _invalid_input("INVALID_INPUT", "editMessageId must be a UUID.") from exc

    # Look up the target message and assert role / conversation membership.
    target = await messages_repo.get_by_id(db, edit_uuid)
    if target is None or target.conversation_id != conversation_id:
        raise _invalid_input(
            "INVALID_INPUT",
            "editMessageId does not reference a message in this conversation.",
        )
    if target.role != "user":
        raise _invalid_input(
            "INVALID_INPUT",
            "editMessageId must reference a user message.",
        )

    # Truncate at the target (inclusive) — drops the user message AND
    # every message that came after it.
    await messages_repo.truncate_from(
        db,
        conversation_id=conversation_id,
        message_id=edit_uuid,
    )
    # Load history BEFORE inserting the new user message — the provider
    # gets prior turns only, plus `user_text` as the current submission.
    history = await messages_repo.load_history(db, conversation_id)
    # Insert the replacement user message at the truncation point.
    try:
        new_row = await messages_repo.create_user_message(
            db=db,
            conversation_id=conversation_id,
            client_message_id=client_uuid,
            text=new_text,
            attachments=attachments,
            request_fingerprint=request_fingerprint,
        )
        # Edit-and-rerun accepts a new turn, so bump the conversation to the
        # top of the sidebar. Same session as the replacement user message;
        # commits atomically with the turn below.
        await conversations_repo.touch_updated_at(db, conversation_id)
        await db.commit()
    except IntegrityError as exc:
        # An edit submission with a clientMessageId that collides with an
        # already-existing user row is an error: the FE must mint a fresh id.
        await db.rollback()
        raise _invalid_input(
            "INVALID_INPUT",
            "clientMessageId already exists in this conversation.",
        ) from exc
    return new_row.id, history, new_text


def _replay_response(
    *,
    user_message_id: UUID,
    assistant_message_id: UUID,
    reasoning_text: str,
    answer_text: str,
    attribution_dict: dict[str, object],
    status_part: dict[str, object] | None = None,
    sources_items: list[dict[str, object]] | None = None,
    sources_requested: bool = False,
    tool_parts: list[dict[str, object]] | None = None,
) -> EventSourceResponse:
    """Replay a prior terminal as a single combined frame.

    Plan §"Behavior - Idempotency": yields `submitted` with the prior user
    message id, replays persisted reasoning/tool/status/text/source frames in
    canonical part order, then `terminal` with the stored attribution. No new
    DB writes.
    """
    attribution = ModelAttribution.model_validate(attribution_dict)
    items = sources_items or []
    tools = tool_parts or []

    async def _gen() -> AsyncIterator[ServerSentEvent]:
        yield encode_submitted(SubmittedEvent(message_id=str(user_message_id)))
        if reasoning_text:
            yield encode_reasoning_delta(ReasoningDeltaEvent(text=reasoning_text))
            yield encode_reasoning_done(ReasoningDoneEvent())
        for part in tools:
            ptype = part.get("type")
            if ptype == "tool_call":
                yield encode_tool_call(ToolCallEvent.model_validate(part))
            elif ptype == "tool_result":
                yield encode_tool_result(ToolResultEvent.model_validate(part))
        # Persisted `status` part (a completed search line) replays after the tool
        # transcript, matching the canonical persisted part order.
        if status_part is not None:
            yield encode_status(
                StatusEvent(
                    label=str(status_part.get("label", "")),
                    state="done",
                )
            )
        # Single answer_delta carrying the full final text (no mid-stream resume).
        yield encode_answer_delta(AnswerDeltaEvent(text=answer_text))
        # Persisted `sources` part replays after the answer, mirroring the live
        # order [text] [sources]. `SourceItem.model_validate` re-validates the
        # stored dicts so a malformed row can't emit a broken wire frame. An
        # ungrounded turn persists an empty `items` with `requested=True`, so we
        # replay the frame whenever EITHER items exist OR web search was
        # effective — never letting the ungrounded marker silently drop.
        if items or sources_requested:
            yield encode_sources(
                SourcesEvent(
                    items=[SourceItem.model_validate(it) for it in items],
                    requested=sources_requested,
                )
            )
        yield encode_terminal(
            TerminalEvent(
                message_id=str(assistant_message_id),
                attribution=attribution,
            )
        )
        # Yield to the event loop so the response actually streams in tests.
        await asyncio.sleep(0)

    return _eventsource_response(
        _gen(),
        media_type="text/event-stream",
    )

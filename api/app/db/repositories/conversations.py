"""Conversation repository.

M0 needs:
- list summaries for the sidebar (bootstrap)
- get a single conversation by id, scoped to the user
- get messages of a conversation (ordered by created_at)

M2 adds:
- `update_for_user` — patch title and/or pinned on an owned conversation.
- `delete_for_user` — delete an owned conversation. Cascades to messages/votes
  via the FK chain.
- `update_title` — single-field title write used by the title-autogen task
  (no user_id available at call site; the task already trusts that the
  conversation existed when the first terminal fired).
"""

from __future__ import annotations

import secrets
from collections.abc import Iterable, Sequence
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import String, delete, func, or_, select
from sqlalchemy import cast as sa_cast
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Message, Preferences, Project, Stream, Vote
from app.db.repositories import audit_events
from app.schemas.common import ModelTierId
from app.schemas.conversation import Conversation as ConversationSchema
from app.schemas.conversation import ConversationSearchResult, ConversationSummary
from app.schemas.message import ChatMessage, MessagePart
from app.schemas.share import PublicAttribution, PublicConversation, PublicMessage

# Share tokens are `secrets.token_urlsafe(_SHARE_TOKEN_BYTES)` — 24 random
# bytes => a 32-char URL-safe base64 string (~192 bits of entropy). Unguessable
# by brute force; the UNIQUE index on `conversation.share_token` is belt-and-
# braces against the astronomically unlikely collision.
_SHARE_TOKEN_BYTES = 24
_SEARCH_SNIPPET_RADIUS = 64
_SEARCH_PAGE_SIZE = 100


class _Unset:
    """Sentinel distinguishing "don't touch" from an explicit `None`.

    Needed for the nullable `retention_days` patch: `None` is a meaningful value
    ("clear the per-conversation override"), so a default of `None` could not
    also mean "leave the column unchanged."
    """


_UNSET = _Unset()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _coerce_tier(tier_id: str) -> ModelTierId:
    if tier_id not in ("fast", "smart", "pro", "auto"):
        # Repositories return wire schemas; fall back to "auto" if the DB row
        # somehow holds an unknown tier id (defensive — M1 inserts validate).
        return "auto"
    return cast(ModelTierId, tier_id)


def _escape_like(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _string_field(part: dict[str, object], key: str) -> str | None:
    value = part.get(key)
    return value if isinstance(value, str) else None


def _iter_source_strings(items: object) -> Iterable[str]:
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("title", "snippet", "url"):
            value = item.get(key)
            if isinstance(value, str):
                yield value


def _iter_searchable_part_strings(parts: object) -> Iterable[str]:
    if not isinstance(parts, list):
        return
    for part in parts:
        if not isinstance(part, dict):
            continue
        match part.get("type"):
            case "text" | "reasoning":
                text = _string_field(part, "text")
                if text is not None:
                    yield text
            case "status":
                label = _string_field(part, "label")
                if label is not None:
                    yield label
            case "sources":
                yield from _iter_source_strings(part.get("items"))
            case "attachment":
                name = _string_field(part, "name")
                if name is not None:
                    yield name
            case "tool_call":
                for key in ("label", "name"):
                    value = _string_field(part, key)
                    if value is not None:
                        yield value
            case "tool_result":
                for key in ("label", "name", "summary", "error"):
                    value = _string_field(part, key)
                    if value is not None:
                        yield value


def _snippet_for(text: str, query: str) -> str | None:
    needle = query.casefold()
    index = text.casefold().find(needle)
    if index < 0:
        return None

    start = max(0, index - _SEARCH_SNIPPET_RADIUS)
    end = min(len(text), index + len(query) + _SEARCH_SNIPPET_RADIUS)
    body = text[start:end].strip()
    prefix = "... " if start > 0 else ""
    suffix = " ..." if end < len(text) else ""
    return f"{prefix}{body}{suffix}"


def _message_snippet(parts: object, query: str) -> str | None:
    for text in _iter_searchable_part_strings(parts):
        snippet = _snippet_for(text, query)
        if snippet is not None:
            return snippet
    return None


async def list_summaries_for_user(
    db: AsyncSession, user_id: UUID
) -> list[ConversationSummary]:
    """Return sidebar summaries: pinned desc, then updated_at desc."""
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.pinned.desc(), Conversation.updated_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        ConversationSummary(
            id=str(row.id),
            title=row.title,
            updated_at=_iso(row.updated_at),
            is_temporary=False,
            pinned=row.pinned,
            retention_days=row.retention_days,
            project_id=str(row.project_id) if row.project_id is not None else None,
        )
        for row in rows
    ]


async def search_for_user(
    db: AsyncSession,
    user_id: UUID,
    *,
    query: str,
    limit: int = 25,
) -> list[ConversationSearchResult]:
    """Search owned conversation titles and message JSON text.

    The SQL predicate intentionally stays dialect-portable: title uses LIKE,
    and message parts are cast to text for both SQLite local/tests and
    Postgres prod. It is a broad candidate filter; final matching and the
    public limit happen after snippets are generated from user-visible fields.
    """
    stripped = query.strip()
    if not stripped or limit <= 0:
        return []

    pattern = f"%{_escape_like(stripped.casefold())}%"
    title_match = func.lower(Conversation.title).like(pattern, escape="\\")
    message_match = func.lower(sa_cast(Message.parts, String)).like(
        pattern, escape="\\"
    )
    results: list[ConversationSearchResult] = []
    offset = 0
    while len(results) < limit:
        stmt = (
            select(Conversation)
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .where(
                Conversation.user_id == user_id,
                or_(title_match, message_match),
            )
            .distinct()
            .order_by(Conversation.pinned.desc(), Conversation.updated_at.desc())
            .offset(offset)
            .limit(_SEARCH_PAGE_SIZE)
        )
        conversations = (await db.execute(stmt)).scalars().all()
        if not conversations:
            break

        offset += len(conversations)
        conversation_ids = [row.id for row in conversations]
        messages_stmt = (
            select(Message)
            .where(
                Message.conversation_id.in_(conversation_ids),
                func.lower(sa_cast(Message.parts, String)).like(pattern, escape="\\"),
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        matching_messages = (await db.execute(messages_stmt)).scalars().all()

        messages_by_conversation: dict[UUID, list[Message]] = {}
        for message in matching_messages:
            messages_by_conversation.setdefault(message.conversation_id, []).append(
                message
            )

        for row in conversations:
            title_snippet = _snippet_for(row.title, stripped)
            matched_message_id: str | None = None
            snippet = title_snippet

            if snippet is None:
                for message in messages_by_conversation.get(row.id, []):
                    message_snippet = _message_snippet(message.parts, stripped)
                    if message_snippet is None:
                        continue
                    snippet = message_snippet
                    matched_message_id = str(message.id)
                    break

            if snippet is None:
                continue

            results.append(
                ConversationSearchResult(
                    id=str(row.id),
                    title=row.title,
                    updated_at=_iso(row.updated_at),
                    is_temporary=False,
                    pinned=row.pinned,
                    retention_days=row.retention_days,
                    match_snippet=snippet,
                    matched_message_id=matched_message_id,
                )
            )
            if len(results) >= limit:
                break

    return results


async def create_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    selected_tier_id: ModelTierId,
    project_id: UUID | None = None,
) -> Conversation:
    """Persist a new conversation. Returns the row with id/timestamps set.

    `selected_tier_id` is passed in already-resolved by the route — when filing
    under a Project with a `default_tier_id`, the route pre-seeds it from the
    project's create-time default (a labeled default, not a send-path lock). The
    repo does not load the project itself; it just persists the membership +
    pre-seeded tier.
    """
    convo = Conversation(
        user_id=user_id,
        title="New chat",
        selected_tier_id=selected_tier_id,
        pinned=False,
        project_id=project_id,
    )
    db.add(convo)
    await db.flush()
    await db.refresh(convo)
    return convo


async def branch_for_user(
    db: AsyncSession,
    *,
    source_conversation_id: UUID,
    user_id: UUID,
    through_message_id: UUID,
) -> ConversationSchema | None:
    """Copy an owned conversation through one message into a new conversation.

    Branching is a copy operation, not a billing event. The visible message
    content and attribution are preserved for context, but copied assistant
    rows intentionally get ``cost_usd=NULL`` and no usage_rollup writes happen
    here, so historical turns are not double-counted against future budget
    checks.
    """
    source = await owned_by(db, source_conversation_id, user_id)
    if source is None:
        return None

    messages_stmt = (
        select(Message)
        .where(Message.conversation_id == source.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    source_messages = (await db.execute(messages_stmt)).scalars().all()

    copied_source_messages: list[Message] = []
    for message in source_messages:
        copied_source_messages.append(message)
        if message.id == through_message_id:
            break
    else:
        return None

    now = datetime.now(UTC)
    branch = Conversation(
        user_id=user_id,
        title=source.title,
        selected_tier_id=source.selected_tier_id,
        pinned=False,
        # A branch inherits the source's Project membership (D20) so it stays
        # grouped alongside its origin in the sidebar.
        project_id=source.project_id,
        created_at=now,
        updated_at=now,
    )
    db.add(branch)
    await db.flush()

    id_map: dict[UUID, UUID] = {}
    for index, source_message in enumerate(copied_source_messages):
        new_id = uuid4()
        id_map[source_message.id] = new_id
        responds_to = source_message.responds_to_message_id
        copied = Message(
            id=new_id,
            conversation_id=branch.id,
            client_message_id=None,
            role=source_message.role,
            parts=deepcopy(source_message.parts),
            status=source_message.status,
            attribution=deepcopy(source_message.attribution),
            cost_usd=None,
            responds_to_message_id=id_map.get(responds_to) if responds_to else None,
            created_at=now + timedelta(microseconds=index + 1),
        )
        db.add(copied)

    await db.flush()
    return await get_for_user(db, branch.id, user_id)


async def owned_by(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> Conversation | None:
    """Return the ORM row if owned by the user, else None.

    Lighter than `get_for_user` (no messages fetch). Used by routes that just
    need to assert ownership.
    """
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None or row.user_id != user_id:
        return None
    return row


async def get_for_user(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> ConversationSchema | None:
    """Return the full conversation if owned by the user, else None.

    Ownership-not-found is indistinguishable from missing (callers raise 404).
    """
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None or row.user_id != user_id:
        return None

    messages_stmt = (
        select(Message)
        .where(Message.conversation_id == row.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    message_rows = (await db.execute(messages_stmt)).scalars().all()

    messages: list[ChatMessage] = []
    for m in message_rows:
        # parts and attribution come back as JSON dicts; let Pydantic validate.
        parts_list = cast(list[MessagePart], m.parts) if m.parts is not None else []
        chat_message = ChatMessage.model_validate(
            {
                "id": str(m.id),
                "role": m.role,
                "parts": parts_list,
                "created_at": _iso(m.created_at),
                "status": m.status,
                "attribution": m.attribution,
            }
        )
        messages.append(chat_message)

    return ConversationSchema(
        id=str(row.id),
        title=row.title,
        messages=messages,
        selected_tier_id=_coerce_tier(row.selected_tier_id),
        is_temporary=False,
        retention_days=row.retention_days,
        project_id=str(row.project_id) if row.project_id is not None else None,
    )


async def update_for_user(
    db: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
    *,
    title: str | None = None,
    pinned: bool | None = None,
    retention_days: int | None | _Unset = _UNSET,
    project_id: UUID | None | _Unset = _UNSET,
) -> Conversation | None:
    """Update the owned conversation's title/pinned/retention/project. Returns the row.

    `title` / `pinned` use `None` as "don't touch". `retention_days` and
    `project_id` are three-valued — their `None` means "CLEAR" (inherit the
    global retention / un-file from the Project), so they use the `_UNSET`
    sentinel for "don't touch" instead. Returns the refreshed ORM row, or None
    if the row isn't owned/doesn't exist. Bumps `updated_at` so the sidebar's
    pinned/updated ordering reflects the change.
    """
    row = await owned_by(db, conversation_id, user_id)
    if row is None:
        return None
    if title is not None:
        row.title = title
    if pinned is not None:
        row.pinned = pinned
    if not isinstance(retention_days, _Unset):
        row.retention_days = retention_days
    if not isinstance(project_id, _Unset):
        row.project_id = project_id
    # Touch updated_at — the column has a server_default but no onupdate hook,
    # so we set it explicitly. Naive datetime is fine for SQLite tests; Postgres
    # accepts tz-aware values via TIMESTAMP(timezone=True).
    row.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(row)
    return row


async def touch_updated_at(
    db: AsyncSession,
    conversation_id: UUID,
) -> None:
    """Bump `updated_at` to now so the conversation rises in the sidebar.

    Called when a NEW turn is accepted (normal send, regenerate, edit) so the
    sidebar's `pinned desc, updated_at desc` ordering reflects activity, not
    just creation order. The column has a `server_default` but no `onupdate`
    hook, so we set it explicitly. Flush only — the caller commits in the same
    transaction that persists the turn's user message (atomic with the turn).

    Silent no-op if the row is gone (mirrors `update_title`). Distinct from
    `update_title`, which deliberately does NOT bump so title autogen alone
    can't reorder the sidebar.
    """
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return
    row.updated_at = datetime.now(UTC)
    await db.flush()


async def update_title(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    title: str,
) -> None:
    """Set `conversation.title`. Silent no-op if the row is gone.

    Used by the title-autogen detached task on the first terminal. The
    caller owns its own session and commit; we only mutate. Does not bump
    `updated_at` — title autogen is an implicit side effect of the same
    turn that already updated the row's children, so keeping the sidebar
    ordering stable is preferable.
    """
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return
    row.title = title
    await db.flush()


async def delete_for_user(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> bool:
    """Delete the owned conversation. Returns True if a row was deleted.

    Cascades to `message`; `vote` cascades transitively via the FK chain on
    Postgres. SQLite (test) doesn't enforce FK cascades by default (no
    `PRAGMA foreign_keys=ON`), so we issue explicit deletes for `vote` and
    `message` first. The Postgres path is unchanged in semantics — the
    explicit deletes are idempotent there too.
    """
    row = await owned_by(db, conversation_id, user_id)
    if row is None:
        return False
    # Manual cascade for cross-dialect safety. On Postgres the FK ON DELETE
    # CASCADE also fires; the explicit deletes here are idempotent.
    # vote -> message -> conversation deletion order matches the FK chain.
    msg_id_stmt = select(Message.id).where(Message.conversation_id == conversation_id)
    msg_ids = (await db.execute(msg_id_stmt)).scalars().all()
    if msg_ids:
        await db.execute(delete(Vote).where(Vote.message_id.in_(msg_ids)))
    await db.execute(delete(Stream).where(Stream.conversation_id == conversation_id))
    await db.execute(delete(Message).where(Message.conversation_id == conversation_id))
    await db.execute(delete(Conversation).where(Conversation.id == conversation_id))
    await db.flush()
    return True


def _effective_retention_days(
    conversation_retention_days: int | None,
    project_retention_days: int | None,
    global_retention_days: int | None,
) -> int | None:
    """Resolve a conversation's effective retention window in days (D31/D20).

    Precedence is conv > project > global: the per-conversation override wins
    when set; otherwise the conversation's Project retention (D20) applies; else
    the user's global `preferences.retention_days`. `None` from ALL THREE means
    "retain forever" — the conversation never expires.
    """
    if conversation_retention_days is not None:
        return conversation_retention_days
    if project_retention_days is not None:
        return project_retention_days
    return global_retention_days


def _is_expired(
    *,
    updated_at: datetime,
    conversation_retention_days: int | None,
    project_retention_days: int | None,
    global_retention_days: int | None,
    now: datetime,
) -> bool:
    """True iff a conversation is past its effective retention window.

    Expiry is keyed on `updated_at` (mirroring the rest of retention): an old
    conversation that was recently renamed, pinned, or continued is still active
    data. The cutoff is computed in Python (a plain `timedelta` subtraction) so
    no dialect-specific date arithmetic is needed — the same approach the
    orphan-stream reaper uses.

    `updated_at` may be naive (SQLite test rows) or tz-aware (Postgres). Compare
    against a `now` of the matching awareness so the subtraction never raises a
    naive/aware mismatch.
    """
    days = _effective_retention_days(
        conversation_retention_days, project_retention_days, global_retention_days
    )
    if days is None:
        return False
    reference = now if updated_at.tzinfo is not None else now.replace(tzinfo=None)
    return updated_at < reference - timedelta(days=days)


async def _purge_conversation_ids(
    db: AsyncSession,
    conversation_ids: Sequence[UUID],
) -> None:
    """Manual cascade-delete a set of conversations and their dependents.

    SQLite (tests) does not enforce FK cascades by default, so dependent rows
    are removed explicitly in FK order (vote -> stream/message -> conversation).
    On Postgres the ON DELETE CASCADE also fires; the explicit deletes are
    idempotent there too.
    """
    if not conversation_ids:
        return
    msg_id_stmt = select(Message.id).where(
        Message.conversation_id.in_(conversation_ids)
    )
    msg_ids = (await db.execute(msg_id_stmt)).scalars().all()
    if msg_ids:
        await db.execute(delete(Vote).where(Vote.message_id.in_(msg_ids)))
    await db.execute(delete(Stream).where(Stream.conversation_id.in_(conversation_ids)))
    await db.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
    await db.execute(delete(Conversation).where(Conversation.id.in_(conversation_ids)))
    await db.flush()


async def delete_older_than_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    global_retention_days: int | None,
) -> int:
    """Purge a user's expired conversations honoring the per-conversation override.

    Each conversation expires once `now - updated_at` exceeds its effective
    retention window — its own `retention_days` if set, else the caller's global
    `preferences.retention_days` (D31). When BOTH are NULL the conversation is
    retained forever. This is the opportunistic per-user purge invoked on read
    paths (bootstrap, history reads, export); the scheduled
    `delete_expired_all_users` sweep enforces the same rule across every user.

    A single user-scoped candidate fetch (id, updated_at, retention_days, the
    conversation's Project retention via a LEFT JOIN), then the expiry decision
    in Python — no dialect-specific date math. The Project is the conversation's
    own (`conversation.project_id == project.id`); because Project assignment is
    owner-scoped, `project.user_id` always equals this user, so the middle
    retention tier can never be borrowed from another user's Project. Emits the
    user-facing `retention.purge` audit event only when something was actually
    deleted, so the common no-op read path stays silent.
    """
    now = datetime.now(UTC)
    stmt = (
        select(
            Conversation.id,
            Conversation.updated_at,
            Conversation.retention_days,
            Project.retention_days.label("project_retention_days"),
        )
        .outerjoin(Project, Project.id == Conversation.project_id)
        .where(Conversation.user_id == user_id)
    )
    rows = (await db.execute(stmt)).all()
    expired_ids = [
        row.id
        for row in rows
        if _is_expired(
            updated_at=row.updated_at,
            conversation_retention_days=row.retention_days,
            project_retention_days=row.project_retention_days,
            global_retention_days=global_retention_days,
            now=now,
        )
    ]
    if not expired_ids:
        return 0

    await _purge_conversation_ids(db, expired_ids)
    # Record the purge on the user-facing activity log — only when something
    # was actually deleted, so the common no-op read path stays silent.
    await audit_events.record(
        db,
        user_id=user_id,
        event_type="retention.purge",
        details={"purgedConversations": len(expired_ids)},
    )
    return len(expired_ids)


async def delete_expired_all_users(db: AsyncSession) -> int:
    """Scheduled sweep: purge expired conversations across ALL users (D31).

    Each conversation expires by its effective retention window — its own
    `retention_days` override if set, else its Project's `retention_days` (D20),
    else the owning user's global `preferences.retention_days` (a missing
    preferences row => no global window). Conversations with no finite window
    from any source are retained forever.

    Candidate pre-filter (SQL): only rows that have SOME finite window can
    possibly expire, i.e. the conversation override is set OR its Project
    retention is set OR the owner's global preference is set. A LEFT JOIN to
    `preferences` exposes the per-owner global in the same scan; a LEFT JOIN to
    `project` (on `conversation.project_id == project.id`) exposes the
    conversation's own Project retention. CROSS-USER SAFETY: the project join is
    on the conversation's `project_id`, and Project assignment is owner-scoped
    (`project.user_id == conversation.user_id` always holds), so one user's
    Project can never set a retention window on another user's conversation — the
    middle tier is strictly the conversation's own owner's Project. The expiry
    decision is finished in Python (plain `timedelta` subtraction — no
    dialect-specific date arithmetic). The purge is grouped per user so each
    owner gets exactly one `retention.purge` audit event carrying their own
    deleted count.

    Returns the total number of conversations purged across all users. Owns no
    session of its own — the caller (the scheduled-purge loop) provides one and
    commits.
    """
    now = datetime.now(UTC)
    stmt = (
        select(
            Conversation.id,
            Conversation.user_id,
            Conversation.updated_at,
            Conversation.retention_days,
            Project.retention_days.label("project_retention_days"),
            Preferences.retention_days.label("global_retention_days"),
        )
        .outerjoin(Preferences, Preferences.user_id == Conversation.user_id)
        .outerjoin(Project, Project.id == Conversation.project_id)
        .where(
            or_(
                Conversation.retention_days.is_not(None),
                Project.retention_days.is_not(None),
                Preferences.retention_days.is_not(None),
            )
        )
    )
    rows = (await db.execute(stmt)).all()

    expired_by_user: dict[UUID, list[UUID]] = {}
    for row in rows:
        if _is_expired(
            updated_at=row.updated_at,
            conversation_retention_days=row.retention_days,
            project_retention_days=row.project_retention_days,
            global_retention_days=row.global_retention_days,
            now=now,
        ):
            expired_by_user.setdefault(row.user_id, []).append(row.id)

    if not expired_by_user:
        return 0

    total = 0
    for owner_id, conversation_ids in expired_by_user.items():
        await _purge_conversation_ids(db, conversation_ids)
        await audit_events.record(
            db,
            user_id=owner_id,
            event_type="retention.purge",
            details={"purgedConversations": len(conversation_ids)},
        )
        total += len(conversation_ids)
    return total


async def mint_share_token(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> str | None:
    """Mint (or return the existing) share token for an owned conversation.

    Idempotent: re-minting on an already-shared conversation returns the SAME
    token (no rotation) so existing links keep working. Returns None if the
    conversation isn't owned by the user (the route maps that to a 404 so the
    existence of the conversation never leaks).
    """
    row = await owned_by(db, conversation_id, user_id)
    if row is None:
        return None
    if row.share_token is None:
        row.share_token = secrets.token_urlsafe(_SHARE_TOKEN_BYTES)
        await db.flush()
    return row.share_token


async def revoke_share_token(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> bool:
    """Clear the share token on an owned conversation. Idempotent.

    Returns True if the conversation is owned (whether or not it was shared),
    False if it isn't owned / doesn't exist. Revoking an already-unshared
    conversation is a no-op that still returns True. Once cleared, the public
    GET on the old token 404s.
    """
    row = await owned_by(db, conversation_id, user_id)
    if row is None:
        return False
    if row.share_token is not None:
        row.share_token = None
        await db.flush()
    return True


async def get_public_by_share_token(
    db: AsyncSession, share_token: str
) -> PublicConversation | None:
    """Return the COST-STRIPPED public view for a share token, or None.

    Public-by-link: NO ownership / auth check. Looks the conversation up by its
    unique `share_token` and builds a `PublicConversation` that structurally
    cannot carry per-message cost (it uses `PublicMessage` / `PublicAttribution`
    which have no cost fields). Unknown / revoked token => None (the route 404s,
    never leaking which tokens once existed).
    """
    stmt = select(Conversation).where(Conversation.share_token == share_token)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None

    messages_stmt = (
        select(Message)
        .where(Message.conversation_id == row.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    message_rows = (await db.execute(messages_stmt)).scalars().all()

    messages: list[PublicMessage] = []
    for m in message_rows:
        parts_list = cast(list[MessagePart], m.parts) if m.parts is not None else []
        # Re-project attribution through PublicAttribution so ONLY model
        # identity survives — cost_usd / costConfidence / breakdown are dropped
        # because the public schema has no field to receive them.
        public_attribution: PublicAttribution | None = None
        if m.attribution is not None:
            attribution_dict = cast(dict[str, object], m.attribution)
            public_attribution = PublicAttribution.model_validate(attribution_dict)
        messages.append(
            PublicMessage.model_validate(
                {
                    "id": str(m.id),
                    "role": m.role,
                    "parts": parts_list,
                    "created_at": _iso(m.created_at),
                    "attribution": public_attribution,
                }
            )
        )

    return PublicConversation(
        id=str(row.id),
        title=row.title,
        messages=messages,
    )

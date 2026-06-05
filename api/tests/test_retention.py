"""Per-conversation retention + scheduled purge tests (D31).

Covers the durable per-conversation retention override and the scheduled purge:

- PATCH /api/conversations/:id sets / clears the per-conversation `retentionDays`
  override and echoes it on the wire (and on the sidebar summary).
- `delete_expired_all_users` (the scheduled sweep) deletes expired conversations
  across users, honoring the per-conversation override OVER the user's global
  retention, and retaining forever when BOTH are null.
- A `retention.purge` audit event is emitted (and only when something is
  deleted).
- `purge_once` / `run_purge_loop`: the best-effort wrappers used by the lifespan
  seams sweep then cancel cleanly.

Like the rest of the suite the schema is built from the ORM models
(`conftest.py` create_all), so this exercises the new `conversation.retention_days`
column directly.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditEvent, Conversation, Preferences, Project, User
from app.db.repositories import conversations as conversations_repo
from app.maintenance.purge import purge_once, run_purge_loop

pytestmark = pytest.mark.asyncio


# Helpers ----------------------------------------------------------------------


async def _seed_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    global_retention_days: int | None = None,
) -> UUID:
    async with session_factory() as session:
        user = User(is_anonymous=True, name="Guest")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        if global_retention_days is not None:
            session.add(
                Preferences(
                    user_id=user.id,
                    default_tier_id="smart",
                    retention_days=global_retention_days,
                )
            )
            await session.commit()
        return user.id


async def _seed_conversation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    updated_age: timedelta,
    retention_days: int | None = None,
    project_id: UUID | None = None,
    title: str = "chat",
) -> UUID:
    async with session_factory() as session:
        convo = Conversation(
            user_id=user_id,
            title=title,
            selected_tier_id="smart",
            pinned=False,
            retention_days=retention_days,
            project_id=project_id,
            updated_at=datetime.now(UTC) - updated_age,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return convo.id


async def _seed_project(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    retention_days: int | None = None,
    name: str = "project",
) -> UUID:
    async with session_factory() as session:
        project = Project(
            user_id=user_id,
            name=name,
            retention_days=retention_days,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project.id


async def _conversation_ids(
    session_factory: async_sessionmaker[AsyncSession],
) -> set[UUID]:
    async with session_factory() as session:
        rows = (await session.execute(select(Conversation.id))).scalars().all()
        return set(rows)


async def _purge_audit_counts(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: UUID,
) -> list[int]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.user_id == user_id,
                    AuditEvent.event_type == "retention.purge",
                )
            )
        ).scalars().all()
        return [int(r.details["purgedConversations"]) for r in rows]


# PATCH set / clear the per-conversation override --------------------------------


async def test_patch_sets_per_conversation_retention(client: AsyncClient) -> None:
    """PATCH with `retentionDays` sets the override and echoes it back; the
    sidebar summary surfaces it on the next bootstrap."""
    await client.get("/api/bootstrap")
    created = await client.post(
        "/api/conversations", json={"selectedTierId": "smart", "isTemporary": False}
    )
    convo_id = created.json()["id"]

    resp = await client.patch(
        f"/api/conversations/{convo_id}", json={"retentionDays": 30}
    )
    assert resp.status_code == 200
    assert resp.json()["retentionDays"] == 30

    # GET round-trips the value.
    fetched = await client.get(f"/api/conversations/{convo_id}")
    assert fetched.json()["retentionDays"] == 30

    # Sidebar summary carries it too.
    boot = await client.get("/api/bootstrap")
    summary = next(c for c in boot.json()["conversations"] if c["id"] == convo_id)
    assert summary["retentionDays"] == 30


async def test_patch_clears_per_conversation_retention(client: AsyncClient) -> None:
    """An explicit `retentionDays: null` CLEARS the override (not a no-op)."""
    await client.get("/api/bootstrap")
    created = await client.post(
        "/api/conversations", json={"selectedTierId": "smart", "isTemporary": False}
    )
    convo_id = created.json()["id"]

    assert (
        await client.patch(
            f"/api/conversations/{convo_id}", json={"retentionDays": 90}
        )
    ).json()["retentionDays"] == 90

    cleared = await client.patch(
        f"/api/conversations/{convo_id}", json={"retentionDays": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["retentionDays"] is None

    fetched = await client.get(f"/api/conversations/{convo_id}")
    assert fetched.json()["retentionDays"] is None


async def test_patch_empty_body_still_rejected(client: AsyncClient) -> None:
    """An all-null patch with NO retention field set is still a 400 no-op."""
    await client.get("/api/bootstrap")
    created = await client.post(
        "/api/conversations", json={"selectedTierId": "smart", "isTemporary": False}
    )
    convo_id = created.json()["id"]
    resp = await client.patch(
        f"/api/conversations/{convo_id}", json={"title": None, "pinned": None}
    )
    assert resp.status_code == 400


async def test_patch_rejects_non_positive_retention(client: AsyncClient) -> None:
    """A zero / negative retention is rejected by the schema bound."""
    await client.get("/api/bootstrap")
    created = await client.post(
        "/api/conversations", json={"selectedTierId": "smart", "isTemporary": False}
    )
    convo_id = created.json()["id"]
    resp = await client.patch(
        f"/api/conversations/{convo_id}", json={"retentionDays": 0}
    )
    assert resp.status_code == 400


# Scheduled sweep: delete_expired_all_users -------------------------------------


async def test_sweep_deletes_expired_by_global_retention(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A conversation past the owner's GLOBAL window (no override) is purged;
    a fresh one is kept."""
    user_id = await _seed_user(session_factory, global_retention_days=30)
    old_id = await _seed_conversation(
        session_factory, user_id=user_id, updated_age=timedelta(days=40)
    )
    fresh_id = await _seed_conversation(
        session_factory, user_id=user_id, updated_age=timedelta(days=5)
    )

    async with session_factory() as session:
        purged = await conversations_repo.delete_expired_all_users(session)
        await session.commit()

    assert purged == 1
    assert await _conversation_ids(session_factory) == {fresh_id}
    assert old_id not in await _conversation_ids(session_factory)


async def test_override_keeps_conversation_longer_than_global(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A per-conversation override LONGER than the global window spares a
    conversation the global window would have purged (override wins)."""
    user_id = await _seed_user(session_factory, global_retention_days=30)
    # 40 days old: expired under the 30-day global, but a 90-day override keeps it.
    kept_id = await _seed_conversation(
        session_factory,
        user_id=user_id,
        updated_age=timedelta(days=40),
        retention_days=90,
    )
    # No override: the 30-day global purges it.
    purged_id = await _seed_conversation(
        session_factory, user_id=user_id, updated_age=timedelta(days=40)
    )

    async with session_factory() as session:
        purged = await conversations_repo.delete_expired_all_users(session)
        await session.commit()

    assert purged == 1
    assert await _conversation_ids(session_factory) == {kept_id}
    _ = purged_id


async def test_override_expires_conversation_without_global(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A per-conversation override expires a conversation even when the owner has
    NO global retention (override is the only finite window)."""
    user_id = await _seed_user(session_factory, global_retention_days=None)
    expired_id = await _seed_conversation(
        session_factory,
        user_id=user_id,
        updated_age=timedelta(days=10),
        retention_days=7,
    )
    # Same owner, no override + no global => retained forever.
    kept_id = await _seed_conversation(
        session_factory, user_id=user_id, updated_age=timedelta(days=10)
    )

    async with session_factory() as session:
        purged = await conversations_repo.delete_expired_all_users(session)
        await session.commit()

    assert purged == 1
    assert await _conversation_ids(session_factory) == {kept_id}
    _ = expired_id


async def test_never_expire_when_both_null(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """No override and no global retention => the conversation is retained
    forever, no matter how old."""
    user_id = await _seed_user(session_factory, global_retention_days=None)
    ancient_id = await _seed_conversation(
        session_factory, user_id=user_id, updated_age=timedelta(days=3650)
    )

    async with session_factory() as session:
        purged = await conversations_repo.delete_expired_all_users(session)
        await session.commit()

    assert purged == 0
    assert await _conversation_ids(session_factory) == {ancient_id}


async def test_sweep_spans_multiple_users(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The sweep crosses ALL users and emits one purge audit row per owner
    carrying that owner's own deleted count."""
    user_a = await _seed_user(session_factory, global_retention_days=30)
    user_b = await _seed_user(session_factory, global_retention_days=None)

    await _seed_conversation(
        session_factory, user_id=user_a, updated_age=timedelta(days=40)
    )
    await _seed_conversation(
        session_factory, user_id=user_a, updated_age=timedelta(days=50)
    )
    await _seed_conversation(
        session_factory,
        user_id=user_b,
        updated_age=timedelta(days=40),
        retention_days=10,
    )

    async with session_factory() as session:
        purged = await conversations_repo.delete_expired_all_users(session)
        await session.commit()

    assert purged == 3
    assert await _conversation_ids(session_factory) == set()
    # One audit row per owner, with that owner's own count.
    assert sorted(await _purge_audit_counts(session_factory, user_a)) == [2]
    assert sorted(await _purge_audit_counts(session_factory, user_b)) == [1]


# Project-tier retention precedence (D20): conv > project > global ------------


async def test_project_retention_expires_without_global(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A Project's retention expires a conversation even when the owner has NO
    global retention and the conversation has no per-conversation override."""
    user_id = await _seed_user(session_factory, global_retention_days=None)
    project_id = await _seed_project(
        session_factory, user_id=user_id, retention_days=7
    )
    # 10 days old, filed under the 7-day project => expired by the project tier.
    expired_id = await _seed_conversation(
        session_factory,
        user_id=user_id,
        updated_age=timedelta(days=10),
        project_id=project_id,
    )
    # Same owner, no project + no global => retained forever.
    kept_id = await _seed_conversation(
        session_factory, user_id=user_id, updated_age=timedelta(days=10)
    )

    async with session_factory() as session:
        purged = await conversations_repo.delete_expired_all_users(session)
        await session.commit()

    assert purged == 1
    assert await _conversation_ids(session_factory) == {kept_id}
    _ = expired_id


async def test_conversation_override_beats_project_retention(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The per-conversation override wins OVER the project tier (conv > project):
    a longer override spares a conversation the project window would purge."""
    user_id = await _seed_user(session_factory, global_retention_days=None)
    project_id = await _seed_project(
        session_factory, user_id=user_id, retention_days=7
    )
    # 10 days old, project says 7 (would purge) but a 90-day override keeps it.
    kept_id = await _seed_conversation(
        session_factory,
        user_id=user_id,
        updated_age=timedelta(days=10),
        retention_days=90,
        project_id=project_id,
    )
    # Same project, no override => the 7-day project window purges it.
    purged_id = await _seed_conversation(
        session_factory,
        user_id=user_id,
        updated_age=timedelta(days=10),
        project_id=project_id,
    )

    async with session_factory() as session:
        purged = await conversations_repo.delete_expired_all_users(session)
        await session.commit()

    assert purged == 1
    assert await _conversation_ids(session_factory) == {kept_id}
    _ = purged_id


async def test_project_retention_beats_global(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The project tier wins OVER the global (project > global): a longer project
    window spares a conversation the global window would purge."""
    user_id = await _seed_user(session_factory, global_retention_days=30)
    project_id = await _seed_project(
        session_factory, user_id=user_id, retention_days=90
    )
    # 40 days old: expired under the 30-day global, but the 90-day project keeps it.
    kept_id = await _seed_conversation(
        session_factory,
        user_id=user_id,
        updated_age=timedelta(days=40),
        project_id=project_id,
    )
    # No project: the 30-day global purges it.
    purged_id = await _seed_conversation(
        session_factory, user_id=user_id, updated_age=timedelta(days=40)
    )

    async with session_factory() as session:
        purged = await conversations_repo.delete_expired_all_users(session)
        await session.commit()

    assert purged == 1
    assert await _conversation_ids(session_factory) == {kept_id}
    _ = purged_id


async def test_per_user_purge_honors_project_retention(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The opportunistic per-user purge uses the project tier too (D20)."""
    user_id = await _seed_user(session_factory)
    project_id = await _seed_project(
        session_factory, user_id=user_id, retention_days=7
    )
    purged_id = await _seed_conversation(
        session_factory,
        user_id=user_id,
        updated_age=timedelta(days=10),
        project_id=project_id,
    )
    kept_id = await _seed_conversation(
        session_factory, user_id=user_id, updated_age=timedelta(days=10)
    )

    async with session_factory() as session:
        count = await conversations_repo.delete_older_than_for_user(
            session, user_id=user_id, global_retention_days=None
        )
        await session.commit()

    assert count == 1
    assert await _conversation_ids(session_factory) == {kept_id}
    _ = purged_id


async def test_fleet_sweep_project_retention_is_cross_user_isolated(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """CROSS-USER SAFETY: the fleet-wide sweep's project LEFT JOIN must never let
    one user's Project retention affect another user's conversation.

    User A owns a SHORT-retention (7d) Project. User B owns a conversation that
    is NOT filed under any project and has no global/own retention. Even though
    A's aggressive 7-day window exists in the same sweep, B's conversation (older
    than 7 days) must be RETAINED — its `project_id` is NULL so the join yields
    no project retention for it, and A's project can never bleed across.
    """
    user_a = await _seed_user(session_factory, global_retention_days=None)
    user_b = await _seed_user(session_factory, global_retention_days=None)

    project_a = await _seed_project(
        session_factory, user_id=user_a, retention_days=7
    )
    # A's conversation under A's 7-day project, 30 days old => expired.
    a_expired = await _seed_conversation(
        session_factory,
        user_id=user_a,
        updated_age=timedelta(days=30),
        project_id=project_a,
    )
    # B's conversation: unfiled, no retention anywhere, 30 days old => must KEEP.
    b_kept = await _seed_conversation(
        session_factory, user_id=user_b, updated_age=timedelta(days=30)
    )

    async with session_factory() as session:
        purged = await conversations_repo.delete_expired_all_users(session)
        await session.commit()

    # Only A's conversation is purged; B's survives untouched by A's project.
    assert purged == 1
    assert await _conversation_ids(session_factory) == {b_kept}
    _ = a_expired


async def test_fleet_sweep_uses_each_conversations_own_project_retention(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """CROSS-USER SAFETY (stronger): when BOTH users own projects, the fleet-wide
    sweep must resolve each conversation's retention from ITS OWN project — never
    a different user's. User A owns a SHORT (7d) project; User B owns a LONG
    (3650d) project; both conversations are 30 days old. A's must purge (its own
    7d window expired) and B's must survive (its own 3650d window), proving the
    LEFT JOIN keys strictly on `conversation.project_id == project.id` and can
    never borrow A's short window for B's row.
    """
    user_a = await _seed_user(session_factory, global_retention_days=None)
    user_b = await _seed_user(session_factory, global_retention_days=None)

    project_a = await _seed_project(
        session_factory, user_id=user_a, retention_days=7
    )
    project_b = await _seed_project(
        session_factory, user_id=user_b, retention_days=3650
    )
    # A's conversation under A's 7-day project, 30 days old => expired.
    a_expired = await _seed_conversation(
        session_factory,
        user_id=user_a,
        updated_age=timedelta(days=30),
        project_id=project_a,
    )
    # B's conversation under B's 3650-day project, 30 days old => must KEEP.
    b_kept = await _seed_conversation(
        session_factory,
        user_id=user_b,
        updated_age=timedelta(days=30),
        project_id=project_b,
    )

    async with session_factory() as session:
        purged = await conversations_repo.delete_expired_all_users(session)
        await session.commit()

    # A's expired under its own short window; B's retained under its own long one.
    assert purged == 1
    assert await _conversation_ids(session_factory) == {b_kept}
    _ = a_expired


async def test_sweep_emits_no_audit_when_nothing_purged(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A no-op sweep records NO `retention.purge` audit event."""
    user_id = await _seed_user(session_factory, global_retention_days=30)
    await _seed_conversation(
        session_factory, user_id=user_id, updated_age=timedelta(days=5)
    )

    async with session_factory() as session:
        purged = await conversations_repo.delete_expired_all_users(session)
        await session.commit()

    assert purged == 0
    assert await _purge_audit_counts(session_factory, user_id) == []


# Opportunistic per-user purge honors the override ------------------------------


async def test_per_user_purge_honors_override(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The opportunistic per-user purge uses the override OVER the passed global
    window — both directions (longer keeps, shorter purges)."""
    user_id = await _seed_user(session_factory)
    kept_id = await _seed_conversation(
        session_factory,
        user_id=user_id,
        updated_age=timedelta(days=40),
        retention_days=90,
    )
    purged_id = await _seed_conversation(
        session_factory,
        user_id=user_id,
        updated_age=timedelta(days=10),
        retention_days=7,
    )

    async with session_factory() as session:
        count = await conversations_repo.delete_older_than_for_user(
            session, user_id=user_id, global_retention_days=30
        )
        await session.commit()

    assert count == 1
    assert await _conversation_ids(session_factory) == {kept_id}
    _ = purged_id


# purge_once / loop wrappers ----------------------------------------------------


async def test_purge_once_commits_and_returns_count(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`purge_once` owns its own session, commits, and returns the purged count."""
    user_id = await _seed_user(session_factory, global_retention_days=30)
    await _seed_conversation(
        session_factory, user_id=user_id, updated_age=timedelta(days=40)
    )

    purged = await purge_once(session_factory)

    assert purged == 1
    # Durable: a fresh session sees the deletion.
    assert await _conversation_ids(session_factory) == set()


async def test_run_purge_loop_sweeps_then_cancels_cleanly(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The loop sweeps once immediately, then parks on the interval sleep;
    cancelling it (lifespan shutdown) propagates `CancelledError` cleanly."""
    user_id = await _seed_user(session_factory, global_retention_days=30)
    await _seed_conversation(
        session_factory, user_id=user_id, updated_age=timedelta(days=40)
    )

    task = asyncio.create_task(
        run_purge_loop(session_factory, interval_seconds=3600.0)
    )
    # Yield until the first immediate sweep has committed.
    for _ in range(50):
        if await _conversation_ids(session_factory) == set():
            break
        await asyncio.sleep(0.01)

    assert await _conversation_ids(session_factory) == set()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

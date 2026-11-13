"""Unit tests for repository-layer CRUD (projects, prompt_templates, tags, memory_facts).

These tests exercise the data-access functions directly against SQLite to cover
the uncovered branches: update, delete, ownership scoping, and sentinel-based
three-valued patch semantics.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    Conversation,
    ConversationTag,
    Project,
    Tag,
    User,
)
from app.db.repositories import memory_facts, projects, prompt_templates, tags

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_user(db: AsyncSession, *, name: str = "Tester") -> User:
    user = User(id=uuid4(), name=name, is_anonymous=False, plan_label="Free")
    db.add(user)
    await db.flush()
    return user


# ===========================================================================
# projects
# ===========================================================================


async def test_projects_list_for_user_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user = await _make_user(db)
        result = await projects.list_for_user(db, user.id)
        assert result == []


async def test_projects_add_and_get(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user = await _make_user(db)
        p = await projects.add(
            db,
            user_id=user.id,
            name="My Project",
            custom_instructions="Be helpful",
            default_tier_id="smart",
            retention_days=7,
            per_conversation_budget_usd=2.5,
        )
        assert p.name == "My Project"
        assert p.custom_instructions == "Be helpful"
        assert p.default_tier_id == "smart"
        assert p.retention_days == 7
        assert p.per_conversation_budget_usd == 2.5

        fetched = await projects.get_for_user(db, project_id=p.id, user_id=user.id)
        assert fetched is not None
        assert fetched.id == p.id


async def test_projects_get_for_user_wrong_owner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user_a = await _make_user(db, name="A")
        user_b = await _make_user(db, name="B")
        p = await projects.add(db, user_id=user_a.id, name="Private")
        assert await projects.get_for_user(db, project_id=p.id, user_id=user_b.id) is None


async def test_projects_update_partial(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Three-valued PATCH: omission leaves unchanged, explicit None clears."""
    async with session_factory() as db:
        user = await _make_user(db)
        p = await projects.add(
            db,
            user_id=user.id,
            name="Original",
            default_tier_id="smart",
            retention_days=30,
        )
        updated = await projects.update(
            db,
            project_id=p.id,
            user_id=user.id,
            name="Renamed",
            default_tier_id=None,  # explicit clear
            # retention_days omitted -> unchanged
        )
        assert updated is not None
        assert updated.name == "Renamed"
        assert updated.default_tier_id is None
        assert updated.retention_days == 30


async def test_projects_update_not_owned(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user_a = await _make_user(db, name="A")
        user_b = await _make_user(db, name="B")
        p = await projects.add(db, user_id=user_a.id, name="Secret")
        result = await projects.update(
            db, project_id=p.id, user_id=user_b.id, name="Hacked"
        )
        assert result is None


async def test_projects_delete_unfiles_conversations(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Deleting a project un-files its conversations (sets project_id to None)."""
    async with session_factory() as db:
        user = await _make_user(db)
        p = await projects.add(db, user_id=user.id, name="Doomed")
        convo = Conversation(
            id=uuid4(), user_id=user.id, title="c1",
            selected_tier_id="fast", project_id=p.id,
        )
        db.add(convo)
        await db.flush()

        deleted = await projects.delete(db, project_id=p.id, user_id=user.id)
        assert deleted is True
        await db.commit()

    async with session_factory() as db:
        from sqlalchemy import select

        rows = (await db.execute(select(Project))).scalars().all()
        assert rows == []
        convo_row = (await db.execute(select(Conversation))).scalar_one()
        assert convo_row.project_id is None


async def test_projects_delete_not_owned(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user_a = await _make_user(db, name="A")
        user_b = await _make_user(db, name="B")
        p = await projects.add(db, user_id=user_a.id, name="Safe")
        assert await projects.delete(db, project_id=p.id, user_id=user_b.id) is False


# ===========================================================================
# prompt_templates
# ===========================================================================


async def test_prompt_templates_list_for_user_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user = await _make_user(db)
        result = await prompt_templates.list_for_user(db, user.id)
        assert result == []


async def test_prompt_templates_add_and_get(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user = await _make_user(db)
        t = await prompt_templates.add(
            db,
            user_id=user.id,
            title="Summarize",
            body="Summarize this: {{text}}",
            description="A summarizer",
        )
        assert t.title == "Summarize"
        assert t.body == "Summarize this: {{text}}"
        assert t.description == "A summarizer"

        fetched = await prompt_templates.get_for_user(
            db, template_id=t.id, user_id=user.id
        )
        assert fetched is not None
        assert fetched.id == t.id


async def test_prompt_templates_get_wrong_owner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user_a = await _make_user(db, name="A")
        user_b = await _make_user(db, name="B")
        t = await prompt_templates.add(
            db, user_id=user_a.id, title="X", body="Y"
        )
        assert await prompt_templates.get_for_user(db, template_id=t.id, user_id=user_b.id) is None


async def test_prompt_templates_update(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user = await _make_user(db)
        t = await prompt_templates.add(
            db, user_id=user.id, title="Old", body="old body"
        )
        updated = await prompt_templates.update(
            db,
            template_id=t.id,
            user_id=user.id,
            title="New",
            body="new body",
            description="desc",
        )
        assert updated is not None
        assert updated.title == "New"
        assert updated.body == "new body"
        assert updated.description == "desc"


async def test_prompt_templates_update_not_owned(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user_a = await _make_user(db, name="A")
        user_b = await _make_user(db, name="B")
        t = await prompt_templates.add(
            db, user_id=user_a.id, title="X", body="Y"
        )
        result = await prompt_templates.update(
            db, template_id=t.id, user_id=user_b.id, title="Z", body="W", description=None
        )
        assert result is None


async def test_prompt_templates_delete(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user = await _make_user(db)
        t = await prompt_templates.add(
            db, user_id=user.id, title="Temp", body="body"
        )
        assert await prompt_templates.delete(db, template_id=t.id, user_id=user.id) is True
        assert await prompt_templates.get_for_user(db, template_id=t.id, user_id=user.id) is None


async def test_prompt_templates_delete_not_owned(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user_a = await _make_user(db, name="A")
        user_b = await _make_user(db, name="B")
        t = await prompt_templates.add(
            db, user_id=user_a.id, title="X", body="Y"
        )
        assert await prompt_templates.delete(db, template_id=t.id, user_id=user_b.id) is False


# ===========================================================================
# tags
# ===========================================================================


async def test_tags_list_for_user_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user = await _make_user(db)
        result = await tags.list_for_user(db, user.id)
        assert result == []


async def test_tags_create_and_get(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user = await _make_user(db)
        t = await tags.create_for_user(db, user_id=user.id, name="work", color="#00ff00")
        assert t.name == "work"
        assert t.color == "#00ff00"

        fetched = await tags.get_for_user(db, tag_id=t.id, user_id=user.id)
        assert fetched is not None
        assert fetched.id == t.id


async def test_tags_get_wrong_owner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user_a = await _make_user(db, name="A")
        user_b = await _make_user(db, name="B")
        t = await tags.create_for_user(db, user_id=user_a.id, name="private")
        assert await tags.get_for_user(db, tag_id=t.id, user_id=user_b.id) is None


async def test_tags_update_for_user_partial(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Three-valued PATCH: omit color -> unchanged, explicit None -> clears."""
    async with session_factory() as db:
        user = await _make_user(db)
        t = await tags.create_for_user(db, user_id=user.id, name="alpha", color="red")

        # Rename only, color survives.
        updated = await tags.update_for_user(
            db, tag_id=t.id, user_id=user.id, name="beta"
        )
        assert updated is not None
        assert updated.name == "beta"
        assert updated.color == "red"

        # Explicitly clear color.
        cleared = await tags.update_for_user(
            db, tag_id=t.id, user_id=user.id, color=None
        )
        assert cleared is not None
        assert cleared.color is None


async def test_tags_update_for_user_not_owned(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user_a = await _make_user(db, name="A")
        user_b = await _make_user(db, name="B")
        t = await tags.create_for_user(db, user_id=user_a.id, name="x")
        result = await tags.update_for_user(
            db, tag_id=t.id, user_id=user_b.id, name="hacked"
        )
        assert result is None


async def test_tags_delete_for_user_cleans_join_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Deleting a tag removes conversation_tag join rows."""
    async with session_factory() as db:
        user = await _make_user(db)
        t = await tags.create_for_user(db, user_id=user.id, name="doomed")
        convo = Conversation(
            id=uuid4(), user_id=user.id, title="c1", selected_tier_id="fast"
        )
        db.add(convo)
        await db.flush()
        ct = ConversationTag(conversation_id=convo.id, tag_id=t.id)
        db.add(ct)
        await db.flush()

        assert await tags.delete_for_user(db, tag_id=t.id, user_id=user.id) is True
        await db.commit()

    async with session_factory() as db:
        from sqlalchemy import select

        assert (await db.execute(select(Tag))).scalars().all() == []
        assert (await db.execute(select(ConversationTag))).scalars().all() == []
        # Conversation itself survives.
        assert len((await db.execute(select(Conversation))).scalars().all()) == 1


async def test_tags_delete_for_user_not_owned(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user_a = await _make_user(db, name="A")
        user_b = await _make_user(db, name="B")
        t = await tags.create_for_user(db, user_id=user_a.id, name="safe")
        assert await tags.delete_for_user(db, tag_id=t.id, user_id=user_b.id) is False


# ===========================================================================
# memory_facts
# ===========================================================================


async def test_memory_facts_list_for_user_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user = await _make_user(db)
        result = await memory_facts.list_for_user(db, user.id)
        assert result == []


async def test_memory_facts_add_and_get(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user = await _make_user(db)
        f = await memory_facts.add(db, user_id=user.id, content="important fact")
        assert f.content == "important fact"
        assert f.source == "manual"

        fetched = await memory_facts.get_for_user(db, fact_id=f.id, user_id=user.id)
        assert fetched is not None
        assert fetched.id == f.id


async def test_memory_facts_list_for_injection(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Injection returns oldest-first content strings up to the limit."""
    async with session_factory() as db:
        user = await _make_user(db)
        await memory_facts.add(db, user_id=user.id, content="first")
        await memory_facts.add(db, user_id=user.id, content="second")
        await memory_facts.add(db, user_id=user.id, content="third")

        result = await memory_facts.list_for_injection(db, user.id, limit=2)
        # The ordering is by (created_at ASC, id ASC). In a single transaction
        # created_at ties (SQLite second-resolution), so order depends on UUID
        # sort. Just check the limit is respected.
        assert len(result) == 2
        assert set(result).issubset({"first", "second", "third"})


async def test_memory_facts_update_content(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user = await _make_user(db)
        f = await memory_facts.add(db, user_id=user.id, content="old")
        updated = await memory_facts.update_content(
            db, fact_id=f.id, user_id=user.id, content="new"
        )
        assert updated is not None
        assert updated.content == "new"


async def test_memory_facts_update_content_not_owned(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user_a = await _make_user(db, name="A")
        user_b = await _make_user(db, name="B")
        f = await memory_facts.add(db, user_id=user_a.id, content="private")
        result = await memory_facts.update_content(
            db, fact_id=f.id, user_id=user_b.id, content="hacked"
        )
        assert result is None


async def test_memory_facts_delete(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user = await _make_user(db)
        f = await memory_facts.add(db, user_id=user.id, content="temp")
        assert await memory_facts.delete(db, fact_id=f.id, user_id=user.id) is True
        assert await memory_facts.get_for_user(db, fact_id=f.id, user_id=user.id) is None


async def test_memory_facts_delete_not_owned(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as db:
        user_a = await _make_user(db, name="A")
        user_b = await _make_user(db, name="B")
        f = await memory_facts.add(db, user_id=user_a.id, content="safe")
        assert await memory_facts.delete(db, fact_id=f.id, user_id=user_b.id) is False

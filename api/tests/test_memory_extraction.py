"""Memory auto-extraction tests (D19, T08b).

Covers the extraction-reply parser and the fire-and-forget extraction task:
- `_parse_extracted_facts` tolerates JSON arrays and newline lists, drops
  blanks/dupes, and caps at the per-turn maximum.
- `_extract_memory_facts` inserts distilled facts (source="conversation") and
  respects the per-user cap.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, MemoryFact, User
from app.providers.protocol import ChatMessage, ProviderEvent
from app.streaming.handler import (
    _MEMORY_EXTRACT_MAX,
    _MEMORY_FACTS_PER_USER_CAP,
    _extract_memory_facts,
    _parse_extracted_facts,
)

# Parser ------------------------------------------------------------------------


def test_parse_json_array() -> None:
    facts = _parse_extracted_facts('["Prefers metric units", "Lives in Tokyo"]')
    assert facts == ["Prefers metric units", "Lives in Tokyo"]


def test_parse_caps_at_max() -> None:
    facts = _parse_extracted_facts('["a", "b", "c", "d", "e"]')
    assert len(facts) == _MEMORY_EXTRACT_MAX


def test_parse_drops_blanks_and_dupes() -> None:
    facts = _parse_extracted_facts('["", "  ", "Likes tea", "likes tea"]')
    # Blank/whitespace dropped; case-insensitive dedupe keeps the first.
    assert facts == ["Likes tea"]


def test_parse_newline_fallback() -> None:
    facts = _parse_extracted_facts("- Plays guitar\n- Has two cats\n")
    assert facts == ["Plays guitar", "Has two cats"]


def test_parse_empty_array_and_garbage() -> None:
    assert _parse_extracted_facts("[]") == []
    assert _parse_extracted_facts("") == []
    assert _parse_extracted_facts("   ") == []


# Extraction task ---------------------------------------------------------------


class _FactProvider:
    """Provider whose `complete` returns a canned extraction reply."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.seen: list[str] = []

    def stream(self, **_kwargs: object) -> AsyncIterator[ProviderEvent]:  # pragma: no cover
        raise NotImplementedError

    async def complete(
        self,
        *,
        model_id: str,
        history: list[ChatMessage],
        user_text: str,
        api_key: str | None = None,
        system_prefix: str | None = None,
    ) -> str:
        self.seen.append(user_text)
        return self.reply


async def _bootstrap_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID]:
    """Create an anon user via bootstrap and seed a conversation; return ids."""
    await client.get("/api/bootstrap")
    async with session_factory() as session:
        user_id = (await session.execute(select(User))).scalar_one().id
        convo = Conversation(
            user_id=user_id,
            title="New chat",
            selected_tier_id="smart",
            pinned=False,
        )
        session.add(convo)
        await session.commit()
        await session.refresh(convo)
        return user_id, convo.id


async def test_extraction_inserts_conversation_facts(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id, conv_id = await _bootstrap_user(client, session_factory)
    provider = _FactProvider('["Prefers metric units", "Lives in Tokyo"]')

    await _extract_memory_facts(
        provider=provider,
        model_id="model-x",
        api_key=None,
        conversation_id=conv_id,
        user_id=user_id,
        user_text="I always use kilometers and I'm based in Tokyo.",
        answer_text="Noted!",
        session_factory=session_factory,
    )

    # The model saw the turn transcript.
    assert provider.seen
    assert "Tokyo" in provider.seen[0]

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(MemoryFact).order_by(MemoryFact.created_at.asc())
            )
        ).scalars().all()
        contents = [r.content for r in rows]
        assert contents == ["Prefers metric units", "Lives in Tokyo"]
        assert all(r.source == "conversation" for r in rows)
        assert all(r.source_conversation_id == conv_id for r in rows)


async def test_extraction_noop_when_no_facts(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id, conv_id = await _bootstrap_user(client, session_factory)

    await _extract_memory_facts(
        provider=_FactProvider("[]"),
        model_id="model-x",
        api_key=None,
        conversation_id=conv_id,
        user_id=user_id,
        user_text="What's the weather?",
        answer_text="I can't check live weather.",
        session_factory=session_factory,
    )

    async with session_factory() as session:
        rows = (await session.execute(select(MemoryFact))).scalars().all()
        assert rows == []


async def test_extraction_respects_per_user_cap(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id, conv_id = await _bootstrap_user(client, session_factory)

    # Shrink the cap so the test stays cheap: pre-seed up to (cap - 1) facts so
    # only ONE of the extracted facts fits.
    monkeypatch.setattr("app.streaming.handler._MEMORY_FACTS_PER_USER_CAP", 2)
    async with session_factory() as session:
        session.add(MemoryFact(user_id=user_id, content="Existing fact", source="manual"))
        await session.commit()

    await _extract_memory_facts(
        provider=_FactProvider('["New fact A", "New fact B", "New fact C"]'),
        model_id="model-x",
        api_key=None,
        conversation_id=conv_id,
        user_id=user_id,
        user_text="some turn",
        answer_text="ok",
        session_factory=session_factory,
    )

    async with session_factory() as session:
        rows = (await session.execute(select(MemoryFact))).scalars().all()
        # Started at 1, cap is 2 ⇒ exactly one new fact inserted.
        assert len(rows) == 2
        contents = {r.content for r in rows}
        assert "Existing fact" in contents
        assert len(contents & {"New fact A", "New fact B", "New fact C"}) == 1


def test_per_user_cap_constant_is_bounded() -> None:
    # Sanity: the cap is a real positive bound, not accidentally 0/None.
    assert _MEMORY_FACTS_PER_USER_CAP > _MEMORY_EXTRACT_MAX
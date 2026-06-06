"""Alembic environment.

- Uses an async engine driven by `settings.database_url`.
- Target metadata = `app.db.base.Base.metadata` for autogen.
- The naming convention in `app/db/base.py` keeps constraint names stable.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Import the metadata target and models so autogen sees them.
from app.config import get_settings
from app.db import models  # noqa: F401 — register all tables on metadata
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a live connection)."""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def _ensure_wide_alembic_version(connection: Connection) -> None:
    """Widen Alembic's version-tracking column on Postgres.

    Alembic creates `alembic_version.version_num` as VARCHAR(32), but a couple
    of this project's revision ids are longer (e.g.
    `0019_preferences_per_conversation_budget` is 40 chars). SQLite ignores
    VARCHAR length, so tests / local dev never notice; Postgres rejects the
    write with `StringDataRightTruncationError` — which silently blocked prod
    from migrating past 0018. Ensure the version table exists with a wide column
    (fresh DB) and widen an existing narrow one (prod) BEFORE Alembic touches
    it. No-op off Postgres; widening a varchar is a metadata-only change. The
    constraint name matches Alembic's default so its own `checkfirst` create
    sees the table and skips re-creating it.
    """
    if connection.dialect.name != "postgresql":
        return
    connection.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS alembic_version ("
        " version_num VARCHAR(255) NOT NULL,"
        " CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
    )
    connection.exec_driver_sql(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )


async def run_migrations_online() -> None:
    """Run migrations against a live async engine."""
    engine = create_async_engine(_get_url(), future=True)
    # Widen the version column first, in its own committed transaction, so the
    # long revision ids fit on Postgres before Alembic writes them.
    async with engine.begin() as connection:
        await connection.run_sync(_ensure_wide_alembic_version)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

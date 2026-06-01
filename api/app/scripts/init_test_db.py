"""Reset all ORM tables on the configured ``DATABASE_URL``.

Test-only affordance for the FE↔BE Playwright E2E suite, which boots a real
uvicorn process against an ephemeral SQLite file. Non-test environments use
Alembic migrations and never import this module.

The script honours whatever ``DATABASE_URL`` is in the env, drops/recreates the
schema for a clean test run, and refuses to run unless ``ENV=test`` so a
misconfigured CI/cron job can't bypass Alembic on a real database. Import
``app.db.models`` for its metadata side-effect so every ``Base.metadata`` table
is registered before ``create_all`` runs.

Usage::

    uv run python -m app.scripts.init_test_db
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.db import models as _models  # noqa: F401 — register tables with Base.metadata
from app.db.base import Base


async def _reset_all(database_url: str) -> None:
    """Drop and recreate every Base.metadata table on ``database_url``."""
    # SQLite needs check_same_thread=False even on the async driver when the
    # engine is used briefly across the main task only (matches
    # ``app.db.session._build_engine``). No pool tuning needed — this is a
    # one-shot script.
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        parsed = make_url(database_url)
        if parsed.database and parsed.database != ":memory:":
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(database_url, connect_args=connect_args, future=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


def main() -> int:
    settings = get_settings()
    if settings.env != "test":
        print(
            "init_test_db refuses to run unless ENV=test; use Alembic.",
            file=sys.stderr,
        )
        return 1
    asyncio.run(_reset_all(settings.database_url))
    print(
        f"init_test_db: schema reset on {settings.database_url}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

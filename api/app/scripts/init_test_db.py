"""Create all ORM tables on the configured ``DATABASE_URL``.

Test-only affordance for the FE↔BE Playwright E2E suite, which boots a real
uvicorn process against an ephemeral SQLite file. Production uses Alembic
migrations and never imports this module.

The script honours whatever ``DATABASE_URL`` is in the env (typically
``sqlite+aiosqlite:///./.playwright-db/test.sqlite3`` for E2E). It refuses to
run when ``ENV=production`` so a misconfigured CI/cron job can't bypass
Alembic on a real database. Import ``app.db.models`` for its metadata
side-effect so every ``Base.metadata`` table is registered before
``create_all`` runs.

Usage::

    uv run python -m app.scripts.init_test_db
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.db import models as _models  # noqa: F401 — register tables with Base.metadata
from app.db.base import Base


async def _create_all(database_url: str) -> None:
    """Create every Base.metadata table on ``database_url`` (idempotent)."""
    # SQLite needs check_same_thread=False even on the async driver when the
    # engine is used briefly across the main task only (matches
    # ``app.db.session._build_engine``). No pool tuning needed — this is a
    # one-shot script.
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_async_engine(database_url, connect_args=connect_args, future=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


def main() -> int:
    settings = get_settings()
    if settings.env == "production":
        print(
            "init_test_db refuses to run with ENV=production; use Alembic.",
            file=sys.stderr,
        )
        return 1
    asyncio.run(_create_all(settings.database_url))
    print(
        f"init_test_db: schema created on {settings.database_url}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

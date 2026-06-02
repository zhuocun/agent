"""Alembic migration-drift test.

The rest of the suite builds its schema with `Base.metadata.create_all`
(see `tests/conftest.py`) for speed, which means the Alembic upgrade path is
only ever exercised at Docker boot (`alembic upgrade head`). This test closes
that gap inside pytest: it runs the migrations from base to head against a
fresh, throwaway SQLite database and then asserts the resulting schema has no
drift versus the ORM models in `app.db.models`.

Assertion strategy
------------------
We use the strict, full `alembic.autogenerate.compare_metadata` approach
(NOT the weaker structural fallback). On this schema `compare_metadata` on
SQLite emits exactly ONE category of spurious diff and nothing else, so the
strict path stays deterministic while still catching any real drift (missing
table/column/index/constraint, nullability changes, etc.).

The single spurious category we filter:

* ``modify_type`` from a reflected ``TIMESTAMP()`` to the model's
  ``DateTime(timezone=True)``. Every ``DateTime(timezone=True)`` column
  reflects back from SQLite as a plain ``TIMESTAMP`` because SQLite has no
  native timezone-aware timestamp type — the dialect simply cannot round-trip
  the ``timezone=True`` flag. This is a pure reflection artifact of running on
  SQLite; on Postgres (prod) the column is ``TIMESTAMP WITH TIME ZONE`` and the
  flag round-trips, so there is no diff there. We match this category as
  tightly as possible (old type is a ``TIMESTAMP`` instance, new type is a
  ``DateTime`` instance) so a genuine type change to/from any other type would
  still surface as a failing diff.

The test mirrors `alembic/env.py`'s online configuration exactly
(`compare_type=True`, `render_as_batch=True` on SQLite) so the comparison sees
the same picture the real autogenerate would.
"""

from __future__ import annotations

import os
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import TIMESTAMP, DateTime, create_engine

from alembic import command

# Repo layout: this file lives at api/tests/test_migrations.py, so the API
# project root (which holds alembic.ini and the alembic/ script directory) is
# the parent of the tests/ directory.
_API_ROOT = Path(__file__).resolve().parent.parent


def _is_spurious_sqlite_timestamp_diff(diff: object) -> bool:
    """True iff `diff` is the documented SQLite TIMESTAMP/DateTime artifact.

    For ``modify_type`` `compare_metadata` yields a flat 7-tuple
    ``(op, schema, table, column, existing_kwargs, old_type, new_type)``,
    wrapped in a single-element list. We accept ONLY the exact pattern where the
    reflected type is a `TIMESTAMP` and the model type is a `DateTime` — i.e.
    SQLite dropping the `timezone=True` flag on round-trip. Anything else
    (different op, different types) is treated as real drift.
    """
    # Column-level diffs arrive wrapped in a one-element list; table-level diffs
    # (e.g. add_table / remove_table) arrive as bare tuples. Unwrap the former.
    if isinstance(diff, list):
        if len(diff) != 1:
            return False
        diff = diff[0]
    if not isinstance(diff, tuple) or len(diff) != 7:
        return False
    op = diff[0]
    old_type = diff[5]
    new_type = diff[6]
    return (
        op == "modify_type"
        and isinstance(old_type, TIMESTAMP)
        and isinstance(new_type, DateTime)
    )


@pytest.fixture
def fresh_sqlite_url() -> Iterator[tuple[str, str]]:
    """A brand-new throwaway SQLite file, distinct from any other fixture DB.

    Yields ``(async_url, sync_url)``: the async URL is what `env.py` builds its
    engine from; the sync URL is what we open the reflection connection with.
    The file is removed on teardown so the test leaves nothing behind.
    """
    fd, path = tempfile.mkstemp(prefix="migration-drift-", suffix=".sqlite3")
    os.close(fd)
    p = Path(path)
    try:
        yield f"sqlite+aiosqlite:///{p}", f"sqlite:///{p}"
    finally:
        p.unlink(missing_ok=True)


def test_migrations_upgrade_to_head_has_no_drift(
    fresh_sqlite_url: tuple[str, str],
) -> None:
    """`alembic upgrade head` builds a schema with no drift vs the ORM models.

    Step 1 (broken-migration / bad batch_alter guard): run every migration from
    base to head and assert it completes without raising.

    Step 2 (drift guard): reflect the migrated DB and assert
    `compare_metadata` reports no diffs once the documented SQLite-only
    spurious category is filtered out.
    """
    async_url, sync_url = fresh_sqlite_url

    # `alembic/env.py` reads the URL from `get_settings().database_url`, which is
    # backed by the DATABASE_URL env var. Point it at our throwaway DB for the
    # duration, clearing the cached Settings before AND after so neither this
    # test nor its siblings see a stale/leaked engine URL. Restore the prior
    # env value on the way out to keep the test hermetic.
    # Importing models registers every table on Base.metadata (mirrors env.py).
    import app.db.models  # noqa: F401
    from app.config import get_settings
    from app.db.base import Base

    prior_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = async_url
    get_settings.cache_clear()
    try:
        cfg = Config(str(_API_ROOT / "alembic.ini"))
        # alembic.ini's script_location is relative ("alembic"); pin it to the
        # repo path so the test is independent of the process working directory.
        cfg.set_main_option("script_location", str(_API_ROOT / "alembic"))

        # Step 1: this raises if any migration (incl. SQLite batch_alter ops) is
        # broken on the upgrade path.
        #
        # `alembic/env.py` drives migrations via `asyncio.run(...)`, which
        # creates and then *closes* an event loop on the calling thread. Running
        # that on the main thread under `asyncio_mode=auto` would tear down the
        # loop that pytest-asyncio manages for sibling async tests (observed as
        # spurious `MissingGreenlet` failures elsewhere in the suite). Running
        # the upgrade on a dedicated worker thread keeps `asyncio.run`'s
        # loop lifecycle fully isolated from the test session's loop.
        upgrade_error: list[BaseException] = []

        def _run_upgrade() -> None:
            try:
                command.upgrade(cfg, "head")
            except BaseException as exc:  # re-raised on the test thread below
                upgrade_error.append(exc)

        worker = threading.Thread(target=_run_upgrade)
        worker.start()
        worker.join()
        if upgrade_error:
            raise upgrade_error[0]

        # Step 2: reflect the migrated schema and diff it against the ORM models
        # using the same options env.py configures for SQLite.
        engine = create_engine(sync_url)
        try:
            with engine.connect() as conn:
                context = MigrationContext.configure(
                    conn,
                    opts={
                        "compare_type": True,
                        "render_as_batch": True,
                        "target_metadata": Base.metadata,
                    },
                )
                diffs = compare_metadata(context, Base.metadata)
        finally:
            engine.dispose()
    finally:
        if prior_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prior_db_url
        get_settings.cache_clear()

    real_diffs = [d for d in diffs if not _is_spurious_sqlite_timestamp_diff(d)]
    assert real_diffs == [], (
        "Alembic migrations drift from the ORM models. Unexpected diffs:\n"
        + "\n".join(repr(d) for d in real_diffs)
    )

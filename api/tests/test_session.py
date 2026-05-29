"""Unit tests for the async DB-URL normalization in app.db.session."""

from app.db.session import _normalize_async_url


def test_bare_postgres_scheme_gets_asyncpg_driver() -> None:
    assert (
        _normalize_async_url("postgres://user:pw@host:5432/db")
        == "postgresql+asyncpg://user:pw@host:5432/db"
    )


def test_postgresql_scheme_gets_asyncpg_driver() -> None:
    assert (
        _normalize_async_url("postgresql://user:pw@host/db")
        == "postgresql+asyncpg://user:pw@host/db"
    )


def test_explicit_async_driver_is_untouched() -> None:
    url = "postgresql+asyncpg://user:pw@host/db"
    assert _normalize_async_url(url) == url


def test_sqlite_url_is_untouched() -> None:
    url = "sqlite+aiosqlite:///./dev.sqlite3"
    assert _normalize_async_url(url) == url

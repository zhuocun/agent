"""Cross-dialect column type helpers.

The plan calls for `JSONB` and `UUID` in Postgres but the test suite runs on
SQLite via `aiosqlite`. We pick the dialect at column-bind time so the same ORM
models work in both environments without per-test schema swaps.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import CHAR, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811 (vendor alias)
from sqlalchemy.types import TypeDecorator


class JsonVariant(TypeDecorator[Any]):
    """JSONB on Postgres, JSON elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class UuidVariant(TypeDecorator[UUID]):
    """Native UUID on Postgres, 36-char string elsewhere. Always passes UUIDs."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PgUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, UUID):
            return value if dialect.name == "postgresql" else str(value)
        # Accept stringified UUIDs too.
        parsed = UUID(str(value))
        return parsed if dialect.name == "postgresql" else str(parsed)

    def process_result_value(self, value: Any, dialect: Any) -> UUID | None:
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        return UUID(str(value))

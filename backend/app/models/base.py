"""Declarative base, mixins and a portable GUID column type.

IDs are stored as 36-char UUID strings on every database (including
PostgreSQL).  This keeps generated DDL, the runtime type, and client code
identical across SQLite and PostgreSQL - there is no native-UUID cast
mismatch between Alembic migrations and the ORM.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import CHAR, TypeDecorator


class GUID(TypeDecorator):
    """UUID stored as a 36-char string (portable across databases)."""

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return str(value)


def utcnow() -> datetime:
    """Naive UTC timestamp (kept naive for portability across DBs)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class UUIDPkMixin:
    id: Mapped[str] = mapped_column(
        GUID, primary_key=True, default=lambda: str(uuid.uuid4())
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow, onupdate=utcnow, nullable=False
    )

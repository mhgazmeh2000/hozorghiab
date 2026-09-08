"""Async engine + session factory.

Production deployments use PostgreSQL (DATABASE_URL=postgresql+psycopg://...).
SQLite (aiosqlite) is supported for local development and tests.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.models.base import Base  # noqa: F401  (re-exported for alembic autogen)

_engine = None
_session_factory = None


def _make_engine_kwargs():
    kw: dict = {"echo": settings.db_echo, "pool_pre_ping": True}
    if settings.is_postgres:
        kw.update(pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow)
    else:
        kw.update(connect_args={"check_same_thread": False, "timeout": 30})
    return kw


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.database_url, **_make_engine_kwargs())
        event.listen(_engine.sync_engine, "connect", _configure_sqlite_connection)
    return _engine


def reset_engine_for_tests(url: str | None = None):
    """Allow tests to rebind a fresh in-memory engine."""
    global _engine, _session_factory
    if _engine is not None:
        import asyncio

        try:
            asyncio.get_event_loop()
        except Exception:
            pass
        _engine = None
    _session_factory = None
    if url:
        settings.database_url = url


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


async def init_db() -> None:
    """Create tables (used only for tests / ultra-fast local bootstrap).

    Production deployments must use Alembic migrations (`alembic upgrade head`).
    """
    from app.models import register_models  # noqa: F401

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    """Allow local SQLite readers/writers to coexist during background jobs."""
    if settings.is_postgres:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()



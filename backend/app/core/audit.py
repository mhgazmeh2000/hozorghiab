"""Audit logging helper.

All security-relevant operations must be recorded through this module.  The
write is best-effort: an audit failure must never break the primary operation.
"""
from __future__ import annotations

import time
from contextvars import ContextVar
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.personnel import AuditLog
from app.models.base import utcnow

# request-scoped context (username/ip) populated by middleware/deps
current_actor: ContextVar[dict] = ContextVar("audit_actor", default={})


def set_actor(username: Optional[str], user_id: Optional[str], source_ip: Optional[str]):
    current_actor.set({"username": username, "user_id": user_id, "source_ip": source_ip})


class Audit:
    """Async-friendly audit recorder bound to a session."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record(
        self,
        action: str,
        *,
        result: str = "success",
        device_id: Optional[str] = None,
        device_ip: Optional[str] = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None,
        details: Optional[dict] = None,
        actor: Optional[dict] = None,
    ) -> None:
        actor = actor or current_actor.get()
        try:
            entry = AuditLog(
                created_at=utcnow(),
                username=actor.get("username"),
                user_id=actor.get("user_id"),
                source_ip=actor.get("source_ip"),
                action=action,
                device_id=device_id,
                device_ip=device_ip,
                result=result,
                error=(error or "")[:4000],
                duration_ms=duration_ms,
                details=details or {},
            )
            self.db.add(entry)
            await self.db.flush()
        except Exception:  # pragma: no cover - never crash on audit failure
            await self.db.rollback()


class AuditTimer:
    """Records an audit entry with elapsed duration on context exit."""

    def __init__(self, audit: Audit, action: str, **kwargs):
        self.audit = audit
        self.action = action
        self.kwargs = kwargs
        self.start = time.perf_counter()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        ms = int((time.perf_counter() - self.start) * 1000)
        if exc is not None:
            await self.audit.record(
                self.action, result="error", error=str(exc)[:2000],
                duration_ms=ms, **self.kwargs,
            )
        else:
            await self.audit.record(self.action, duration_ms=ms, **self.kwargs)
        return False

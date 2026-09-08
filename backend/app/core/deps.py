"""Shared FastAPI dependencies."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import set_actor
from app.core.config import settings
from app.core.security import decode_access_token
from app.database import get_session
from app.models import SystemUser

_bearer = HTTPBearer(auto_error=False)


# --------------------------------------------------------------------------
# Rate limiting (in-memory sliding window)
# --------------------------------------------------------------------------

_hits: dict[str, deque] = defaultdict(deque)


def _check_rate(scope: str, limit_per_minute: int, key: str) -> None:
    now = time.monotonic()
    q = _hits[f"{scope}:{key}"]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
        )
    q.append(now)


def rate_limit(scope: str, limit_per_minute: Optional[int] = None) -> callable:
    limit = limit_per_minute or (
        settings.rate_limit_auth_per_minute
        if scope == "auth"
        else settings.rate_limit_api_per_minute
    )

    def dep(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        client = request.client.host if request.client else "unknown"
        _check_rate(scope, limit, client)

    return dep


# --------------------------------------------------------------------------
# Auth / RBAC
# --------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_session),
) -> SystemUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        ) from exc
    user = await db.scalar(
        select(SystemUser).where(SystemUser.username == payload.get("sub"))
    )
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="inactive user"
        )
    set_actor(
        user.username,
        user.id,
        request.client.host if request.client else None,
    )
    return user


def require_roles(*roles: str):
    async def dep(user: SystemUser = Depends(get_current_user)) -> SystemUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires role {', '.join(roles)}",
            )
        return user

    return dep


async def require_viewer(user: SystemUser = Depends(get_current_user)) -> SystemUser:
    return user


def get_source_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None

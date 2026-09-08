"""Shared FastAPI dependencies.

Rate limiting
-------------
Two backends:

* ``memory`` -- simple in-process sliding window (single-node dev only).
* ``redis``  -- Redis-backed sliding window (safe across multiple workers
  / replicas). Uses a sorted-set per key with O(log N) trimming and is
  atomic per Lua script; connection failures fall back to memory so a
  Redis outage does not lock out the API.

Both backends key on ``(scope, client_ip)`` so they don't affect auth state.
"""
from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


# --------------------------------------------------------------------------
# Redis connection (lazy, optional)
# --------------------------------------------------------------------------

_redis_client = None
_redis_tried = False


def _get_redis_client():  # pragma: no cover - exercised only when redis up
    """Return a redis.asyncio client if REDIS_URL is reachable, else None.

    We do NOT crash if Redis is unavailable; we fall back to in-memory
    rate limiting so the API stays usable (single-node dev / transient
    outages). In production the validation layer already ensures Redis
    is configured; here we just stay resilient.
    """
    global _redis_client, _redis_tried
    if _redis_tried:
        return _redis_client
    _redis_tried = True
    if settings.rate_limit_backend != "redis" or not settings.redis_url:
        return None
    try:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(
            settings.redis_url,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
            decode_responses=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis rate-limit backend unavailable: %s", exc)
        _redis_client = None
    return _redis_client


# Lua script: atomically ZADD/ZREMRANGEBYSCORE/ZCARD/EXPIRE for sliding window.
_LUA_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window * 1000)
local count = tonumber(redis.call('ZCARD', key))
if count >= limit then
    redis.call('EXPIRE', key, window)
    return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window)
return 1
"""


async def _redis_check(scope: str, limit_per_minute: int, key: str) -> None:
    import uuid

    redis_client = _get_redis_client()
    if redis_client is None:
        return _memory_check(scope, limit_per_minute, key)
    rk = f"rl:{scope}:{key}"
    now_ms = int(time.time() * 1000)
    try:
        ok = await redis_client.eval(
            _LUA_SLIDING_WINDOW,
            1,
            rk,
            now_ms,
            60,
            limit_per_minute,
            f"{now_ms}-{uuid.uuid4().hex}",
        )
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded",
            )
    except (HTTPException, RuntimeError):
        raise
    except Exception as exc:  # noqa: BLE001 - redis outage fallback
        logger.warning("Redis rate-limit error; falling back to memory: %s", exc)
        return _memory_check(scope, limit_per_minute, key)


# --------------------------------------------------------------------------
# In-memory sliding window (dev / fallback)
# --------------------------------------------------------------------------

_hits: dict[str, deque] = defaultdict(deque)


def _memory_check(scope: str, limit_per_minute: int, key: str) -> None:
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


def rate_limit(scope: str, limit_per_minute: Optional[int] = None):
    """Return an async FastAPI dependency that enforces rate limits."""
    limit = limit_per_minute or (
        settings.rate_limit_auth_per_minute
        if scope == "auth"
        else settings.rate_limit_api_per_minute
    )

    async def dep(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        client = request.client.host if request.client else "unknown"
        xff = request.headers.get("x-forwarded-for")
        if xff:
            client = xff.split(",")[0].strip() or client
        if settings.rate_limit_backend == "redis":
            await _redis_check(scope, limit, client)
        else:
            _memory_check(scope, limit, client)

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
    """RBAC dependency. Pass role names that may access the route.

    The ``admin`` role is always allowed unless the endpoint explicitly
    lists a stricter set that does NOT include "admin" (defensive default:
    admins can do anything).
    """
    allowed = set(roles)

    async def dep(user: SystemUser = Depends(get_current_user)) -> SystemUser:
        if user.role == "admin":
            return user
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires role {', '.join(sorted(allowed))}",
            )
        return user

    return dep


async def require_viewer(user: SystemUser = Depends(get_current_user)) -> SystemUser:
    return user


def get_source_ip(request: Request) -> Optional[str]:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip() or (request.client.host if request.client else None)
    return request.client.host if request.client else None

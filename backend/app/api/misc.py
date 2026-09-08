"""Audit log browsing, settings, system-user management."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Audit
from app.core.deps import get_current_user, require_roles
from app.core.security import hash_password
from app.database import get_session
from app.models import SystemSetting, SystemUser
from app.models.personnel import AuditLog
from app.schemas.schemas import SettingOut, SettingUpdate
from app.services.settings_store import DEFAULTS, get_setting, set_setting

router = APIRouter(tags=["system"])


# --- audit ---------------------------------------------------------------


@router.get("/audit", response_model=dict)
async def audit_logs(
    action: Optional[str] = None,
    username: Optional[str] = None,
    result: Optional[str] = None,
    device_id: Optional[str] = None,
    date_from=None,
    date_to=None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if username:
        stmt = stmt.where(AuditLog.username == username)
    if result:
        stmt = stmt.where(AuditLog.result == result)
    if device_id:
        stmt = stmt.where(AuditLog.device_id == device_id)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (
        await db.scalars(
            stmt.order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    items = [
        {
            "id": r.id,
            "created_at": r.created_at,
            "username": r.username,
            "action": r.action,
            "device_id": r.device_id,
            "device_ip": r.device_ip,
            "result": r.result,
            "error": r.error,
            "duration_ms": r.duration_ms,
            "source_ip": r.source_ip,
            "details": r.details,
        }
        for r in rows
    ]
    return {"total": int(total or 0), "page": page, "page_size": page_size, "items": items}


# --- settings -------------------------------------------------------------


@router.get("/settings", response_model=list[SettingOut])
async def list_settings(
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator", "viewer")),
):
    from app.services.settings_store import ensure_defaults

    await ensure_defaults(db)
    rows = (
        await db.scalars(select(SystemSetting).order_by(SystemSetting.key))
    ).all()
    rows = [r for r in rows if not r.key.startswith("_")]
    return rows


@router.get("/settings/defaults", response_model=dict)
async def settings_defaults(
    user: SystemUser = Depends(require_roles("admin", "operator", "viewer")),
):
    return {k: v["description"] for k, v in DEFAULTS.items()}


@router.put("/settings/{key}", response_model=SettingOut)
async def update_setting(
    key: str,
    body: SettingUpdate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin")),
):
    valid = {k for k in DEFAULTS} | {
        "realtime.poll_interval_s",
    }
    if key not in DEFAULTS:
        raise HTTPException(status_code=400, detail=f"unknown setting key: {key}")
    row = await set_setting(db, key, body.value)
    audit = Audit(db)
    await audit.record(
        "settings_update", result="success",
        details={"key": key}, actor={"username": user.username},
    )
    await db.commit()
    return row


# --- system users -----------------------------------------------------------


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    role: str


class UserPatch(BaseModel):
    password: Optional[str] = None
    display_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/system/users", response_model=list)
async def list_system_users(
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin")),
):
    rows = (await db.scalars(select(SystemUser).order_by(SystemUser.username))).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "role": u.role,
            "is_active": u.is_active,
            "must_change_password": u.must_change_password,
            "last_login_at": u.last_login_at,
            "created_at": u.created_at,
        }
        for u in rows
    ]


@router.post("/system/users", status_code=201)
async def create_system_user(
    body: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin")),
):
    if body.role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=400, detail="invalid role")
    existing = await db.scalar(
        select(SystemUser).where(SystemUser.username == body.username)
    )
    if existing:
        raise HTTPException(status_code=409, detail="username exists")
    row = SystemUser(
        username=body.username,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(row)
    await db.flush()
    audit = Audit(db)
    await audit.record(
        "user_create", details={"system_user": body.username},
        actor={"username": user.username},
    )
    await db.commit()
    return {"ok": True, "id": row.id}


@router.patch("/system/users/{user_id}")
async def patch_system_user(
    user_id: str,
    body: UserPatch,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin")),
):
    row = await db.get(SystemUser, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="user not found")
    if body.password:
        row.password_hash = hash_password(body.password)
        row.must_change_password = False
    if body.display_name is not None:
        row.display_name = body.display_name
    if body.role is not None:
        if body.role not in ("admin", "operator", "viewer"):
            raise HTTPException(status_code=400, detail="invalid role")
        if row.username == user.username and body.role != "admin":
            raise HTTPException(status_code=400, detail="cannot demote yourself")
        row.role = body.role
    if body.is_active is not None:
        if row.username == user.username and not body.is_active:
            raise HTTPException(status_code=400, detail="cannot disable yourself")
        row.is_active = body.is_active
    audit = Audit(db)
    await audit.record(
        "user_update", details={"system_user": row.username},
        actor={"username": user.username},
    )
    await db.commit()
    return {"ok": True}

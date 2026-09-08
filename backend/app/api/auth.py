"""Authentication: login, me, change password, logout."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Audit
from app.core.deps import (
    get_current_user,
    get_session,
    rate_limit,
)
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.database import get_session as _dbdep
from app.models import SystemUser
from app.models.base import utcnow
from app.schemas.schemas import (
    LoginRequest,
    MeResponse,
    PasswordChangeRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit("auth"))])
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(_dbdep),
):
    user = await db.scalar(
        select(SystemUser).where(SystemUser.username == body.username)
    )
    if user is None or not verify_password(body.password, user.password_hash):
        audit = Audit(db)
        await audit.record(
            "login",
            result="error",
            error="invalid credentials",
            details={"username": body.username},
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="invalid username or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="account disabled")
    user.last_login_at = utcnow()
    token = create_access_token(user.username, user.role)
    audit = Audit(db)
    await audit.record("login", details={"username": user.username})
    await db.commit()
    return TokenResponse(
        access_token=token,
        role=user.role,
        display_name=user.display_name,
        username=user.username,
    )


@router.post("/logout")
async def logout(
    request: Request,
    user: SystemUser = Depends(get_current_user),
    db: AsyncSession = Depends(_dbdep),
):
    audit = Audit(db)
    await audit.record("logout", details={"username": user.username})
    await db.commit()
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(user: SystemUser = Depends(get_current_user)):
    return user


@router.post("/change-password")
async def change_password(
    body: PasswordChangeRequest,
    user: SystemUser = Depends(get_current_user),
    db: AsyncSession = Depends(_dbdep),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="current password incorrect")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    audit = Audit(db)
    await audit.record("password_change", details={"username": user.username})
    await db.commit()
    return {"ok": True}

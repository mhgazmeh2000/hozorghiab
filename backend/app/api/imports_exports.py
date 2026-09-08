"""User (and attendance) import/export endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Audit
from app.core.deps import get_current_user, require_roles
from app.database import get_session
from app.models import SystemUser
from app.schemas.schemas import ImportPreview
from app.services import importexport

router = APIRouter(prefix="/importexport", tags=["importexport"])


@router.post("/{entity}/preview", response_model=ImportPreview)
async def preview_import(
    entity: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    if entity not in ("users", "attendance"):
        raise HTTPException(status_code=400, detail="entity must be users or attendance")
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file too large (max 20MB)")
    try:
        path = importexport.save_import_file(file.filename or "upload", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return await importexport.validate_import(db, path, entity)
    except Exception as exc:  # noqa: BLE001
        import os

        try:
            os.remove(path)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail=f"cannot parse file: {exc}") from exc


@router.post("/{entity}/apply")
async def apply_import(
    entity: str,
    file: UploadFile = File(...),
    device_id: Optional[str] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    if entity not in ("users", "attendance"):
        raise HTTPException(status_code=400, detail="entity must be users or attendance")
    content = await file.read()
    try:
        path = importexport.save_import_file(file.filename or "upload", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = await importexport.apply_import(db, path, entity, device_id=device_id)
    except Exception as exc:  # noqa: BLE001
        audit = Audit(db)
        await audit.record(
            "user_import" if entity == "users" else "attendance_import",
            result="error",
            error=str(exc)[:2000],
            details={"entity": entity, "device_id": device_id},
            actor={"username": user.username},
        )
        await db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit = Audit(db)
    await audit.record(
        "user_import" if entity == "users" else "attendance_import",
        result="success",
        device_id=device_id,
        details={"entity": entity, "applied": result.get("applied")},
        actor={"username": user.username},
    )
    await db.commit()
    return result


@router.get("/users/export")
async def export_users(
    fmt: str = Query("csv", pattern="^(csv|json|xlsx)$"),
    device_id: Optional[str] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator", "viewer")),
):
    content = await importexport.export_users(db, device_id, fmt)
    audit = Audit(db)
    await audit.record(
        "user_export", device_id=device_id,
        details={"format": fmt}, actor={"username": user.username},
    )
    await db.commit()
    ctype = {
        "csv": "text/csv; charset=utf-8",
        "json": "application/json",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }[fmt]
    return Response(
        content,
        media_type=ctype,
        headers={
            "Content-Disposition": (
                f'attachment; filename="users-{device_id or "all"}.{fmt}"'
            )
        },
    )

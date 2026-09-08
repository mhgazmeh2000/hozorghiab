"""Attendance log querying and export endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Audit
from app.core.deps import get_current_user
from app.database import get_session
from app.models import AttendanceLog, Device, DeviceUser, SystemUser
from app.schemas.schemas import AttendanceLogOut
from app.services import importexport

router = APIRouter(prefix="/attendance", tags=["attendance"])

SORT_FIELDS = {
    "event_time": AttendanceLog.event_time,
    "employee": AttendanceLog.employee_code,
    "event_type": AttendanceLog.event_type,
    "created_at": AttendanceLog.created_at,
}


def _apply_filters(
    stmt,
    device_id=None,
    employee=None,
    department=None,
    date_from=None,
    date_to=None,
    event_type=None,
    verification=None,
    search=None,
):
    if device_id:
        stmt = stmt.where(AttendanceLog.device_id == device_id)
    if employee:
        stmt = stmt.where(AttendanceLog.employee_code == employee)
    if department:
        stmt = stmt.join(DeviceUser, AttendanceLog.user_id == DeviceUser.id, isouter=True).where(
            DeviceUser.department == department
        )
    if date_from:
        stmt = stmt.where(AttendanceLog.event_time >= date_from)
    if date_to:
        stmt = stmt.where(AttendanceLog.event_time <= date_to)
    if event_type:
        stmt = stmt.where(AttendanceLog.event_type == event_type.upper())
    if verification:
        stmt = stmt.where(AttendanceLog.verification_type == verification.upper())
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            (AttendanceLog.employee_code.like(like))
            | (AttendanceLog.user_id_on_device.like(like))
        )
    return stmt


@router.get("", response_model=dict)
async def list_attendance(
    device_id: Optional[str] = None,
    employee: Optional[str] = None,
    department: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    event_type: Optional[str] = None,
    verification: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = Query("event_time"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    base = _apply_filters(
        select(AttendanceLog),
        device_id, employee, department, date_from, date_to,
        event_type, verification, search,
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    sort_col = SORT_FIELDS.get(sort, AttendanceLog.event_time)
    col = sort_col.desc() if order == "desc" else sort_col.asc()
    rows = (
        await db.scalars(
            base.order_by(col).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return {
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
        "items": [AttendanceLogOut.model_validate(r).model_dump() for r in rows],
    }


@router.get("/recent")
async def recent_attendance(
    limit: int = Query(25, le=100),
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    """Latest events (used by the real-time dashboard ticker)."""
    rows = (
        await db.scalars(
            select(AttendanceLog)
            .order_by(AttendanceLog.created_at.desc())
            .limit(limit)
        )
    ).all()
    items = []
    for r in rows:
        d = AttendanceLogOut.model_validate(r).model_dump()
        dev = await db.get(Device, r.device_id)
        d["device_ip"] = dev.ip_address if dev else None
        items.append(d)
    return items


@router.get("/today/summary")
async def today_summary(
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    total = int(
        (
            await db.scalar(
                select(func.count(AttendanceLog.id)).where(
                    AttendanceLog.event_time >= start
                )
            )
        )
        or 0
    )
    by_type = dict(
        (
            await db.execute(
                select(AttendanceLog.event_type, func.count())
                .where(AttendanceLog.event_time >= start)
                .group_by(AttendanceLog.event_type)
            )
        ).all()
    )
    return {"today_total": total, "by_event_type": by_type}


@router.get("/export")
async def export_attendance(
    fmt: str = Query("csv", pattern="^(csv|json|xlsx)$"),
    device_id: Optional[str] = None,
    employee: Optional[str] = None,
    department: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    event_type: Optional[str] = None,
    verification: Optional[str] = None,
    request: Request = None,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    content = await importexport.export_attendance(
        db,
        fmt,
        device_id=device_id,
        employee=employee,
        department=department,
        date_from=date_from,
        date_to=date_to,
        event_type=event_type,
        verification=verification,
    )
    audit = Audit(db)
    await audit.record(
        "attendance_export",
        device_id=device_id,
        details={"format": fmt, "filters": {
            "employee": employee, "department": department,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        }},
        actor={"username": user.username},
    )
    await db.commit()
    ctype = {
        "csv": "text/csv; charset=utf-8",
        "json": "application/json",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }[fmt]
    fname = {
        "csv": "attendance.csv",
        "json": "attendance.json",
        "xlsx": "attendance.xlsx",
    }[fmt]
    return Response(
        content,
        media_type=ctype,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )

"""Dashboard statistics endpoint."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_session
from app.models import (
    AttendanceLog,
    AuditLog,
    Device,
    DeviceUser,
    SystemUser,
)
from app.models.enums import DeviceStatus
from app.schemas.schemas import DashboardStats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def stats(
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    out = DashboardStats()

    async def count(where=None):
        stmt = select(func.count())
        if where is not None:
            stmt = stmt.select_from(Device).where(where)
        else:
            stmt = stmt.select_from(Device)
        return int((await db.scalar(stmt)) or 0)

    out.total_devices = await count()
    out.online_devices = await count(Device.status == DeviceStatus.ONLINE.value)
    out.offline_devices = await count(Device.status == DeviceStatus.OFFLINE.value)
    out.unknown_devices = await count(Device.status == DeviceStatus.UNKNOWN.value)
    out.verified_devices = await count(Device.status == DeviceStatus.VERIFIED.value)
    out.attendance_candidates = await count(Device.is_attendance_candidate.is_(True))

    out.total_users = int(
        (await db.scalar(select(func.count(DeviceUser.id)))) or 0
    )
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    out.today_attendance = int(
        (
            await db.scalar(
                select(func.count(AttendanceLog.id)).where(
                    AttendanceLog.event_time >= start
                )
            )
        )
        or 0
    )
    out.last_sync_at = await db.scalar(
        select(func.max(Device.last_sync_at))
    )
    cutoff = datetime.now() - timedelta(hours=24)
    out.failed_operations_24h = int(
        (
            await db.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.created_at >= cutoff,
                    AuditLog.result == "error",
                )
            )
        )
        or 0
    )
    from app.models import DeviceNetwork

    out.networks_count = int(
        (await db.scalar(select(func.count(DeviceNetwork.id)))) or 0
    )
    from app.models.jobs import DiscoveryJob, SyncJob

    pending = await db.scalar(
        select(func.count(DiscoveryJob.id)).where(
            DiscoveryJob.status.in_(["PENDING", "RUNNING"])
        )
    )
    pending += (
        await db.scalar(
            select(func.count(SyncJob.id)).where(
                SyncJob.status.in_(["PENDING", "RUNNING"])
            )
        )
    ) or 0
    out.pending_jobs = int(pending or 0)
    return out

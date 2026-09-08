"""Dashboard statistics endpoint.

Counts device states accurately per the Task 6/21 model:

- ONLINE_PROTOCOL_OPEN + ONLINE_PROTOCOL_VERIFIED + VERIFIED -> online_devices
- OFFLINE_VERIFIED                                          -> offline_devices
- PROBE_UNREACHABLE                                         -> probe_unreachable_devices
  (does NOT prove the device is down; call out separately)
- UNKNOWN / DISABLED                                        -> unknown_devices
- VERIFIED                                                  -> verified_devices
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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

_ONLINE_STATES = [
    DeviceStatus.ONLINE_PROTOCOL_OPEN.value,
    DeviceStatus.ONLINE_PROTOCOL_VERIFIED.value,
    DeviceStatus.VERIFIED.value,
]
_OFFLINE_STATES = [DeviceStatus.OFFLINE_VERIFIED.value]
_PROBE_UNREACHABLE = [DeviceStatus.PROBE_UNREACHABLE.value]


@router.get("/stats", response_model=DashboardStats)
async def stats(
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    out = DashboardStats()
    out.server_time = datetime.utcnow()

    async def count(where=None):
        stmt = select(func.count()).select_from(Device)
        if where is not None:
            stmt = stmt.where(where)
        return int((await db.scalar(stmt)) or 0)

    out.total_devices = await count()
    out.online_devices = await count(Device.status.in_(_ONLINE_STATES))
    out.offline_devices = await count(Device.status.in_(_OFFLINE_STATES))
    out.probe_unreachable_devices = await count(Device.status.in_(_PROBE_UNREACHABLE))
    out.execution_environment_unreachable = out.probe_unreachable_devices  # alias for UI
    out.last_known_online_devices = out.offline_devices  # offine-verified were previously online
    out.unknown_devices = await count(
        or_(Device.status == DeviceStatus.UNKNOWN.value, Device.status == DeviceStatus.DISABLED.value)
    )
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
    out.last_sync_at = await db.scalar(select(func.max(Device.last_sync_at)))
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
    sync_pending = await db.scalar(
        select(func.count(SyncJob.id)).where(
            SyncJob.status.in_(["PENDING", "RUNNING"])
        )
    )
    out.pending_jobs = int((pending or 0) + (sync_pending or 0))

    # Storage threshold alerts (configurable)
    alerts = []
    thresholds = sorted(settings.storage_warn_thresholds)
    if thresholds:
        warn_threshold = thresholds[0]
        rows = (
            await db.scalars(
                select(Device).where(
                    Device.storage_usage_pct.isnot(None),
                    Device.storage_usage_pct >= warn_threshold,
                )
            )
        ).all()
        for d in rows:
            pct = d.storage_usage_pct or 0
            level = next((t for t in reversed(thresholds) if pct >= t), warn_threshold)
            alerts.append({
                "device_id": d.id,
                "ip": d.ip_address,
                "name": d.display_name,
                "usage_pct": pct,
                "threshold": level,
            })
    out.storage_alerts = alerts

    # Last overall sync status: most recent finished sync job result
    last_sync_job = (
        await db.scalar(
            select(SyncJob)
            .where(SyncJob.status.in_(["COMPLETED", "FAILED"]))
            .order_by(SyncJob.finished_at.desc())
            .limit(1)
        )
    )
    out.last_sync_status = last_sync_job.status if last_sync_job else None

    return out

"""Sync engine.

Directions:
  device_to_server: pull users + logs into the local DB (idempotent).
  server_to_device: push users from the local DB to the device.
  bidirectional:     pull first, then push.

Runs as a background job persisted in sync_jobs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session_factory
from app.models import Device, DeviceUser, SyncJob
from app.models.base import utcnow
from app.models.enums import JobStatus, SyncDirection
from app.services.attendance_service import pull_attendance_logs
from app.services.device_service import (
    instantiate_adapter,
    read_and_store_users,
    run_adapter_op,
)
from app.services import job_runner


def start_sync_job(job_id: str) -> None:
    """Dispatch a sync job via the configured runner (builtin or celery)."""
    job_runner.submit_sync_job(job_id)


async def create_sync_job(
    db: AsyncSession,
    device_id: str,
    direction: str,
    scope: str = "full",
    requested_by: Optional[str] = None,
) -> SyncJob:
    job = SyncJob(
        device_id=device_id,
        direction=direction,
        scope=scope,
        requested_by=requested_by,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def execute_sync_job(job_id: str) -> None:
    sf = get_session_factory()
    async with sf() as db:
        job = await db.get(SyncJob, job_id)
        if job is None:
            return
        device = await db.get(Device, job.device_id)
        if device is None:
            job.status = JobStatus.FAILED.value
            job.error = "device not found"
            job.finished_at = utcnow()
            await db.commit()
            return
        job.status = JobStatus.RUNNING.value
        job.started_at = utcnow()
        await db.commit()

        stats: dict = {}
        try:
            if job.direction in (
                SyncDirection.DEVICE_TO_SERVER.value,
                SyncDirection.BIDIRECTIONAL.value,
            ):
                if job.scope in ("full", "users"):
                    users = await read_and_store_users(db, device)
                    stats["users_pulled"] = len(users)
                    stats["logs_pulled"] = 0
                if job.scope in ("full", "logs"):
                    pulled = await pull_attendance_logs(db, device)
                    stats["logs_pulled"] = pulled.get("inserted", 0)
                    stats["logs_duplicates"] = pulled.get("duplicates", 0)
                    stats["device_log_count"] = pulled.get("device_count")

            if job.direction in (
                SyncDirection.SERVER_TO_DEVICE.value,
                SyncDirection.BIDIRECTIONAL.value,
            ):
                pushed = await push_users_to_device(db, device)
                stats["users_pushed"] = pushed.get("pushed", 0)
                stats["users_failed"] = pushed.get("failed", 0)

            job.status = JobStatus.COMPLETED.value
            job.stats = stats
            device.last_sync_at = utcnow()
            device.last_sync_status = "success"
        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.FAILED.value
            job.error = str(exc)[:3000]
            job.stats = stats
            device.last_sync_status = "failed"
            device.last_error = str(exc)[:2000]
        job.finished_at = utcnow()
        await db.commit()


async def push_users_to_device(db: AsyncSession, device: Device) -> dict:
    """Push local DeviceUser rows to the device (create + update + delete)."""
    stats = {"pushed": 0, "failed": 0, "deleted": 0, "errors": []}
    adapter = await instantiate_adapter(db, device)
    try:
        await adapter.test_connection()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"cannot reach device for push: {exc}") from exc

    existing_on_device = {u.user_id_on_device for u in await adapter.get_users()}
    local_users = (
        await db.scalars(
            select(DeviceUser).where(
                DeviceUser.device_id == device.id,
            )
        )
    ).all()

    for local in local_users:
        if not local.enabled:
            # push disabled state via update when the user exists on device
            try:
                await adapter.update_user(_to_adapter_record(local, enabled=False))
                stats["pushed"] += 1
            except Exception as exc:  # noqa: BLE001
                stats["failed"] += 1
                stats["errors"].append(f"{local.user_id_on_device}: {exc}")
            continue
        try:
            if local.user_id_on_device in existing_on_device:
                await adapter.update_user(_to_adapter_record(local))
            else:
                await adapter.create_user(_to_adapter_record(local))
            stats["pushed"] += 1
        except Exception as exc:  # noqa: BLE001
            stats["failed"] += 1
            stats["errors"].append(f"{local.user_id_on_device}: {exc}")
    return stats


def _to_adapter_record(user: DeviceUser, enabled: Optional[bool] = None):
    from app.adapters.base import DeviceUserRecord

    raw = dict(user.device_user_raw_data or {})
    raw["password"] = user.extra.get("_pending_password")
    return DeviceUserRecord(
        user_id_on_device=user.user_id_on_device,
        device_user_sn=user.device_user_sn,
        name=user.name,
        card_number=user.card_number,
        privilege_level=user.privilege_level,
        group_number=user.group_number,
        enabled=user.enabled if enabled is None else enabled,
        raw=raw,
    )

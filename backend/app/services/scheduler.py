"""Built-in scheduler and real-time monitor.

A single asyncio loop wakes periodically and asks the database what is due
(scan intervals, per-device sync intervals, stale online detection, raw-data
retention).  All work is dispatched through the normal job services so state
remains inspectable in the dashboard.  One instance should run scheduler
tasks; with multiple API workers set SCHEDULER_ENABLED=false on all but one
(or move to a Celery beat worker later).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import get_session_factory
from app.models import Device, DiscoveryJob, DeviceNetwork
from app.models.base import utcnow
from app.models.enums import DeviceStatus
from app.services import discovery_service, sync_service
from app.services.settings_store import get_setting

logger = logging.getLogger("freebuff.scheduler")

_last_scan_run: dict = {}
_running = False
_task = None


async def _due(interval_min: int, key: str) -> bool:
    if interval_min <= 0:
        return False
    last = _last_scan_run.get(key)
    now = datetime.now()
    if last is None:
        _last_scan_run[key] = now
        return True
    if now - last >= timedelta(minutes=interval_min):
        _last_scan_run[key] = now
        return True
    return False


async def _scheduler_tick() -> None:
    sf = get_session_factory()
    try:
        async with sf() as db:
            enabled = await get_setting(db, "scheduler.enabled", True)
            if not enabled:
                return
            scan_interval = int(
                await get_setting(db, "scheduler.scan_interval_min", 60)
            )
            # periodic network scans
            if await _due(scan_interval, "scan_all") and scan_interval > 0:
                nets = await discovery_service.list_networks(db)
                enabled_nets = [n for n in nets if n.enabled]
                # only one scan job at a time
                running = (
                    await db.scalars(
                        select(DiscoveryJob).where(
                            DiscoveryJob.status.in_(
                                ["PENDING", "RUNNING"]
                            )
                        )
                    )
                ).all()
                if not running and enabled_nets:
                    job = await discovery_service.create_discovery_job(
                        db, "all", requested_by="scheduler"
                    )
                    discovery_service.start_job_in_background(job.id)

            # per-device auto-sync
            devices = (
                await db.scalars(
                    select(Device).where(Device.auto_sync_enabled.is_(True))
                )
            ).all()
            for device in devices:
                interval = device.sync_interval_min or int(
                    await get_setting(db, "sync.default_interval_min", 5)
                )
                if interval <= 0:
                    continue
                await _sync_if_due(db, device, interval)

            # stale online -> offline
            await _mark_stale(db)
    except Exception:  # noqa: BLE001
        logger.exception("scheduler tick failed")


async def _sync_if_due(db, device: Device, interval_min: int) -> None:
    now = datetime.now()
    if device.last_sync_at is None:
        due = True
    else:
        due = now - device.last_sync_at >= timedelta(minutes=interval_min)
    if not due:
        return
    running = (
        await db.scalar(
            select(sync_service.SyncJob.id)
            .where(
                sync_service.SyncJob.device_id == device.id,
                sync_service.SyncJob.status.in_(["PENDING", "RUNNING"]),
            )
            .limit(1)
        )
    )
    if running:
        return
    job = await sync_service.create_sync_job(
        db,
        device.id,
        "device_to_server",
        scope="logs",
        requested_by="scheduler",
    )
    sync_service.start_sync_job(job.id)


async def _mark_stale(db) -> None:
    cutoff = utcnow() - timedelta(minutes=2)
    devices = (
        await db.scalars(
            select(Device).where(
                Device.status.notin_([
                    DeviceStatus.OFFLINE_VERIFIED.value,
                    DeviceStatus.PROBE_UNREACHABLE.value,
                    DeviceStatus.UNKNOWN.value,
                    DeviceStatus.DISABLED.value,
                ]),
                Device.last_seen_at.is_not(None),
                Device.last_seen_at < cutoff,
            )
        )
    ).all()
    for d in devices:
        d.last_offline_at = utcnow()
        if d.status == DeviceStatus.VERIFIED.value:
            d.status = DeviceStatus.OFFLINE_VERIFIED.value
        else:
            d.status = DeviceStatus.PROBE_UNREACHABLE.value
    if devices:
        await db.commit()


async def _run_loop() -> None:
    global _running
    _running = True
    try:
        while _running:
            try:
                await _scheduler_tick()
            except Exception:  # noqa: BLE001
                logger.exception("scheduler error")
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        pass


def start_scheduler() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.get_event_loop().create_task(_run_loop())


def stop_scheduler() -> None:
    global _running, _task
    _running = False
    if _task is not None:
        _task.cancel()

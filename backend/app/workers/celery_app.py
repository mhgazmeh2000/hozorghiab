"""Celery application bootstrap.

Architecture (production)
-------------------------
* API processes create rows in ``discovery_jobs`` / ``sync_jobs`` and dispatch
  the corresponding Celery task.
* Celery workers pull tasks from Redis, acquire a DB session, and call the
  existing ``execute_*_job`` service functions -- the same code paths used by
  the built-in dev runner, so behavior is identical.
* Celery Beat (scheduler) enqueues periodic scan/sync tasks when the built-in
  scheduler is disabled (which is required for production).

In development with ``TASK_RUNNER=builtin`` the same services run in-process
via ``job_runner.submit`` -- Celery is imported lazily and not used.
"""
from __future__ import annotations

import asyncio
import logging

from celery import Celery

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "freebuff",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_default_queue="freebuff",
    result_expires=3600,
)
# Load the beat schedule (only used by the beat process).
try:
    from app.workers.celery_beat_schedule import beat_schedule as _bs
    celery_app.conf.beat_schedule = _bs
except Exception:  # noqa: BLE001
    logger.exception("failed to load celery beat schedule")

# Register task modules so Celery discovers them.
celery_app.autodiscover_tasks(["app.workers"], force=True)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task worker thread."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="freebuff.execute_sync_job", bind=True, max_retries=2)
def execute_sync_job_task(self, job_id: str):
    """Run a sync job (pull/push users + attendance) via Celery."""
    from app.database import get_session_factory  # local import to avoid circular
    from app.models import SyncJob
    from app.services import sync_service
    from app.models.base import utcnow
    from sqlalchemy import select

    async def _run():
        sf = get_session_factory()
        async with sf() as db:
            job = await db.get(SyncJob, job_id)
            if job is None:
                logger.warning("sync job %s not found; skipping", job_id)
                return
            # Delegate to the existing service function (same as builtin runner).
            await sync_service.execute_sync_job(job_id)

    try:
        return _run_async(_run())
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync job %s failed", job_id)
        # Mark job FAILED
        async def _mark_failed():
            from app.database import get_session_factory
            from app.models import SyncJob
            from app.models.base import utcnow
            from app.models.enums import JobStatus

            sf = get_session_factory()
            async with sf() as db:
                job = await db.get(SyncJob, job_id)
                if job is not None and job.status not in (
                    JobStatus.COMPLETED.value,
                    JobStatus.FAILED.value,
                ):
                    job.status = JobStatus.FAILED.value
                    job.error = str(exc)[:3000]
                    job.finished_at = utcnow()
                    await db.commit()

        try:
            _run_async(_mark_failed())
        except Exception:  # noqa: BLE001
            logger.exception("failed to mark sync job %s as failed", job_id)
        # Retry transient errors a couple of times.
        raise self.retry(exc=exc, countdown=10)


@celery_app.task(name="freebuff.execute_discovery_job", bind=True, max_retries=1)
def execute_discovery_job_task(self, job_id: str):
    """Run a network discovery/scan job via Celery."""
    from app.services import discovery_service

    async def _run():
        await discovery_service.execute_discovery_job(job_id)

    try:
        return _run_async(_run())
    except Exception as exc:  # noqa: BLE001
        logger.exception("discovery job %s failed", job_id)
        raise self.retry(exc=exc, countdown=15)


@celery_app.task(name="freebuff.scheduled_device_sync")
def scheduled_device_sync_task(device_id: str):
    """Enqueued by beat for per-device periodic sync."""
    from app.database import get_session_factory
    from app.models import Device
    from app.services import sync_service
    from sqlalchemy import select

    async def _run():
        sf = get_session_factory()
        async with sf() as db:
            device = await db.get(Device, device_id)
            if device is None or not device.enabled or not device.auto_sync_enabled:
                return
            job = await sync_service.create_sync_job(
                db, device_id, "device_to_server", scope="logs",
                requested_by="scheduler",
            )
            await db.commit()
            await sync_service.execute_sync_job(job.id)

    try:
        _run_async(_run())
    except Exception:  # noqa: BLE001
        logger.exception("scheduled sync failed for device %s", device_id)


@celery_app.task(name="freebuff.scheduled_network_scan")
def scheduled_network_scan_task(target: str = "all"):
    """Enqueued by beat for periodic network discovery."""
    from app.database import get_session_factory
    from app.services import discovery_service

    async def _run():
        sf = get_session_factory()
        async with sf() as db:
            job = await discovery_service.create_discovery_job(
                db, target, requested_by="scheduler"
            )
            await db.commit()
            await discovery_service.execute_discovery_job(job.id)

    try:
        _run_async(_run())
    except Exception:  # noqa: BLE001
        logger.exception("scheduled network scan failed")


@celery_app.task(name="freebuff.device_sync_watchdog")
def device_sync_watchdog_task():
    """Dispatch auto-sync for devices whose sync is due."""
    from datetime import timedelta

    from app.database import get_session_factory
    from app.models import Device
    from app.models.enums import JobStatus
    from app.services import sync_service
    from sqlalchemy import select

    async def _run():
        from app.services.settings_store import get_setting

        sf = get_session_factory()
        async with sf() as db:
            default_interval = int(
                await get_setting(db, "sync.default_interval_min", 5)
            )
            devices = (await db.scalars(
                select(Device).where(Device.auto_sync_enabled.is_(True), Device.enabled.is_(True))
            )).all()
            from app.models.base import utcnow
            now = utcnow()
            for d in devices:
                interval = d.sync_interval_min or default_interval
                if interval <= 0:
                    continue
                if d.last_sync_at and now - d.last_sync_at < timedelta(minutes=interval):
                    continue
                # Avoid duplicate running jobs for this device
                running = (await db.scalar(
                    select(sync_service.SyncJob.id)
                    .where(
                        sync_service.SyncJob.device_id == d.id,
                        sync_service.SyncJob.status.in_([JobStatus.PENDING.value, JobStatus.RUNNING.value]),
                    )
                    .limit(1)
                ))
                if running:
                    continue
                job = await sync_service.create_sync_job(
                    db, d.id, "device_to_server", scope="logs",
                    requested_by="scheduler",
                )
                await db.commit()
                execute_sync_job_task.delay(job.id)

    try:
        _run_async(_run())
    except Exception:  # noqa: BLE001
        logger.exception("device sync watchdog failed")


app = celery_app  # alias expected by ``celery -A app.workers.celery_app``

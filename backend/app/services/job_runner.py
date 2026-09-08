"""Background job execution.

Two dispatch modes (selected via ``settings.task_runner``):

* ``builtin`` -- single-process asyncio task pool living inside the API
  process. Used for local development / single-node deployments. Job state
  is always persisted in the DB so restarts are safe.
* ``celery``  -- Redis-backed Celery worker pool. The API only enqueues the
  task; execution happens in one or more worker containers. This mode is
  the only supported production configuration because it scales horizontally
  and survives API replica restarts.

Both modes end up calling the same ``execute_sync_job`` /
``execute_discovery_job`` service functions, so the code path is identical.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_tasks: dict[str, asyncio.Task] = {}


def _is_celery() -> bool:
    return settings.task_runner == "celery"


def submit_sync_job(job_id: str) -> None:
    """Dispatch a sync job by id."""
    if _is_celery():
        # Local import so dev mode doesn't require celery to be fully wired.
        from app.workers.celery_app import execute_sync_job_task

        execute_sync_job_task.delay(job_id)
        return
    submit(job_id, lambda: _execute_sync(job_id))


def submit_discovery_job(job_id: str) -> None:
    """Dispatch a discovery job by id."""
    if _is_celery():
        from app.workers.celery_app import execute_discovery_job_task

        execute_discovery_job_task.delay(job_id)
        return
    submit(job_id, lambda: _execute_discovery(job_id))


async def _execute_sync(job_id: str) -> None:
    from app.services import sync_service

    await sync_service.execute_sync_job(job_id)


async def _execute_discovery(job_id: str) -> None:
    from app.services import discovery_service

    await discovery_service.execute_discovery_job(job_id)


def submit(job_id: str, coro_factory: Callable[[], Awaitable[None]]) -> None:
    """Start a tracked in-process background task (builtin mode / internal use)."""

    async def wrapper():
        try:
            await coro_factory()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("background job %s crashed", job_id)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("no running loop; cannot schedule job %s in-process", job_id)
        return
    task = loop.create_task(wrapper())
    _tasks[job_id] = task
    task.add_done_callback(lambda t: _tasks.pop(job_id, None))


def cancel(job_id: str) -> bool:
    task = _tasks.get(job_id)
    if task is None:
        return False
    task.cancel()
    return True


def running_jobs() -> list[str]:
    return [jid for jid, t in _tasks.items() if not t.done()]


def wait_job(job_id: str, timeout_s: float = 120.0) -> Optional[bool]:
    """Synchronous wait helper (tests only)."""
    import time

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        task = _tasks.get(job_id)
        if task is None:
            return True
        if task.done():
            return not task.cancelled()
        time.sleep(0.1)
    return None

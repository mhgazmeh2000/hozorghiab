"""Background job execution (built-in runner).

Design choice (documented in ARCHITECTURE.md): the default ``task_runner`` is
``builtin`` - a single-process asyncio task pool living inside the API
process.  Rationale: the operations are I/O-bound network calls (scan/sync),
not CPU work, and a single-node deployment does not need a broker.  The
persistence layer (discovery_jobs / sync_jobs) is broker-agnostic so a Celery
worker can be dropped in later behind the same service functions - the
service functions in this package accept only (job_id) and do all DB writes
themselves.

Only job *execution* is in-process; job *state* is always in PostgreSQL, so a
restart is safe and the dashboard shows history.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger("freebuff.jobs")

_tasks: dict[str, asyncio.Task] = {}


def submit(job_id: str, coro_factory: Callable[[], Awaitable[None]]) -> None:
    """Start a tracked background task for a persisted job id."""

    async def wrapper():
        try:
            await coro_factory()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("background job %s crashed", job_id)

    task = asyncio.get_event_loop().create_task(wrapper())
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

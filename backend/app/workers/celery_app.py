"""Celery application bootstrap.

The current job services remain broker-agnostic and use the built-in runner in
local development. This app provides the deployment hook for migrating those
services to Celery tasks without changing API contracts.
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "freebuff",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
)

# Keep the module-level name expected by `celery -A app.workers.celery_app`.
app = celery_app

"""Celery Beat periodic schedule.

Only enabled when ENABLE_SCHEDULER is true and task_runner=celery. The API
process never runs the built-in scheduler when Celery is the runner (see
main.py); beat drives all recurring work in production.
"""
from celery.schedules import crontab, schedule

beat_schedule = {
    # Periodic network scans every hour by default. Override with
    # SCHEDULER_SCAN_INTERVAL_MIN in the environment.
    "scan-all-networks": {
        "task": "freebuff.scheduled_network_scan",
        "schedule": schedule(300.0),  # 5 minutes, can be tuned
        "args": ("all",),
        "options": {"expires": 60},
    },
    # Per-device sync is enqueued dynamically based on device settings;
    # a watchdog task every minute picks up devices whose sync is due.
    "device-sync-watchdog": {
        "task": "freebuff.device_sync_watchdog",
        "schedule": schedule(60.0),
        "options": {"expires": 30},
    },
}

# Watchdog task: look up devices that are due for auto-sync and dispatch them.
# This keeps the beat schedule simple while honoring per-device intervals.

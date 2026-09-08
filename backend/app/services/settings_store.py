"""Database-backed system settings (JSON values keyed by name).

Config layered as: env defaults < DB settings.  All runtime-tunable knobs
(scan ports, timeouts, workers, sync intervals, scheduler flags...) live here
so operators change them from the dashboard without redeploying.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as env
from app.models.personnel import SystemSetting

DEFAULTS: dict[str, dict] = {
    "discovery.scan_ports": {
        "value": list(env.default_scan_ports),
        "description": "TCP ports probed during discovery",
    },
    "discovery.connect_timeout_s": {
        "value": env.scan_tcp_connect_timeout_s,
        "description": "TCP connect timeout (seconds)",
    },
    "discovery.read_timeout_s": {
        "value": env.scan_read_timeout_s,
        "description": "Service probe read timeout (seconds)",
    },
    "discovery.max_workers": {
        "value": env.scan_max_workers,
        "description": "Concurrent scan workers",
    },
    "discovery.retries": {
        "value": env.scan_retry_count,
        "description": "TCP probe retries",
    },
    "discovery.enable_icmp": {
        "value": env.enable_icmp,
        "description": "Attempt raw ICMP pings (needs privileges)",
    },
    "sync.default_users": {"value": True, "description": "Sync users by default"},
    "sync.default_logs": {"value": True, "description": "Sync logs by default"},
    "sync.default_interval_min": {
        "value": 5,
        "description": "Default scheduled sync interval (minutes) for auto-sync devices",
    },
    "scheduler.enabled": {
        "value": env.enable_scheduler,
        "description": "Master switch for the built-in scheduler",
    },
    "scheduler.scan_interval_min": {
        "value": 60,
        "description": "How often to re-scan configured networks (0 = disabled)",
    },
    "retention.raw_data_days": {
        "value": 30,
        "description": "How long to keep raw device payloads",
    },
    "retention.audit_days": {
        "value": 365,
        "description": "How long to keep audit logs",
    },
    "realtime.poll_interval_s": {
        "value": env.realtime_poll_interval_s,
        "description": "Poll cadence for real-time monitoring (fallback)",
    },
}


async def ensure_defaults(db: AsyncSession) -> None:
    for key, spec in DEFAULTS.items():
        exists = await db.scalar(select(SystemSetting).where(SystemSetting.key == key))
        if exists is None:
            db.add(
                SystemSetting(
                    key=key, value=spec["value"], description=spec["description"]
                )
            )
    await db.commit()


async def get_setting(db: AsyncSession, key: str, default: Any = None) -> Any:
    row = await db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if row is None:
        spec = DEFAULTS.get(key)
        return spec["value"] if spec is not None else default
    return row.value


async def set_setting(
    db: AsyncSession, key: str, value: Any, description: Optional[str] = None
) -> SystemSetting:
    row = await db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if row is None:
        row = SystemSetting(key=key, value=value, description=description)
        db.add(row)
    else:
        row.value = value
        if description:
            row.description = description
    await db.commit()
    return row


async def get_scan_params(db: AsyncSession) -> dict:
    return {
        "ports": await get_setting(db, "discovery.scan_ports", []),
        "connect_timeout_s": await get_setting(db, "discovery.connect_timeout_s", 1.0),
        "read_timeout_s": await get_setting(db, "discovery.read_timeout_s", 2.0),
        "max_workers": await get_setting(db, "discovery.max_workers", 96),
        "retries": await get_setting(db, "discovery.retries", 0),
        "enable_icmp": await get_setting(db, "discovery.enable_icmp", False),
    }

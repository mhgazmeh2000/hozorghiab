"""Attendance log ingestion (idempotent) and queries."""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import AttendanceRecord
from app.models import AttendanceLog, Device, DeviceUser
from app.services.device_service import run_adapter_op


def build_fingerprint(
    device_id: str,
    device_event_id: Optional[str],
    user_id_on_device: Optional[str],
    event_time: Optional[datetime],
    verification_type: Optional[str],
    raw_state: Optional[str] = None,
    raw_punch: Optional[str] = None,
) -> str:
    """Deterministic unique key for one attendance event.

    Prefers a real device event id when present; otherwise the documented
    combination (device, user, time, verify type).
    """
    if device_event_id:
        raw = f"{device_id}:evt:{device_event_id}"
    else:
        raw = "|".join(
            [
                device_id,
                str(user_id_on_device or ""),
                event_time.isoformat() if event_time else "",
                str(verification_type or ""),
                str(raw_state or ""),
                str(raw_punch or ""),
            ]
        )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _record_cursor(record: AttendanceRecord) -> tuple[str, int, str]:
    """Return a stable high-water key without inventing a device event id."""
    timestamp = record.event_time.isoformat() if record.event_time else ""
    raw_time = record.raw.get("_time_enc", 0)
    try:
        raw_time = int(raw_time)
    except (TypeError, ValueError):
        raw_time = 0
    return timestamp, raw_time, str(record.user_id_on_device or "")


async def ingest_attendance_records(
    db: AsyncSession,
    device: Device,
    records: list[AttendanceRecord],
    source: str = "device_pull",
) -> dict:
    """Persist records; duplicates are silently skipped (idempotent)."""
    stats = {"inserted": 0, "duplicates": 0, "invalid": 0}
    # map device user-id -> local user pk for linking
    rows = (
        await db.execute(
            select(DeviceUser.user_id_on_device, DeviceUser.id).where(
                DeviceUser.device_id == device.id
            )
        )
    ).all()
    user_ids = {uid: pk for uid, pk in rows}
    for rec in records:
        if rec.event_time is None and not rec.raw.get("event_code"):
            stats["invalid"] += 1
            continue
        # realtime events have no device-side record id; pull has user_sn + time
        device_event_id = None
        if rec.user_sn is not None and rec.event_time is not None:
            ts_raw = rec.raw.get("_time_enc")
            device_event_id = f"{rec.user_sn}:{ts_raw or int(rec.event_time.timestamp())}"
        fp = build_fingerprint(
            device.id,
            device_event_id,
            rec.user_id_on_device,
            rec.event_time,
            rec.verification_type,
            rec.raw_state,
            rec.raw_punch,
        )
        exists = await db.scalar(
            select(AttendanceLog.id).where(
                AttendanceLog.device_id == device.id,
                AttendanceLog.fingerprint == fp,
            )
        )
        if exists:
            stats["duplicates"] += 1
            continue
        raw = {k: v for k, v in rec.raw.items() if not k.startswith("_raw")}
        raw = _json_safe(raw)
        local_user_id = user_ids.get(rec.user_id_on_device)
        db.add(
            AttendanceLog(
                device_id=device.id,
                fingerprint=fp,
                device_event_id=device_event_id,
                user_id_on_device=rec.user_id_on_device,
                user_sn=rec.user_sn,
                employee_code=rec.user_id_on_device,
                user_id=local_user_id,
                event_time=rec.event_time or datetime.now(),
                raw_state=rec.raw_state,
                raw_punch=rec.raw_punch,
                event_type=rec.event_type or "UNKNOWN",
                verification_type=rec.verification_type or "UNKNOWN",
                status=rec.status,
                work_code=rec.work_code,
                door_id=rec.door_id,
                raw_event=raw,
                source=source,
            )
        )
        stats["inserted"] += 1
    await db.commit()
    return stats


async def pull_attendance_logs(db: AsyncSession, device: Device) -> dict:
    """Pull logs from device and store them."""

    async def _run(adapter):
        return await adapter.get_attendance_logs()

    records = await run_adapter_op(
        db, device, "get_attendance_logs", _run, capability="read_logs"
    )
    sync_state = dict((device.extra_config or {}).get("attendance_sync") or {})
    previous_cursor = tuple(sync_state.get("cursor") or ("", 0, ""))
    if len(previous_cursor) != 3:
        previous_cursor = ("", 0, "")
    records = [record for record in records if _record_cursor(record) > previous_cursor]
    stats = await ingest_attendance_records(db, device, records)
    if records:
        extra_config = dict(device.extra_config or {})
        extra_config["attendance_sync"] = {
            "cursor": list(max(_record_cursor(record) for record in records)),
            "mode": "high_water_mark",
            "updated_at": datetime.utcnow().isoformat(),
        }
        device.extra_config = extra_config
    device.last_sync_at = datetime.utcnow()
    try:
        async def _count(adapter):
            return await adapter.get_attendance_log_count()

        count = await run_adapter_op(
            db, device, "get_attendance_log_count", _count, capability="get_log_count"
        )
        stats["device_count"] = count
        device.extra_config.setdefault("counts", {})["attendance_count"] = count
    except Exception:  # noqa: BLE001
        stats["device_count"] = None
    await db.commit()
    return stats


def _json_safe(value):
    """Make a nested structure JSON-column friendly (drop datetimes)."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def count_today(db: AsyncSession) -> int:
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        (
            await db.scalar(
                select(func.count(AttendanceLog.id)).where(
                    AttendanceLog.event_time >= start
                )
            )
        )
        or 0
    )

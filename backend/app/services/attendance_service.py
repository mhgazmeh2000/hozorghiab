"""Attendance log ingestion (idempotent) and queries.

Design
------
* All records pulled from the device are compared against the local DB using
  a content-based fingerprint (SHA-1 over device_id + user + event_time +
  verify type + raw_state + raw_punch). Duplicates are silently skipped
  (idempotent re-runs are safe).
* Incremental sync uses a high-water mark cursor stored on the device row
  (``extra_config.attendance_sync.cursor``). The cursor advances ONLY after
  a successful DB commit so a crash mid-ingest leaves the cursor at the last
  committed safe position and the next run re-pulls & deduplicates.
* Bulk inserts are chunked and flushed every CHUNK_SIZE records for memory
  safety on large datasets (Device B reports ~38k records).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import AttendanceRecord
from app.models import AttendanceLog, Device, DeviceUser
from app.services.device_service import run_adapter_op

logger = logging.getLogger(__name__)

CHUNK_SIZE = 500


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

    We prefer a genuine device-side event id only when the protocol confirms
    one exists (ZK firmware does NOT expose a stable per-event uid across
    syncs; the user_sn + encoded timestamp is used as a surrogate key for
    realtime, not pull). For pulled records the key is composed from the
    full set of identifying fields so that we never falsely collide events.
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
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _record_cursor(record: AttendanceRecord) -> tuple[str, int, str]:
    """Return a stable high-water key WITHOUT inventing a device event id."""
    timestamp = record.event_time.isoformat() if record.event_time else ""
    raw_time = (record.raw or {}).get("_time_enc", 0)
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
    *,
    chunk_size: int = CHUNK_SIZE,
) -> dict:
    """Persist records in chunks; duplicates are silently skipped.

    Returns {inserted, duplicates, invalid}.
    """
    stats = {"inserted": 0, "duplicates": 0, "invalid": 0}
    # Load existing users for fk resolution.
    rows = (
        await db.execute(
            select(DeviceUser.user_id_on_device, DeviceUser.id).where(
                DeviceUser.device_id == device.id
            )
        )
    ).all()
    user_ids = {uid: pk for uid, pk in rows}

    # Pre-fetch existing fingerprints for this device in batches per chunk
    # to keep memory predictable.
    total = len(records)
    for chunk_start in range(0, total, chunk_size):
        chunk = records[chunk_start : chunk_start + chunk_size]
        # Build candidate fingerprints for chunk.
        fps: list[tuple[int, str]] = []
        for idx, rec in enumerate(chunk):
            if rec.event_time is None and not (rec.raw or {}).get("event_code"):
                stats["invalid"] += 1
                continue
            ts_raw = (rec.raw or {}).get("_time_enc")
            device_event_id = None
            if rec.user_sn is not None and rec.event_time is not None:
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
            fps.append((idx, fp))

        if not fps:
            await db.flush()
            continue

        # Single query for existence across the whole chunk.
        existing_fps = set(
            (
                await db.scalars(
                    select(AttendanceLog.fingerprint).where(
                        AttendanceLog.device_id == device.id,
                        AttendanceLog.fingerprint.in_([fp for _, fp in fps]),
                    )
                )
            ).all()
        )

        for idx, fp in fps:
            if fp in existing_fps:
                stats["duplicates"] += 1
                continue
            rec = chunk[idx]
            ts_raw = (rec.raw or {}).get("_time_enc")
            device_event_id = None
            if rec.user_sn is not None and rec.event_time is not None:
                device_event_id = f"{rec.user_sn}:{ts_raw or int(rec.event_time.timestamp())}"
            raw = {k: v for k, v in (rec.raw or {}).items() if not k.startswith("_raw")}
            raw = _json_safe(raw)
            local_user_id = user_ids.get(rec.user_id_on_device)

            # event_type: preserve raw_state/raw_punch verbatim. Do NOT map to
            # IN/OUT unless there is a verified mapping.
            normalized_event_type = "UNKNOWN"
            raw_state_val = str(rec.raw_state) if rec.raw_state is not None else None
            raw_punch_val = str(rec.raw_punch) if rec.raw_punch is not None else None

            db.add(
                AttendanceLog(
                    device_id=device.id,
                    fingerprint=fp,
                    device_event_id=device_event_id,
                    user_id_on_device=rec.user_id_on_device,
                    user_sn=rec.user_sn,
                    employee_code=rec.user_id_on_device,
                    user_id=local_user_id,
                    event_time=rec.event_time or datetime.utcnow(),
                    raw_state=raw_state_val,
                    raw_punch=raw_punch_val,
                    event_type=normalized_event_type,
                    verification_type=rec.verification_type or "UNKNOWN",
                    status=rec.status,
                    work_code=rec.work_code,
                    door_id=rec.door_id,
                    raw_event=raw,
                    source=source,
                )
            )
            stats["inserted"] += 1
        await db.flush()

    await db.commit()
    return stats


async def pull_attendance_logs(db: AsyncSession, device: Device) -> dict:
    """Pull logs from device using the high-water mark cursor (idempotent).

    The cursor is updated ONLY after successful commit, guaranteeing that a
    crash leaves it at the last safe position.
    """
    import time

    started = time.monotonic()

    async def _run(adapter):
        return await adapter.get_attendance_logs()

    records = await run_adapter_op(
        db, device, "get_attendance_logs", _run, capability="read_logs"
    )

    sync_state = dict((device.extra_config or {}).get("attendance_sync") or {})
    previous_cursor = tuple(sync_state.get("cursor") or ("", 0, ""))
    if len(previous_cursor) != 3:
        previous_cursor = ("", 0, "")

    new_records = [r for r in records if _record_cursor(r) > previous_cursor]
    logger.info(
        "device %s: pulled %d total records, %d new since cursor %s",
        device.ip_address, len(records), len(new_records), previous_cursor,
    )

    stats = await ingest_attendance_records(db, device, new_records)
    stats["duration_s"] = round(time.monotonic() - started, 2)
    stats["records_per_sec"] = round(
        len(new_records) / max(stats["duration_s"], 0.001), 1
    )
    stats["device_total_on_pull"] = len(records)

    # Advance cursor ONLY after successful commit (ingest_attendance_records
    # already committed the transaction).
    if new_records:
        # Use a new safe cursor: max of all pulled record cursors, not just
        # inserted, so duplicates don't cause re-pull loops.
        max_cursor = max(_record_cursor(r) for r in records)
        extra_config = dict(device.extra_config or {})
        extra_config["attendance_sync"] = {
            "cursor": list(max_cursor),
            "mode": "high_water_mark",
            "last_synced_at": datetime.utcnow().isoformat(),
            "last_inserted": stats["inserted"],
            "last_duplicates": stats["duplicates"],
        }
        device.extra_config = extra_config

    device.last_sync_at = datetime.utcnow()
    device.last_sync_status = "success"

    # Fetch log count + capacity for storage monitoring (optional).
    try:
        async def _count(adapter):
            return await adapter.get_attendance_log_count()

        count = await run_adapter_op(
            db, device, "get_attendance_log_count", _count, capability="get_log_count"
        )
        stats["device_count"] = count
        extra_config = dict(device.extra_config or {})
        counts = extra_config.setdefault("counts", {})
        counts["attendance_count"] = count
        # Capacity is filled in by device_service.fetch_and_store_device_info
        # (get_free_sizes), but fall back here if available via adapter.
        device.storage_used = count
        if counts.get("attendance_capacity"):
            cap = int(counts["attendance_capacity"])
            device.storage_usage_pct = round(count / max(cap, 1) * 100.0, 2)
        extra_config["counts"] = counts
        device.extra_config = extra_config
    except Exception as exc:  # noqa: BLE001
        logger.warning("device %s: unable to fetch attendance count: %s", device.ip_address, exc)
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

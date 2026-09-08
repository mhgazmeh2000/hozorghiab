"""Real import/export for users and attendance records.

Import flow is two-phase: (1) upload+validate -> preview with error report,
(2) confirm -> apply within a transaction that rolls back on any row failure.
Files are stored transiently under the configured data dir.
"""
from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AttendanceLog, DeviceUser

ALLOWED_EXT = {".csv", ".xlsx", ".json"}
USER_HEADERS = {
    "user_id_on_device": ("user_id", "uid", "device_user_id"),
    "employee_code": ("employee_code", "emp_code", "code", "employee"),
    "name": ("name", "full_name"),
    "first_name": ("first_name",),
    "last_name": ("last_name",),
    "card_number": ("card_number", "card", "cardno"),
    "department": ("department", "dept"),
    "role": ("role",),
    "enabled": ("enabled", "active", "status"),
}
LOG_HEADERS = {
    "user_id_on_device": ("user_id", "employee_code", "code"),
    "employee_code": ("employee_code",),
    "event_time": ("event_time", "time", "datetime", "timestamp", "date"),
    "event_type": ("event_type", "type", "state"),
    "verification_type": ("verification_type", "verify", "method"),
}


def uploads_dir() -> str:
    d = os.path.join(os.getcwd(), "data", "imports")
    os.makedirs(d, exist_ok=True)
    return d


def save_import_file(filename: str, content: bytes) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f"unsupported file type {ext}; use csv, xlsx or json")
    token = uuid.uuid4().hex
    path = os.path.join(uploads_dir(), f"{token}{ext}")
    with open(path, "wb") as fh:
        fh.write(content)
    return path


def _read_rows(path: str) -> tuple[list[dict], list[str]]:
    ext = os.path.splitext(path)[1].lower()
    errors: list[str] = []
    if ext == ".json":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            data = data.get("rows") or data.get("users") or data.get("records") or []
        if not isinstance(data, list):
            raise ValueError("JSON must contain an array of row objects")
        return [dict(r) for r in data if isinstance(r, dict)], errors
    if ext == ".csv":
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                return [], ["empty file"]
            return [dict(r) for r in reader], errors
    if ext == ".xlsx":
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return [], ["empty sheet"]
        headers = [str(h) if h is not None else "" for h in rows[0]]
        out = []
        for r in rows[1:]:
            out.append({h: v for h, v in zip(headers, r)})
        return out, errors
    raise ValueError("unsupported file type")


def _pick(row: dict, aliases: tuple) -> Optional[str]:
    for alias in aliases:
        for key, value in row.items():
            if key.strip().lower() == alias:
                if value is None:
                    return None
                return str(value).strip()
    return None


def normalize_rows(
    rows: list[dict], schema: dict, entity: str
) -> tuple[list[dict], list[dict]]:
    """Normalize aliased headers; returns (valid_rows, issue_rows)."""
    valid: list[dict] = []
    issues: list[dict] = []
    for i, row in enumerate(rows):
        out: dict = {}
        for field, aliases in schema.items():
            value = _pick(row, aliases)
            if field == "enabled" and value is not None:
                out[field] = value.lower() in ("1", "true", "yes", "active", "enabled")
            elif value is not None:
                out[field] = value
        missing = []
        if entity == "users" and not out.get("user_id_on_device"):
            missing.append("user_id")
        if entity == "logs" and not out.get("event_time"):
            missing.append("event_time")
        if missing:
            issues.append({"row": i + 2, "error": f"missing field(s): {', '.join(missing)}", "data": row})
        else:
            valid.append(out)
    return valid, issues


async def validate_import(db: AsyncSession, path: str, entity: str) -> dict:
    rows, read_errors = _read_rows(path)
    schema = USER_HEADERS if entity == "users" else LOG_HEADERS
    valid, issues = normalize_rows(rows, schema, entity)
    duplicates: list[int] = []
    seen: set = set()
    for v in valid:
        key = v.get("user_id_on_device") or v.get("event_time") or v.get("employee_code")
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    return {
        "entity": entity,
        "total_rows": len(rows),
        "valid_rows": len(valid),
        "issue_rows": len(issues),
        "duplicate_rows": len(duplicates),
        "preview": valid[:50],
        "issues": issues[:200],
        "read_errors": read_errors,
    }


async def apply_import(
    db: AsyncSession, path: str, entity: str, device_id: Optional[str] = None
) -> dict:
    """Transactional apply; rolls back entirely if any row fails."""
    rows, _ = _read_rows(path)
    schema = USER_HEADERS if entity == "users" else LOG_HEADERS
    valid, issues = normalize_rows(rows, schema, entity)
    if issues:
        raise ValueError(f"validation failed for {len(issues)} rows")

    from sqlalchemy.exc import IntegrityError

    applied = 0
    try:
        for item in valid:
            if entity == "users":
                if not device_id:
                    raise ValueError("device_id is required to import users")
                existing = await db.scalar(
                    select(DeviceUser).where(
                        DeviceUser.device_id == device_id,
                        DeviceUser.user_id_on_device == item["user_id_on_device"],
                    )
                )
                if existing is None:
                    existing = DeviceUser(
                        device_id=device_id,
                        user_id_on_device=item["user_id_on_device"],
                    )
                    db.add(existing)
                for field in (
                    "employee_code", "name", "first_name", "last_name",
                    "card_number", "department", "role",
                ):
                    if item.get(field):
                        setattr(existing, field, item[field])
                if "enabled" in item:
                    existing.enabled = item["enabled"]
            else:
                if not device_id:
                    raise ValueError("device_id is required to import logs")
                from app.services.attendance_service import build_fingerprint

                try:
                    event_time = datetime.fromisoformat(
                        item["event_time"].replace("Z", "+00:00")
                    )
                except ValueError as exc:
                    raise ValueError(f"bad event_time {item['event_time']}") from exc
                fp = build_fingerprint(
                    device_id,
                    None,
                    item.get("user_id_on_device"),
                    event_time,
                    item.get("verification_type"),
                )
                exists = await db.scalar(
                    select(AttendanceLog.id).where(
                        AttendanceLog.device_id == device_id,
                        AttendanceLog.fingerprint == fp,
                    )
                )
                if exists:
                    continue
                db.add(
                    AttendanceLog(
                        device_id=device_id,
                        fingerprint=fp,
                        user_id_on_device=item.get("user_id_on_device"),
                        employee_code=item.get("employee_code"),
                        event_time=event_time,
                        event_type=(item.get("event_type") or "UNKNOWN").upper(),
                        verification_type=(
                            item.get("verification_type") or "UNKNOWN"
                        ).upper(),
                        raw_event={},
                        source="import",
                    )
                )
            applied += 1
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return {"applied": applied}


# --------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------


async def export_users(
    db: AsyncSession, device_id: Optional[str], fmt: str, filters: Optional[dict] = None
) -> bytes:
    filters = filters or {}
    stmt = select(DeviceUser)
    if device_id:
        stmt = stmt.where(DeviceUser.device_id == device_id)
    users = (await db.scalars(stmt)).all()
    fields = [
        "user_id_on_device", "employee_code", "name", "first_name", "last_name",
        "card_number", "department", "role", "enabled", "fingerprint_count",
        "card_enabled", "password_status", "last_sync_at",
    ]
    rows = [{f: getattr(u, f) for f in fields} for u in users]
    return _serialize(fmt, rows)


async def export_attendance(
    db: AsyncSession,
    fmt: str,
    device_id: Optional[str] = None,
    employee: Optional[str] = None,
    department: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    event_type: Optional[str] = None,
    verification: Optional[str] = None,
) -> bytes:
    stmt = select(AttendanceLog)
    if device_id:
        stmt = stmt.where(AttendanceLog.device_id == device_id)
    if employee:
        stmt = stmt.where(AttendanceLog.employee_code == employee)
    if department:
        stmt = stmt.join(DeviceUser, AttendanceLog.user_id == DeviceUser.id, isouter=True).where(
            DeviceUser.department == department
        )
    if date_from:
        stmt = stmt.where(AttendanceLog.event_time >= date_from)
    if date_to:
        stmt = stmt.where(AttendanceLog.event_time <= date_to)
    if event_type:
        stmt = stmt.where(AttendanceLog.event_type == event_type.upper())
    if verification:
        stmt = stmt.where(AttendanceLog.verification_type == verification.upper())
    stmt = stmt.order_by(AttendanceLog.event_time.desc()).limit(100000)
    logs = (await db.scalars(stmt)).all()
    fields = [
        "user_id_on_device", "employee_code", "event_time", "event_type",
        "verification_type", "status", "work_code", "door_id", "source",
    ]
    rows = [{f: getattr(l, f) for f in fields} for l in logs]
    return _serialize(fmt, rows)


def _serialize(fmt: str, rows: list[dict]) -> bytes:
    fmt = fmt.lower()
    if fmt == "json":
        return json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8")
    if fmt == "csv":
        if not rows:
            return b""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue().encode("utf-8-sig")
    if fmt in ("xlsx", "excel"):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        if rows:
            ws.append(list(rows[0].keys()))
            for r in rows:
                ws.append([r[k] for k in rows[0].keys()])
        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()
    raise ValueError(f"unsupported export format {fmt}")

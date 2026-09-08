"""Device service: adapter wiring, connection handling, device read ops."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import AttendanceAdapter
from app.adapters.registry import instantiate
from app.core.crypto import decrypt_secret, mask
from app.models import Device, DeviceCredential, DeviceUser
from app.models.base import utcnow
from app.models.enums import DeviceStatus
from app.services.discovery_service import mark_capability_verified


def device_to_cfg(device: Device, credentials: list[DeviceCredential]) -> dict:
    cfg = {
        "ip_address": device.ip_address,
        "port": device.port,
        "connect_timeout_s": device.connect_timeout_s,
        "read_timeout_s": device.read_timeout_s,
        "retry_count": device.retry_count,
        "backoff_base_s": device.backoff_base_s,
        "communication_key": None,
        "snmp_community": None,
        "http_scheme": device.extra_config.get("http_scheme"),
    }
    for cred in credentials:
        if not cred.is_active or not cred.secret_ciphertext:
            continue
        try:
            secret = decrypt_secret(cred.secret_ciphertext)
        except ValueError:
            continue
        if cred.kind == "communication_key":
            cfg["communication_key"] = secret
        elif cred.kind == "snmp_community":
            cfg["snmp_community"] = secret
        elif cred.kind == "password":
            cfg["password"] = secret
            cfg["username"] = cred.username
        elif cred.kind == "api_key":
            cfg["api_key"] = secret
        elif cred.kind == "token":
            cfg["token"] = secret
    return cfg


async def get_device_credentials(db: AsyncSession, device_id: str) -> list[DeviceCredential]:
    return list(
        (
            await db.scalars(
                select(DeviceCredential)
                .where(DeviceCredential.device_id == device_id)
                .order_by(DeviceCredential.created_at)
            )
        ).all()
    )


async def instantiate_adapter(db: AsyncSession, device: Device) -> AttendanceAdapter:
    """Build the right adapter for a device row."""
    adapter_id = device.adapter_name
    if not adapter_id:
        if device.protocol_name == "zk_tcp" or device.port == 4370:
            adapter_id = "zkteco"
        else:
            adapter_id = "generic_http"
    creds = await get_device_credentials(db, device.id)
    cfg = device_to_cfg(device, creds)
    return instantiate(adapter_id, cfg)


async def run_adapter_op(
    db: AsyncSession,
    device: Device,
    op: str,
    func,
    *args,
    capability: Optional[str] = None,
    **kwargs,
):
    """Execute an adapter operation with retries + result handling."""
    import asyncio

    adapter = await instantiate_adapter(db, device)
    last_error: Optional[Exception] = None
    for attempt in range(device.retry_count + 1):
        try:
            result = await func(adapter, *args, **kwargs)
            device.last_error = None
            device.last_seen_at = utcnow()
            await db.flush()
            if capability:
                try:
                    await mark_capability_verified(db, device.id, capability)
                except Exception:  # noqa: BLE001
                    pass
            return result
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            device.last_error = str(exc)[:2000]
            await db.flush()
            if attempt < device.retry_count:
                await asyncio.sleep(device.backoff_base_s * (2 ** attempt))
    raise last_error if last_error else DeviceConnectionErrorUnknown()


class DeviceConnectionErrorUnknown(Exception):
    pass


async def test_device(db: AsyncSession, device: Device) -> dict:
    """Connection test that updates online state."""
    try:
        adapter = await instantiate_adapter(db, device)
        result = await adapter.test_connection()
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "detail": str(exc)[:500]}
    ok = bool(result.get("ok"))
    now = utcnow()
    device.last_seen_at = now
    if ok:
        device.status = DeviceStatus.VERIFIED.value if device.verified_at else DeviceStatus.ONLINE.value
        device.last_online_at = now
        device.last_error = None
    else:
        device.status = DeviceStatus.OFFLINE.value
        device.last_offline_at = now
    await db.commit()
    return result


async def fetch_and_store_device_info(db: AsyncSession, device: Device) -> dict:
    async def _run(adapter):
        info = await adapter.get_device_info()
        return info

    info = await run_adapter_op(
        db, device, "get_device_info", _run, capability="device_info"
    )
    now = utcnow()
    device.brand = info.brand or device.brand
    device.model = info.model or device.model
    device.serial_number = info.serial_number or device.serial_number
    device.firmware_version = info.firmware_version or device.firmware_version
    device.platform = info.platform or device.platform
    device.device_name = info.device_name or device.device_name
    device.vendor = info.vendor or device.vendor
    device.device_id = info.device_id or device.device_id
    device.mac_address = info.mac_address or device.mac_address
    if info.device_time is not None:
        extra_config = dict(device.extra_config or {})
        extra_config["device_time"] = info.device_time.isoformat()
        device.extra_config = extra_config
    device.verified_at = now
    device.status = DeviceStatus.VERIFIED.value
    device.detection_state = "VERIFIED"
    device.confidence = max(device.confidence or 0, 0.99)
    if info.user_count is not None:
        sizes = (info.raw or {}).get("free_sizes") or {}
        extra_config = dict(device.extra_config or {})
        extra_config["counts"] = {
            "user_count": info.user_count,
            "user_capacity": sizes.get("user_capacity"),
            "fingerprint_count": info.fingerprint_count,
            "fingerprint_capacity": sizes.get("fingerprint_capacity"),
            "face_count": info.face_count,
            "face_capacity": sizes.get("face_capacity"),
            "attendance_count": info.attendance_count,
            "attendance_capacity": sizes.get("attendance_capacity"),
            "attendance_free": sizes.get("remaining_attendance"),
        }
        device.extra_config = extra_config
    await db.commit()
    return info.__dict__


async def read_and_store_users(db: AsyncSession, device: Device) -> list[DeviceUser]:
    async def _run(adapter):
        return await adapter.get_users()

    records = await run_adapter_op(
        db, device, "get_users", _run, capability="read_users"
    )
    now = utcnow()
    stored: list[DeviceUser] = []
    for rec in records:
        row = await db.scalar(
            select(DeviceUser).where(
                DeviceUser.device_id == device.id,
                DeviceUser.user_id_on_device == rec.user_id_on_device,
            )
        )
        if row is None:
            row = DeviceUser(device_id=device.id, user_id_on_device=rec.user_id_on_device)
            db.add(row)
        row.device_user_sn = rec.device_user_sn
        row.name = rec.name or rec.name
        row.card_number = rec.card_number
        row.password_status = rec.password_status
        row.privilege_level = rec.privilege_level
        row.role = rec.role
        row.group_number = rec.group_number
        row.enabled = rec.enabled
        row.verification_mode = rec.verification_mode
        row.fingerprint_count = rec.fingerprint_count
        row.card_enabled = bool(rec.card_enabled)
        row.password_enabled = bool(rec.password_enabled)
        row.face_enabled = bool(rec.face_enabled)
        row.employee_code = rec.employee_code or rec.user_id_on_device
        row.device_user_raw_data = rec.raw or {}
        row.last_sync_at = now
        await db.flush()
        stored.append(row)
    device.last_sync_at = now
    await db.commit()
    return stored


async def set_user_sync_fields(
    db: AsyncSession, device_id: str, fields: dict, user_id_on_device: str
) -> None:
    row = await db.scalar(
        select(DeviceUser).where(
            DeviceUser.device_id == device_id,
            DeviceUser.user_id_on_device == user_id_on_device,
        )
    )
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
        await db.commit()

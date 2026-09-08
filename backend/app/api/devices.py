"""Device endpoints: registry, detail, actions, users, attendance, sync."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Audit
from app.core.crypto import encrypt_secret, mask
from app.core.deps import get_current_user, require_roles
from app.database import get_session
from app.models import (
    AttendanceLog,
    AuditLog,
    Device,
    DeviceCapability,
    DeviceCredential,
    DeviceProtocol,
    DeviceRawData,
    DeviceUser,
    SystemUser,
)
from app.models.base import utcnow
from app.models.device import DeviceNetwork
from app.schemas.schemas import (
    AttendanceLogOut,
    DeviceCredentialIn,
    DeviceCredentialOut,
    DeviceCreate,
    DeviceDetailOut,
    DeviceOut,
    DeviceUpdate,
    DeviceUserCreate,
    DeviceUserOut,
    SyncRequest,
)
from app.services import attendance_service, discovery_service, device_service, sync_service

router = APIRouter(prefix="/devices", tags=["devices"])


async def _get_device(db: AsyncSession, device_id: str) -> Device:
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="device not found")
    return device


async def _detail_out(db: AsyncSession, device: Device) -> DeviceDetailOut:
    counts = device.extra_config.get("counts") or {}
    caps = (
        await db.scalars(
            select(DeviceCapability)
            .where(DeviceCapability.device_id == device.id)
            .order_by(DeviceCapability.capability)
        )
    ).all()
    protos = (
        await db.scalars(
            select(DeviceProtocol)
            .where(DeviceProtocol.device_id == device.id)
            .order_by(DeviceProtocol.port)
        )
    ).all()
    out = DeviceDetailOut.model_validate(device)
    out.capabilities = [
        {
            "capability": c.capability,
            "implemented": c.implemented,
            "supported": c.implemented,  # back-compat
            "verified": c.verified,
            "enabled": c.enabled,
            "is_destructive": c.is_destructive,
            "source": c.source,
            "reason": c.reason,
        }
        for c in caps
    ]
    out.protocols = [
        {
            "port": p.port,
            "transport": p.transport,
            "service": p.service,
            "protocol": p.protocol_guess,
            "state": p.protocol_state,
            "confidence": p.confidence,
            "source": p.source,
            "banner": p.banner,
            "http_headers": p.http_headers,
            "title": p.html_title,
            "last_seen_at": p.last_seen_at,
        }
        for p in protos
    ]
    out.user_count = counts.get("user_count")
    out.attendance_count = counts.get("attendance_count")
    out.device_time = device.extra_config.get("device_time")
    return out


@router.get("", response_model=dict)
async def list_devices(
    search: Optional[str] = None,
    status: Optional[str] = None,
    detection_state: Optional[str] = None,
    candidate_only: bool = False,
    adapter: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    stmt = select(Device)
    where = []
    if search:
        like = f"%{search}%"
        where.append(
            or_(
                Device.ip_address.like(like),
                Device.hostname.like(like),
                Device.model.like(like),
                Device.brand.like(like),
                Device.serial_number.like(like),
            )
        )
    if status:
        where.append(Device.status == status)
    if detection_state:
        where.append(Device.detection_state == detection_state)
    if candidate_only:
        where.append(Device.is_attendance_candidate.is_(True))
    if adapter:
        where.append(Device.adapter_name == adapter)
    if where:
        stmt = stmt.where(*where)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (
        await db.scalars(
            stmt.order_by(Device.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
        "items": [DeviceOut.model_validate(d).model_dump() for d in rows],
    }


@router.post("", response_model=DeviceOut, status_code=201)
async def create_device(
    body: DeviceCreate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    from app.discovery.validate import validate_ip

    try:
        validate_ip(body.ip_address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    existing = await db.scalar(select(Device).where(Device.ip_address == body.ip_address))
    if existing:
        raise HTTPException(status_code=409, detail="device with this IP already exists")
    if body.network_cidr:
        net = await db.scalar(
            select(DeviceNetwork).where(DeviceNetwork.cidr == body.network_cidr)
        )
        if net is None:
            raise HTTPException(status_code=400, detail="network_cidr is not configured")
    device = Device(
        ip_address=body.ip_address,
        network_cidr=body.network_cidr,
        hostname=body.hostname,
        port=body.port or (4370 if body.adapter_name == "zkteco" else None),
        adapter_name=body.adapter_name,
        is_manual=True,
    )
    db.add(device)
    await db.flush()
    audit = Audit(db)
    await audit.record(
        "device_config", device_id=device.id, device_ip=device.ip_address,
        details={"action": "manual_add"},
        actor={"username": user.username},
    )
    await db.commit()
    await db.refresh(device)
    return device


@router.get("/{device_id}", response_model=DeviceDetailOut)
async def get_device(
    device_id: str,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    device = await _get_device(db, device_id)
    return await _detail_out(db, device)


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: str,
    body: DeviceUpdate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    device = await _get_device(db, device_id)
    changes = {}
    for field in (
        "hostname", "port", "enabled", "auto_sync_enabled", "sync_interval_min",
        "connect_timeout_s", "read_timeout_s", "retry_count", "adapter_name",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(device, field, value)
            changes[field] = value
    if body.note is not None:
        device.raw_notes = body.note
        changes["note"] = body.note
    if body.adapter_name == "zkteco" and not device.port:
        device.port = 4370
    await db.flush()
    audit = Audit(db)
    await audit.record(
        "device_config", device_id=device.id, device_ip=device.ip_address,
        details={"action": "update", "changes": changes},
        actor={"username": user.username},
    )
    await db.commit()
    return device


@router.delete("/{device_id}")
async def delete_device(
    device_id: str,
    request: Request,
    confirm: bool = Query(False),
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin")),
):
    device = await _get_device(db, device_id)
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="deletion requires confirm=true (also removes users, logs, raw data)",
        )
    await db.delete(device)  # cascades
    audit = Audit(db)
    await audit.record(
        "device_config", result="success", device_id=device.id,
        device_ip=device.ip_address, details={"action": "delete"},
        actor={"username": user.username},
    )
    await db.commit()
    return {"ok": True}


# --- actions ---------------------------------------------------------------


@router.post("/{device_id}/test")
async def test_device(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    device = await _get_device(db, device_id)
    result = await device_service.test_device(db, device)
    audit = Audit(db)
    await audit.record(
        "connect",
        result="success" if result.get("ok") else "error",
        device_id=device.id,
        device_ip=device.ip_address,
        error=None if result.get("ok") else result.get("detail"),
        details={"adapter": device.adapter_name},
        actor={"username": user.username},
    )
    await db.commit()
    return {"device_id": device.id, **result}


@router.post("/{device_id}/discover", response_model=dict, status_code=202)
async def discover_device(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    device = await _get_device(db, device_id)
    job = await discovery_service.create_discovery_job(
        db, f"ip:{device.ip_address}", kind="ip", requested_by=user.username
    )
    await db.commit()
    discovery_service.start_job_in_background(job.id)
    audit = Audit(db)
    await audit.record(
        "discovery", device_id=device.id, device_ip=device.ip_address,
        details={"action": "single_ip", "job_id": job.id},
        actor={"username": user.username},
    )
    await db.commit()
    return {"job_id": job.id, "target": device.ip_address}


@router.post("/{device_id}/refresh-info", response_model=dict)
async def refresh_device_info(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    device = await _get_device(db, device_id)
    try:
        info = await device_service.fetch_and_store_device_info(db, device)
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or exc.__class__.__name__
        device.status = "PROBE_UNREACHABLE"
        device.last_probe_error = detail[:500]
        device.last_error = detail[:2000]
        audit = Audit(db)
        await audit.record(
            "connect", result="error", device_id=device.id,
            device_ip=device.ip_address, error=detail[:2000],
            actor={"username": user.username},
        )
        await db.commit()
        return {"ok": False, "device_id": device.id, "detail": detail[:500]}
    audit = Audit(db)
    await audit.record(
        "connect", result="success", device_id=device.id, device_ip=device.ip_address,
        details={"action": "read_device_info"},
        actor={"username": user.username},
    )
    await db.commit()
    return info


# --- capabilities / protocols / raw / logs ---------------------------------


@router.get("/{device_id}/capabilities")
async def device_capabilities(
    device_id: str,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    device = await _get_device(db, device_id)
    rows = (
        await db.scalars(
            select(DeviceCapability)
            .where(DeviceCapability.device_id == device.id)
            .order_by(DeviceCapability.capability)
        )
    ).all()
    return [
        {
            "capability": c.capability,
            "implemented": c.implemented,
            "supported": c.implemented,  # back-compat
            "verified": c.verified,
            "enabled": c.enabled,
            "is_destructive": c.is_destructive,
            "source": c.source,
            "reason": c.reason,
        }
        for c in rows
    ]


@router.get("/{device_id}/protocols")
async def device_protocols(
    device_id: str,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    device = await _get_device(db, device_id)
    rows = (
        await db.scalars(
            select(DeviceProtocol)
            .where(DeviceProtocol.device_id == device.id)
            .order_by(DeviceProtocol.port)
        )
    ).all()
    return [
        {
            "port": p.port,
            "transport": p.transport,
            "service": p.service,
            "protocol": p.protocol_guess,
            "state": p.protocol_state,
            "confidence": p.confidence,
            "source": p.source,
            "banner": p.banner,
            "http_headers": p.http_headers,
            "title": p.html_title,
            "first_seen_at": p.first_seen_at,
            "last_seen_at": p.last_seen_at,
        }
        for p in rows
    ]


@router.get("/{device_id}/raw-data")
async def device_raw_data(
    device_id: str,
    limit: int = Query(50, le=200),
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    device = await _get_device(db, device_id)
    stmt = (
        select(DeviceRawData)
        .where(DeviceRawData.device_id == device.id)
        .order_by(DeviceRawData.captured_at.desc())
    )
    if category:
        stmt = stmt.where(DeviceRawData.category == category)
    rows = (await db.scalars(stmt.limit(limit))).all()
    return [
        {
            "id": r.id,
            "category": r.category,
            "source": r.source,
            "content_type": r.content_type,
            "payload": r.payload,
            "meta": r.meta,
            "captured_at": r.captured_at,
        }
        for r in rows
    ]


@router.get("/{device_id}/logs")
async def device_logs(
    device_id: str,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    device = await _get_device(db, device_id)
    rows = (
        await db.scalars(
            select(AuditLog)
            .where(AuditLog.device_id == device.id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            "username": r.username,
            "action": r.action,
            "result": r.result,
            "error": r.error,
            "duration_ms": r.duration_ms,
            "details": r.details,
        }
        for r in rows
    ]


# --- credentials -----------------------------------------------------------


@router.get("/{device_id}/credentials", response_model=list[DeviceCredentialOut])
async def list_credentials(
    device_id: str,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin")),
):
    device = await _get_device(db, device_id)
    rows = await device_service.get_device_credentials(db, device.id)
    out = []
    for c in rows:
        item = DeviceCredentialOut.model_validate(c)
        item.secret_masked = (
            mask(device_service.device_to_cfg(device, [c]).get("password")
                 or device_service.device_to_cfg(device, [c]).get("communication_key")
                 or device_service.device_to_cfg(device, [c]).get("snmp_community")
                 or device_service.device_to_cfg(device, [c]).get("api_key")
                 or device_service.device_to_cfg(device, [c]).get("token"))
            if c.secret_ciphertext else None
        )
        out.append(item)
    return out


@router.post("/{device_id}/credentials", response_model=DeviceCredentialOut, status_code=201)
async def create_credential(
    device_id: str,
    body: DeviceCredentialIn,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin")),
):
    device = await _get_device(db, device_id)
    cred = DeviceCredential(
        device_id=device.id,
        kind=body.kind,
        username=body.username,
        secret_ciphertext=encrypt_secret(body.secret),
        note=body.note,
    )
    db.add(cred)
    await db.flush()
    audit = Audit(db)
    await audit.record(
        "device_config", device_id=device.id, device_ip=device.ip_address,
        details={"action": "credential_save", "kind": body.kind},
        actor={"username": user.username},
    )
    await db.commit()
    await db.refresh(cred)
    out = DeviceCredentialOut.model_validate(cred)
    out.secret_masked = mask(body.secret)
    return out


@router.delete("/{device_id}/credentials/{credential_id}")
async def delete_credential(
    device_id: str,
    credential_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin")),
):
    device = await _get_device(db, device_id)
    cred = await db.get(DeviceCredential, credential_id)
    if cred is None or cred.device_id != device.id:
        raise HTTPException(status_code=404, detail="credential not found")
    await db.delete(cred)
    audit = Audit(db)
    await audit.record(
        "device_config", device_id=device.id, device_ip=device.ip_address,
        details={"action": "credential_delete"},
        actor={"username": user.username},
    )
    await db.commit()
    return {"ok": True}


# --- sync ------------------------------------------------------------------


@router.post("/{device_id}/sync", response_model=dict, status_code=202)
async def sync_device(
    device_id: str,
    body: SyncRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    device = await _get_device(db, device_id)
    if body.direction not in ("device_to_server", "server_to_device", "bidirectional"):
        raise HTTPException(status_code=400, detail="invalid direction")
    # server_to_device / bidirectional touch device state; require sync_users_to_device
    # capability to be verified+enabled.
    if body.direction in ("server_to_device", "bidirectional"):
        await device_service.require_capability(db, device, "sync_users_to_device")
    job = await sync_service.create_sync_job(
        db, device.id, body.direction, body.scope, requested_by=user.username
    )
    await db.commit()
    sync_service.start_sync_job(job.id)
    audit = Audit(db)
    await audit.record(
        "sync", device_id=device.id, device_ip=device.ip_address,
        details={"job_id": job.id, "direction": body.direction, "scope": body.scope},
        actor={"username": user.username},
    )
    await db.commit()
    return {"job_id": job.id, "direction": body.direction}


@router.get("/sync/jobs")
async def list_sync_jobs(
    device_id: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    from app.models.jobs import SyncJob

    stmt = select(SyncJob).order_by(SyncJob.created_at.desc())
    if device_id:
        stmt = stmt.where(SyncJob.device_id == device_id)
    rows = (await db.scalars(stmt.limit(limit))).all()
    return [
        {
            "id": r.id,
            "device_id": r.device_id,
            "direction": r.direction,
            "scope": r.scope,
            "requested_by": r.requested_by,
            "status": r.status,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "error": r.error,
            "stats": r.stats,
            "created_at": r.created_at,
        }
        for r in rows
    ]


# --- device users -----------------------------------------------------------


@router.get("/{device_id}/users", response_model=dict)
async def list_device_users(
    device_id: str,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    device = await _get_device(db, device_id)
    stmt = select(DeviceUser).where(DeviceUser.device_id == device.id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(
                DeviceUser.user_id_on_device.like(like),
                DeviceUser.name.like(like),
                DeviceUser.employee_code.like(like),
                DeviceUser.card_number.like(like),
            )
        )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (
        await db.scalars(
            stmt.order_by(DeviceUser.user_id_on_device)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
        "items": [DeviceUserOut.model_validate(r).model_dump() for r in rows],
    }


@router.post("/{device_id}/users", response_model=dict, status_code=201)
async def create_device_user(
    device_id: str,
    body: DeviceUserCreate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    device = await _get_device(db, device_id)
    from app.adapters.base import DeviceUserRecord

    rec = DeviceUserRecord(
        user_id_on_device=body.user_id_on_device,
        employee_code=body.employee_code or body.user_id_on_device,
        name=body.name,
        first_name=body.first_name,
        last_name=body.last_name,
        card_number=body.card_number,
        privilege_level=body.privilege_level,
        group_number=body.group_number,
        enabled=body.enabled,
        raw={"password": body.password or ""},
    )
    # Guard: create_users capability must be verified+enabled (destructive).
    await device_service.require_capability(db, device, "create_users")
    # write to device first
    try:
        adapter = await device_service.instantiate_adapter(db, device)
        result = await adapter.create_user(rec)
        await discovery_service.mark_capability_verified(db, device.id, "create_users")
    except Exception as exc:  # noqa: BLE001
        audit = Audit(db)
        await audit.record(
            "user_create", result="error", device_id=device.id,
            device_ip=device.ip_address, error=str(exc)[:2000],
            details={"user_id": body.user_id_on_device},
            actor={"username": user.username},
        )
        await db.commit()
        raise HTTPException(status_code=502, detail=f"device rejected user: {exc}") from exc
    # store locally
    row = await db.scalar(
        select(DeviceUser).where(
            DeviceUser.device_id == device.id,
            DeviceUser.user_id_on_device == body.user_id_on_device,
        )
    )
    if row is None:
        row = DeviceUser(device_id=device.id, user_id_on_device=body.user_id_on_device)
        db.add(row)
    row.employee_code = body.employee_code or body.user_id_on_device
    row.name = body.name
    row.first_name = body.first_name
    row.last_name = body.last_name
    row.card_number = body.card_number
    row.privilege_level = body.privilege_level
    row.group_number = body.group_number
    row.enabled = body.enabled
    row.last_sync_at = utcnow()
    await db.flush()
    audit = Audit(db)
    await audit.record(
        "user_create", device_id=device.id, device_ip=device.ip_address,
        details={"user_id": body.user_id_on_device, "device_result": result},
        actor={"username": user.username},
    )
    await db.commit()
    return {"ok": True, "device_result": result, "user_id": body.user_id_on_device}


@router.patch("/{device_id}/users/{user_pk}", response_model=dict)
async def update_device_user(
    device_id: str,
    user_pk: str,
    body: DeviceUserCreate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    device = await _get_device(db, device_id)
    row = await db.get(DeviceUser, user_pk)
    if row is None or row.device_id != device.id:
        raise HTTPException(status_code=404, detail="user not found")
    await device_service.require_capability(db, device, "update_users")
    from app.adapters.base import DeviceUserRecord

    rec = DeviceUserRecord(
        user_id_on_device=body.user_id_on_device or row.user_id_on_device,
        device_user_sn=row.device_user_sn,
        name=body.name if body.name is not None else row.name,
        card_number=body.card_number if body.card_number is not None else row.card_number,
        privilege_level=body.privilege_level if body.privilege_level is not None else row.privilege_level,
        group_number=body.group_number if body.group_number is not None else row.group_number,
        enabled=body.enabled,
        raw=dict(row.device_user_raw_data or {})
        | ({"password": body.password} if body.password else {}),
    )
    try:
        adapter = await device_service.instantiate_adapter(db, device)
        await adapter.update_user(rec)
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"device rejected update: {exc}") from exc
    for field, value in (
        ("name", body.name), ("employee_code", body.employee_code),
        ("card_number", body.card_number), ("privilege_level", body.privilege_level),
        ("group_number", body.group_number), ("enabled", body.enabled),
        ("first_name", body.first_name), ("last_name", body.last_name),
        ("department", body.department), ("role", body.role),
    ):
        if value is not None:
            setattr(row, field, value)
    row.last_sync_at = utcnow()
    await db.flush()
    audit = Audit(db)
    await audit.record(
        "user_update", device_id=device.id, device_ip=device.ip_address,
        details={"user_id": row.user_id_on_device},
        actor={"username": user.username},
    )
    await db.commit()
    return {"ok": True}


@router.delete("/{device_id}/users/{user_pk}")
async def delete_device_user(
    device_id: str,
    user_pk: str,
    request: Request,
    confirm: bool = Query(False),
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    device = await _get_device(db, device_id)
    row = await db.get(DeviceUser, user_pk)
    if row is None or row.device_id != device.id:
        raise HTTPException(status_code=404, detail="user not found")
    if not confirm:
        raise HTTPException(status_code=400, detail="deletion requires confirm=true (destructive)")
    await device_service.require_capability(db, device, "delete_users")
    try:
        adapter = await device_service.instantiate_adapter(db, device)
        await adapter.delete_user(row.user_id_on_device)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"device rejected deletion: {exc}") from exc
    await db.delete(row)
    audit = Audit(db)
    await audit.record(
        "destructive_write", device_id=device.id, device_ip=device.ip_address,
        details={"user_id": row.user_id_on_device},
        actor={"username": user.username},
    )
    await db.commit()
    return {"ok": True}


@router.post("/{device_id}/users/sync-from-device", response_model=dict, status_code=202)
async def sync_users_from_device(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    device = await _get_device(db, device_id)
    job = await sync_service.create_sync_job(
        db, device.id, "device_to_server", scope="users", requested_by=user.username
    )
    await db.commit()
    sync_service.start_sync_job(job.id)
    return {"job_id": job.id}


@router.post("/{device_id}/users/sync-to-device", response_model=dict, status_code=202)
async def sync_users_to_device(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    device = await _get_device(db, device_id)
    job = await sync_service.create_sync_job(
        db, device.id, "server_to_device", scope="users", requested_by=user.username
    )
    await db.commit()
    sync_service.start_sync_job(job.id)
    return {"job_id": job.id}


# --- attendance -------------------------------------------------------------


@router.get("/{device_id}/attendance", response_model=dict)
async def list_device_attendance(
    device_id: str,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    employee: Optional[str] = None,
    event_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(get_current_user),
):
    device = await _get_device(db, device_id)
    stmt = select(AttendanceLog).where(AttendanceLog.device_id == device.id)
    if date_from:
        stmt = stmt.where(AttendanceLog.event_time >= date_from)
    if date_to:
        stmt = stmt.where(AttendanceLog.event_time <= date_to)
    if employee:
        stmt = stmt.where(AttendanceLog.employee_code == employee)
    if event_type:
        stmt = stmt.where(AttendanceLog.event_type == event_type.upper())
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (
        await db.scalars(
            stmt.order_by(AttendanceLog.event_time.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
        "items": [AttendanceLogOut.model_validate(r).model_dump() for r in rows],
    }


@router.post("/{device_id}/attendance/pull", response_model=dict, status_code=202)
async def pull_attendance(
    device_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin", "operator")),
):
    device = await _get_device(db, device_id)
    job = await sync_service.create_sync_job(
        db, device.id, "device_to_server", scope="logs", requested_by=user.username
    )
    await db.commit()
    sync_service.start_sync_job(job.id)
    return {"job_id": job.id}


@router.post("/{device_id}/attendance/clear")
async def clear_attendance(
    device_id: str,
    request: Request,
    confirm: bool = Query(False),
    db: AsyncSession = Depends(get_session),
    user: SystemUser = Depends(require_roles("admin")),
):
    device = await _get_device(db, device_id)
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="clearing device attendance logs requires confirm=true (destructive, irreversible)",
        )
    await device_service.require_capability(db, device, "delete_logs")
    try:
        adapter = await device_service.instantiate_adapter(db, device)
        result = await adapter.clear_attendance_logs()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"device rejected: {exc}") from exc
    audit = Audit(db)
    await audit.record(
        "destructive_write", device_id=device.id, device_ip=device.ip_address,
        result="success", details={"op": "clear_attendance", **result},
        actor={"username": user.username},
    )
    await db.commit()
    return result

"""Discovery service: network CRUD, scan/sync job orchestration + persistence."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.registry import get_adapter_class
from app.database import get_session_factory
from app.discovery.engine import (
    build_host_list,
    discover_host,
    discover_many,
)
from app.discovery.validate import network_hosts, validate_cidr, validate_ip
from app.models import Device, DeviceCapability, DeviceNetwork, DeviceProtocol
from app.models.base import utcnow
from app.models.device import DeviceRawData
from app.models.enums import (
    DetectionState,
    DeviceStatus,
    DiscoveryStage,
    JobStatus,
)
from app.models.jobs import DiscoveryJob, DiscoveryResult
from app.services import job_runner
from app.services.settings_store import get_scan_params

CAPABILITY_KEYS = [
    "device_info", "read_users", "read_user", "create_users", "update_users",
    "delete_users", "read_logs", "delete_logs", "get_log_count",
    "sync_users_to_device", "sync_users_from_device", "realtime_events",
    "fingerprint", "face", "card", "password", "set_time", "get_time",
    "clear_data", "read_templates", "write_templates",
    "read_operational_logs",
]


# --------------------------------------------------------------------------
# Networks
# --------------------------------------------------------------------------


async def list_networks(db: AsyncSession) -> list[DeviceNetwork]:
    return list(
        (await db.scalars(select(DeviceNetwork).order_by(DeviceNetwork.cidr))).all()
    )


async def get_network(db: AsyncSession, network_id: str) -> Optional[DeviceNetwork]:
    return await db.get(DeviceNetwork, network_id)


async def add_network(
    db: AsyncSession,
    cidr: str,
    label: Optional[str] = None,
    exclude_ips: Optional[list[str]] = None,
    note: Optional[str] = None,
) -> DeviceNetwork:
    validate_cidr(cidr)
    existing = await db.scalar(
        select(DeviceNetwork).where(DeviceNetwork.cidr == cidr)
    )
    if existing:
        raise ValueError(f"network {cidr} already configured")
    net = DeviceNetwork(
        cidr=cidr,
        label=label,
        exclude_ips=[x.strip() for x in (exclude_ips or []) if x.strip()],
        note=note,
        is_single_ip="/" not in cidr or validate_cidr(cidr).num_addresses == 1,
        is_default=False,
    )
    db.add(net)
    await db.commit()
    await db.refresh(net)
    return net


async def update_network(
    db: AsyncSession,
    network_id: str,
    *,
    cidr: Optional[str] = None,
    label: Optional[str] = None,
    exclude_ips: Optional[list[str]] = None,
    enabled: Optional[bool] = None,
    note: Optional[str] = None,
) -> DeviceNetwork:
    net = await get_network(db, network_id)
    if net is None:
        raise ValueError("network not found")
    if cidr and cidr != net.cidr:
        validate_cidr(cidr)
        net.cidr = cidr
    if label is not None:
        net.label = label
    if exclude_ips is not None:
        net.exclude_ips = [x.strip() for x in exclude_ips if x.strip()]
    if enabled is not None:
        net.enabled = enabled
    if note is not None:
        net.note = note
    await db.commit()
    await db.refresh(net)
    return net


async def delete_network(db: AsyncSession, network_id: str) -> None:
    net = await get_network(db, network_id)
    if net is None:
        raise ValueError("network not found")
    await db.delete(net)
    await db.commit()


# --------------------------------------------------------------------------
# Job lifecycle
# --------------------------------------------------------------------------


async def create_discovery_job(
    db: AsyncSession,
    target: str,
    kind: str = "scan",
    requested_by: Optional[str] = None,
    params: Optional[dict] = None,
) -> DiscoveryJob:
    job = DiscoveryJob(
        kind=kind,
        target=target,
        requested_by=requested_by,
        params=params or {},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_job(db: AsyncSession, job_id: str) -> Optional[DiscoveryJob]:
    return await db.get(DiscoveryJob, job_id)


def start_job_in_background(job_id: str) -> None:
    """Dispatch a discovery job via the configured runner (builtin/celery)."""
    job_runner.submit_discovery_job(job_id)


async def execute_discovery_job(job_id: str) -> None:
    """Runs a persisted DiscoveryJob to completion (safe to call in worker)."""
    sf = get_session_factory()
    async with sf() as db:
        job = await db.get(DiscoveryJob, job_id)
        if job is None:
            return
        job.status = JobStatus.RUNNING.value
        job.started_at = utcnow()
        job.stage = DiscoveryStage.SCANNING.value
        await db.commit()
        try:
            hosts, cidr_for_results = await _resolve_targets(db, job)
        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.FAILED.value
            job.error = str(exc)[:2000]
            job.finished_at = utcnow()
            job.stage = DiscoveryStage.FAILED.value
            await db.commit()
            return

        job.total_hosts = len(hosts)
        job.progress = 0.0
        await db.commit()

        params = await get_scan_params(db)
        ports = [int(p) for p in params["ports"]]

        async def progress(done: int, total: int) -> None:
            job = await db.get(DiscoveryJob, job_id)
            if job is None:
                return
            job.scanned_hosts = done
            job.progress = round((done / total) * 100, 1) if total else 100.0
            await db.commit()

        def should_cancel() -> bool:
            return job.cancel_requested

        reports = []
        try:
            if kind_is_manual(job):
                rep = await discover_host(
                    hosts[0],
                    ports,
                    deep_verify=True,
                )
                reports = [rep]
            else:
                reports = await discover_many(
                    hosts,
                    ports,
                    max_workers=int(params["max_workers"]),
                    progress=progress,
                    should_cancel=should_cancel,
                    deep_verify=True,
                )
        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED.value
            job.finished_at = utcnow()
            job.stage = DiscoveryStage.CANCELLED.value
            await db.commit()
            raise
        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.FAILED.value
            job.error = str(exc)[:2000]
            job.finished_at = utcnow()
            job.stage = DiscoveryStage.FAILED.value
            await db.commit()
            return

        # persist
        found = 0
        async with sf() as db2:
            job2 = await db2.get(DiscoveryJob, job_id)
            if job2 is None:
                return
            for rep in reports:
                if rep.get("reachable"):
                    found += 1
                try:
                    await persist_report(db2, rep, job_id, cidr_for_results)
                except Exception as exc:  # noqa: BLE001
                    job2.errors = (job2.errors or 0) + 1
                    await db2.commit()
            job2.status = (
                JobStatus.CANCELLED.value
                if job2.cancel_requested
                else JobStatus.COMPLETED.value
            )
            job2.found_hosts = found
            job2.progress = 100.0
            job2.stage = DiscoveryStage.COMPLETED.value
            job2.finished_at = utcnow()
            job2.summary = {"reachable": found, "scanned": len(reports)}
            # mark devices in this network not seen during scan as OFFLINE
            await _mark_stale_devices(db2, hosts, cidr_for_results)
            await db2.commit()


def kind_is_manual(job: DiscoveryJob) -> bool:
    return job.kind in ("ip", "manual") or "/" not in job.target


async def _resolve_targets(db: AsyncSession, job: DiscoveryJob) -> tuple[list[str], str]:
    target = job.target
    if target.startswith("network:"):
        network_id = target.split(":", 1)[1]
        net = await db.get(DeviceNetwork, network_id)
        if net is None:
            raise ValueError("network not found")
        hosts = [h for h in network_hosts(net.cidr) if h not in (net.exclude_ips or [])]
        return hosts, net.cidr
    if target.startswith("ip:"):
        ip = target.split(":", 1)[1]
        validate_ip(ip)
        return [ip], None
    if target == "all":
        nets = await list_networks(db)
        enabled = [n for n in nets if n.enabled]
        return (
            build_host_list(
                [n.cidr for n in enabled],
                [ip for n in enabled for ip in (n.exclude_ips or [])],
            ),
            None,
        )
    # direct cidr
    validate_cidr(target)
    return network_hosts(target), target


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


async def persist_report(
    db: AsyncSession,
    report: dict,
    job_id: str,
    network_cidr: Optional[str],
) -> Optional[Device]:
    ip = report["ip"]
    verdict = report.get("verdict") or {}
    state = verdict.get("state", DetectionState.UNKNOWN.value)
    device = await db.scalar(select(Device).where(Device.ip_address == ip))
    if device is None and not report.get("reachable"):
        return None
    is_new = device is None
    if device is None:
        device = Device(ip_address=ip, network_cidr=network_cidr)
        db.add(device)

    now = utcnow()
    reachable = bool(report.get("reachable"))
    device.last_seen_at = now
    device.last_probe_at = now
    if reachable:
        device.last_online_at = now
        # Port reachable; protocol upgrade happens below.
        device.status = DeviceStatus.ONLINE_PROTOCOL_OPEN.value
        device.last_probe_error = None
    else:
        device.last_offline_at = now
        # Only mark OFFLINE_VERIFIED for previously-verified devices.
        if device.status in (
            DeviceStatus.VERIFIED.value,
            DeviceStatus.ONLINE_PROTOCOL_VERIFIED.value,
        ):
            device.status = DeviceStatus.OFFLINE_VERIFIED.value
        else:
            device.status = DeviceStatus.PROBE_UNREACHABLE.value
        device.last_probe_error = "; ".join(report.get("errors") or [])[:500] or "probe unreachable"
    device.detection_state = state
    device.confidence = float(verdict.get("confidence", 0.0))
    device.detection_evidence = list(report.get("services", {}).values()) if report.get(
        "services"
    ) else []
    device.is_attendance_candidate = bool(verdict.get("candidate"))
    if report.get("icmp_reachable") is not None:
        device.extra_config["icmp_reachable"] = report["icmp_reachable"]

    zk = report.get("zk")
    info = report.get("device_info")
    if zk and zk.get("verified"):
        device.protocol_name = "zk_tcp"
        device.adapter_name = "zkteco"
        device.is_attendance_candidate = True
        device.detection_state = DetectionState.PROTOCOL_VERIFIED.value
        device.status = DeviceStatus.ONLINE_PROTOCOL_VERIFIED.value
        if info:
            # Vendor stays UNLESS OEMVendor explicitly reports it (Task 9)
            if info.get("brand"):
                device.brand = info.get("brand")
            device.model = info.get("model")
            device.serial_number = info.get("serial_number")
            device.firmware_version = info.get("firmware_version")
            device.platform = info.get("platform")
            device.device_name = info.get("device_name")
            if info.get("vendor"):
                device.vendor = info.get("vendor")
            device.mac_address = info.get("mac_address")
            device.verified_at = now
            device.detection_state = DetectionState.DEVICE_VERIFIED.value
            device.confidence = max(device.confidence or 0, 0.99)
            device.status = DeviceStatus.VERIFIED.value
    elif info:
        device.detection_state = DetectionState.PROTOCOL_VERIFIED.value

    if report.get("errors"):
        device.last_error = "; ".join(report["errors"])[:2000]

    await db.flush()

    # protocols rows
    seen_protos: set[tuple] = set()
    for port, svc in (report.get("services") or {}).items():
        if svc.get("error"):
            continue
        port_i = int(port)
        proto_state = DetectionState.UNKNOWN.value
        conf = 0.0
        protocol = None
        source = svc.get("source")
        if svc.get("zk_tcp"):
            protocol = "zk_tcp"
            proto_state = DetectionState.PROTOCOL_VERIFIED.value
            conf = svc.get("confidence", 0.95)
        elif svc.get("http"):
            protocol = "http"
            proto_state = DetectionState.PORT_OPEN.value
            conf = 0.6
        elif svc.get("snmp"):
            protocol = "snmp"
            proto_state = DetectionState.PORT_OPEN.value
            conf = svc.get("confidence", 0.7)
        elif svc.get("banner"):
            protocol = "tcp"
            proto_state = DetectionState.PORT_OPEN.value
            conf = 0.2
        row = await db.scalar(
            select(DeviceProtocol).where(
                DeviceProtocol.device_id == device.id,
                DeviceProtocol.port == port_i,
            )
        )
        if row is None:
            row = DeviceProtocol(device_id=device.id, port=port_i)
            db.add(row)
        row.transport = "tcp"
        row.protocol_guess = protocol
        row.protocol_state = proto_state
        row.confidence = conf
        row.source = source
        row.last_seen_at = now
        row.evidence = svc.get("evidence") or {}
        row.banner = (svc.get("banner") or "")[:2000] or None
        row.http_headers = svc.get("headers") or {}
        row.html_title = svc.get("title")
        if svc.get("http"):
            row.service = "http"
        seen_protos.add((port_i, row.id))

    # capability rows from adapter declarations
    if device.adapter_name:
        await _seed_capabilities(db, device)

    # raw payloads (bounded)
    for port, svc in (report.get("services") or {}).items():
        if svc.get("body_snippet"):
            db.add(
                DeviceRawData(
                    device_id=device.id,
                    category="http_body",
                    source=f"port {port}",
                    payload=svc["body_snippet"][:8000],
                    meta={"port": int(port)},
                )
            )
        if svc.get("evidence") and svc.get("zk_tcp"):
            db.add(
                DeviceRawData(
                    device_id=device.id,
                    category="zk_handshake",
                    source="discovery",
                    meta=svc["evidence"],
                )
            )

    # discovery result row
    dr = DiscoveryResult(
        discovery_job_id=job_id,
        device_id=device.id if not is_new else None,
        ip_address=ip,
        reachable=reachable,
        open_ports=report.get("open_ports") or [],
        icmp_reachable=report.get("icmp_reachable"),
        http_headers=next(
            (h.get("headers") or {} for h in (report.get("http") or []) if h.get("http")),
            {},
        ),
        html_title=next(
            (h.get("title") for h in (report.get("http") or []) if h.get("title")),
            None,
        ),
        banners={
            str(s.get("port")): s.get("banner")
            for s in (report.get("services") or {}).values()
            if s.get("banner")
        },
        detection_state=state,
        confidence=float(verdict.get("confidence", 0.0)),
        source=verdict.get("source"),
        evidence=verdict,
    )
    if not is_new:
        dr.device_id = device.id
    db.add(dr)
    await db.flush()
    return device


async def _seed_capabilities(db: AsyncSession, device: Device) -> None:
    """(Re)seed capability matrix rows from adapter declarations.

    Only when the device has no capability rows yet; later scans must not
    erase runtime verification flags. Destructive capabilities default to
    enabled=False and require explicit operator approval.
    """
    existing_count = await db.scalar(
        select(DeviceCapability.id)
        .where(DeviceCapability.device_id == device.id)
        .limit(1)
    )
    if existing_count:
        return
    adapter_cls = get_adapter_class(device.adapter_name or "")
    if adapter_cls is None:
        return
    adapter = adapter_cls({"ip_address": device.ip_address, "port": device.port or 4370})
    declared = adapter.declare_capabilities()
    for cap in CAPABILITY_KEYS:
        spec = declared.get(cap) or {"supported": False, "reason": "undeclared"}
        row = await db.scalar(
            select(DeviceCapability).where(
                DeviceCapability.device_id == device.id,
                DeviceCapability.capability == cap,
            )
        )
        if row is None:
            row = DeviceCapability(device_id=device.id, capability=cap)
            db.add(row)
        implemented = bool(spec.get("supported", False))
        destructive = cap in {
            "create_users", "update_users", "delete_users", "delete_logs",
            "clear_data", "set_time", "sync_users_to_device", "write_templates",
        }
        # Read-only safe operations start enabled as soon as they are verified;
        # destructive operations stay disabled until an operator turns them on.
        row.implemented = implemented
        row.source = spec.get("source")
        row.reason = spec.get("reason")
        row.is_destructive = destructive
        # verified stays False until a real op succeeds; enabled is set on
        # first verification (see mark_capability_verified).
        row.verified = False
        row.enabled = False
    await db.flush()


async def mark_device_offline(db: AsyncSession, device_id: str) -> None:
    device = await db.get(Device, device_id)
    if device:
        device.status = DeviceStatus.OFFLINE_VERIFIED.value
        device.last_offline_at = utcnow()
        await db.commit()


async def mark_capability_verified(
    db: AsyncSession, device_id: str, capability: str, supported: bool = True
) -> None:
    """Record that a capability has been verified against a real device.

    Non-destructive capabilities are auto-enabled on first verification;
    destructive ones stay disabled until an operator flips the flag
    (and the UI additionally requires confirmation + re-auth).
    """
    DESTRUCTIVE_CAPS = {
        "create_users", "update_users", "delete_users", "delete_logs",
        "clear_data", "set_time", "sync_users_to_device", "write_templates",
    }
    row = await db.scalar(
        select(DeviceCapability).where(
            DeviceCapability.device_id == device_id,
            DeviceCapability.capability == capability,
        )
    )
    if row is None:
        row = DeviceCapability(device_id=device_id, capability=capability)
        db.add(row)
    row.implemented = supported
    row.verified = supported
    if supported and not row.is_destructive and capability not in DESTRUCTIVE_CAPS:
        row.enabled = True
    row.is_destructive = capability in DESTRUCTIVE_CAPS
    row.source = "verified on device"
    await db.flush()


async def _mark_stale_devices(
    db: AsyncSession, scanned_ips: list[str], network_cidr: Optional[str]
) -> None:
    """Devices inside the scanned range that didn't answer become PROBE_UNREACHABLE
    (or OFFLINE_VERIFIED for previously-verified devices)."""
    if not network_cidr:
        return
    stale_since = utcnow() - timedelta(minutes=5)
    devices = (
        await db.scalars(
            select(Device).where(
                Device.network_cidr == network_cidr,
                Device.last_seen_at < stale_since,
            )
        )
    ).all()
    ipset = set(scanned_ips)
    for d in devices:
        if d.ip_address in ipset:
            d.last_offline_at = utcnow()
            if d.status in (
                DeviceStatus.VERIFIED.value,
                DeviceStatus.ONLINE_PROTOCOL_VERIFIED.value,
            ):
                d.status = DeviceStatus.OFFLINE_VERIFIED.value
            else:
                d.status = DeviceStatus.PROBE_UNREACHABLE.value

"""Discovery engine orchestration.

Pipeline per host (stages):
    scan ports -> service probes -> fingerprint -> (optional) deep verify
"""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

from app.adapters.registry import candidate_adapters_for_evidence
from app.core.config import settings
from app.discovery.fingerprint import fingerprint_evidence
from app.discovery.probes import probe_service
from app.discovery.scanner import ScanConfig, scan_hosts
from app.discovery.validate import network_hosts

ServiceProbeResult = dict
HostReport = dict


async def probe_open_port(
    ip: str, port: int, connect_timeout: float, zk_probe: bool = False
) -> dict:
    try:
        return await asyncio.wait_for(
            probe_service(ip, port, connect_timeout, zk_probe=zk_probe),
            timeout=max(connect_timeout * 4, 8),
        )
    except Exception as exc:  # noqa: BLE001
        return {"port": port, "error": str(exc)[:300]}


async def discover_host(
    ip: str,
    ports: list[int],
    *,
    connect_timeout: Optional[float] = None,
    deep_verify: bool = False,
    zk_probe: bool = False,
) -> HostReport:
    """Scan + probe + fingerprint a single host."""
    timeout = connect_timeout or settings.scan_tcp_connect_timeout_s
    cfg = ScanConfig(
        ports=ports,
        connect_timeout_s=timeout,
        max_workers=min(len(ports), 64),
    )
    (res,) = await scan_hosts([ip], cfg)
    report: HostReport = {
        "ip": ip,
        "reachable": res.reachable,
        "open_ports": res.open_ports,
        "icmp_reachable": res.icmp_reachable,
        "services": {},
        "http": [],
        "zk": None,
        "snmp": None,
        "verdict": None,
        "device_info": None,
        "errors": [],
    }
    if not res.reachable:
        report["verdict"] = fingerprint_evidence(report)
        return report

    for port in res.open_ports:
        svc = await probe_open_port(ip, port, timeout, zk_probe=zk_probe or port == 4370)
        report["services"][str(port)] = svc
        if svc.get("zk_tcp"):
            report["zk"] = {
                "verified": True,
                "confidence": svc.get("confidence", 0.0),
                "evidence": svc.get("evidence", {}),
                "detail": svc.get("detail", ""),
                "attendance_ports": [port],
            }
        if svc.get("http"):
            report["http"].append(svc)
        if svc.get("snmp"):
            report["snmp"] = {
                "verified": True,
                "confidence": svc.get("confidence", 0.0),
                "evidence": svc.get("evidence", {}),
            }

    evidence = {
        "open_ports": res.open_ports,
        "services": report["services"],
        "zk": report["zk"],
        "http": report["http"],
        "snmp": report["snmp"],
    }
    candidates = candidate_adapters_for_evidence(
        {
            "open_ports": res.open_ports,
            "protocols": [s.get("protocol") for s in report["services"].values() if s.get("protocol")],
        }
    )
    evidence["adapter_candidates"] = [c.id_ for c in candidates]
    report["verdict"] = fingerprint_evidence(evidence)
    report["adapter_candidates"] = [c.id_ for c in candidates]

    # deep verify: instantiate the strongest adapter and read device info
    if deep_verify and report["zk"]:
        from app.adapters.registry import instantiate

        zk_ports = (report["zk"].get("attendance_ports") or []) or [
            int(p) for p, s in (report.get("services") or {}).items() if s.get("zk_tcp")
        ]
        zk_port = zk_ports[0] if zk_ports else 4370
        try:
            adapter = instantiate("zkteco", {"ip_address": ip, "port": zk_port})
            info = await adapter.get_device_info()
            report["device_info"] = {
                k: v
                for k, v in info.__dict__.items()
                if k != "raw" and v is not None
            }
            if info.raw:
                report["device_info"]["raw"] = info.raw
            await adapter.disconnect()
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"deep verify failed: {exc}")
    return report


async def discover_many(
    ips: list[str],
    ports: list[int],
    *,
    max_workers: int | None = None,
    progress: Optional[Callable] = None,
    should_cancel: Optional[Callable] = None,
    deep_verify: bool = True,
) -> list[HostReport]:
    """Run the full pipeline over many hosts with global concurrency."""
    workers = max_workers or settings.scan_max_workers
    sem = asyncio.Semaphore(workers)
    out: list[HostReport] = []

    async def worker(ip: str, idx: int) -> None:
        if should_cancel and should_cancel():
            return
        async with sem:
            rep = await discover_host(
                ip,
                ports,
                deep_verify=deep_verify,
                zk_probe=4370 in ports,
            )
        out.append(rep)
        if progress:
            result = progress(idx + 1, len(ips))
            if asyncio.iscoroutine(result):
                await result

    # hosts are independent; process in chunks to keep progress meaningful
    chunk = max(1, workers * 2)
    for start in range(0, len(ips), chunk):
        if should_cancel and should_cancel():
            break
        batch = ips[start : start + chunk]
        await asyncio.gather(*(worker(ip, start + n) for n, ip in enumerate(batch)))
    return out


def build_host_list(
    cidrs: list[str], exclude_ips: list[str] | None = None
) -> list[str]:
    """Merge several CIDRs into a deduplicated host list."""
    exclude = set(exclude_ips or [])
    seen: dict[str, None] = {}
    for cidr in cidrs:
        for h in network_hosts(cidr):
            if h not in exclude and h not in seen:
                seen[h] = None
    return list(seen.keys())

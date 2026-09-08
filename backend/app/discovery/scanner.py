"""Stage 1+2: network reachability and TCP service discovery.

Pure asyncio implementation - no OS commands are ever invoked, so IP/host
input can not be turned into command injection.  All targets are validated
with ipaddress and must come from configured networks or explicit manual IPs
(enforced by the service layer).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from app.discovery.validate import validate_target  # noqa: F401

ProgressCallback = Callable[[int, int], Awaitable[None]]  # done, total
CancelCheck = Callable[[], bool]


@dataclass
class ScanConfig:
    ports: list[int] = field(default_factory=list)
    connect_timeout_s: float = 1.0
    max_workers: int = 96
    retries: int = 0


@dataclass
class HostResult:
    ip: str
    reachable: bool = False
    open_ports: list[int] = field(default_factory=list)
    connect_errors: int = 0
    icmp_reachable: Optional[bool] = None


async def _tcp_probe(ip: str, port: int, timeout: float) -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=timeout
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        return True
    except (OSError, asyncio.TimeoutError, ConnectionError):
        return False


async def _probe_host_ports(
    ip: str,
    ports: list[int],
    config: ScanConfig,
    sem: asyncio.Semaphore,
) -> HostResult:
    result = HostResult(ip=ip)
    # ICMP is attempted only when explicitly enabled AND permitted (raw socket
    # availability is detected at runtime; failure simply degrades to TCP).
    if config_icmp_enabled():
        result.icmp_reachable = await _icmp_ping(ip, config.connect_timeout_s)
    async def one(port: int) -> None:
        async with sem:
            ok = False
            for attempt in range(config.retries + 1):
                if await _tcp_probe(ip, port, config.connect_timeout_s):
                    ok = True
                    break
            if ok:
                result.open_ports.append(port)
                result.reachable = True
            else:
                result.connect_errors += 1

    await asyncio.gather(*(one(p) for p in ports))
    result.open_ports.sort()
    return result


async def scan_hosts(
    ips: list[str],
    config: ScanConfig,
    progress: Optional[ProgressCallback] = None,
    should_cancel: Optional[CancelCheck] = None,
) -> list[HostResult]:
    """Scan many hosts concurrently; returns per-host results."""
    sem = asyncio.Semaphore(config.max_workers)
    results: list[HostResult] = []

    async def worker(ip: str, idx: int) -> None:
        if should_cancel and should_cancel():
            return
        r = await _probe_host_ports(ip, config.ports, config, sem)
        results.append(r)
        if progress:
            result = progress(idx + 1, len(ips))
            if asyncio.iscoroutine(result):
                await result

    chunk = max(1, config.max_workers * 4)
    for i in range(0, len(ips), chunk):
        if should_cancel and should_cancel():
            break
        batch = ips[i : i + chunk]
        await asyncio.gather(*(worker(ip, i + n) for n, ip in enumerate(batch)))
    return results


_icmp_available: Optional[bool] = None


def config_icmp_enabled() -> bool:
    # Enabled only if the caller sets it; detection happens at ping time.
    from app.core.config import settings

    return bool(settings.enable_icmp)


async def _icmp_ping(ip: str, timeout: float) -> Optional[bool]:
    """Best-effort ICMP echo using a raw socket (requires privileges).

    Returns None when ICMP is unavailable (no permission / no support), so a
    permission failure is never reported as 'offline'.
    """
    global _icmp_available
    try:
        import socket
        import struct

        if _icmp_available is False:
            return None
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    except (OSError, PermissionError, AttributeError):
        _icmp_available = False
        return None
    try:
        _icmp_available = True
        import os
        import random

        pid = os.getpid() & 0xFFFF
        seq = random.randint(0, 0xFFFF)
        payload = struct.pack(">d", 0.0)
        checksum = _icmp_checksum(struct.pack(">BBHHH", 8, 0, 0, pid, seq) + payload)
        pkt = struct.pack(">BBHHH", 8, 0, checksum, pid, seq) + payload
        sock.settimeout(timeout)
        sock.sendto(pkt, (ip, 1))
        loop = asyncio.get_event_loop()

        def recv():
            while True:
                data, _ = sock.recvfrom(2048)
                if len(data) >= 28 and data[20] == 0:  # icmp echo reply
                    return True

        return await asyncio.to_thread(recv)
    except (OSError, asyncio.TimeoutError):
        return False
    finally:
        sock.close()


def _icmp_checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    s = sum(int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2))
    s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF

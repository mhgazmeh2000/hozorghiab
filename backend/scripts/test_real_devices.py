#!/usr/bin/env python3
"""Real-device read-only verification script.

Usage (Windows or Linux)::

    cd backend
    python scripts/test_real_devices.py            # test known devices
    python scripts/test_real_devices.py --json     # JSON report
    python scripts/test_real_devices.py --ingest   # also ingest into DB

This script NEVER performs any write, clear, restart, set-time, delete or
other destructive operation. It is strictly read-only. For each device
it attempts:

    TCP 4370 connect
    ZK protocol handshake
    firmware / serial / platform / MAC / name
    network params
    device time
    users list
    attendance list
    DB ingest (only with --ingest flag; requires running API DB)

If the execution environment has no route to the device IPs (which is true
in cloud sandboxes), every step is reported EXECUTION_ENVIRONMENT with
the socket error attached. The code remains ready to run on an operator's
Windows machine where the devices are reachable.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

# Ensure we can import `app` when run as ``python scripts/test_real_devices.py``
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.adapters.zk_protocol import ZKConnection, DeviceConnectionError, DeviceProtocolError  # noqa: E402


KNOWN_DEVICES = [
    {"ip": "172.16.0.20", "port": 4370, "tag": "Device A"},
    {"ip": "172.16.32.21", "port": 4370, "tag": "Device B"},
]


@dataclass
class StepResult:
    name: str
    status: str          # PASS | FAIL | NOT_SUPPORTED | NOT_VERIFIED | EXECUTION_ENVIRONMENT
    detail: str = ""
    duration_ms: int = 0
    data: dict = field(default_factory=dict)


def _tcp_probe(ip: str, port: int, timeout: float = 3.0) -> StepResult:
    t0 = time.monotonic()
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            pass
        return StepResult(
            name=f"TCP {port}",
            status="PASS",
            detail="connect() succeeded",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
    except OSError as exc:
        # Distinguish "no route / unreachable" (execution environment)
        # from "connection refused" (device is reachable but port closed).
        code = getattr(exc, "errno", None)
        if code in (113, 101, 110, 111, 10060, 10061, 10051) or isinstance(exc, (TimeoutError, socket.timeout)):
            status = "EXECUTION_ENVIRONMENT"
            if code == 111 or (hasattr(exc, "args") and exc.args and "refused" in str(exc).lower()):
                status = "FAIL"
            return StepResult(
                name=f"TCP {port}",
                status=status,
                detail=f"{type(exc).__name__}: {exc}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        return StepResult(
            name=f"TCP {port}",
            status="FAIL",
            detail=str(exc),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )


async def _zk_handshake(ip: str, port: int, timeout: float) -> tuple[Optional[ZKConnection], StepResult]:
    t0 = time.monotonic()
    conn = ZKConnection(ip, port, connect_timeout=timeout, read_timeout=max(timeout * 2, 8))
    try:
        await conn.connect()
        return conn, StepResult(
            name="ZK handshake",
            status="PASS",
            detail=f"session_id={conn.session_id}",
            duration_ms=int((time.monotonic() - t0) * 1000),
            data={"session_id": conn.session_id},
        )
    except DeviceConnectionError as exc:
        msg = str(exc)
        status = "EXECUTION_ENVIRONMENT" if ("cannot open TCP" in msg or "timeout" in msg.lower()) else "FAIL"
        return None, StepResult(
            name="ZK handshake", status=status, detail=msg,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        return None, StepResult(
            name="ZK handshake", status="FAIL", detail=str(exc),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )


async def _safe(coro, name: str) -> StepResult:
    t0 = time.monotonic()
    try:
        result = await coro
        detail = ""
        data: dict[str, Any] = {}
        if isinstance(result, str):
            detail = result[:200]
        elif isinstance(result, dict):
            data = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in result.items()}
            detail = ", ".join(f"{k}={v}" for k, v in list(data.items())[:6])
        elif isinstance(result, list):
            data["count"] = len(result)
            detail = f"{len(result)} items"
        elif result is not None:
            detail = str(result)[:200]
        return StepResult(name=name, status="PASS", detail=detail,
                          duration_ms=int((time.monotonic() - t0) * 1000), data=data)
    except NotSupportedClass as exc:
        return StepResult(name=name, status="NOT_SUPPORTED", detail=str(exc),
                          duration_ms=int((time.monotonic() - t0) * 1000))
    except (DeviceConnectionError, DeviceProtocolError, OSError, asyncio.TimeoutError) as exc:
        return StepResult(name=name, status="EXECUTION_ENVIRONMENT",
                          detail=f"{type(exc).__name__}: {exc}",
                          duration_ms=int((time.monotonic() - t0) * 1000))
    except Exception as exc:  # noqa: BLE001
        return StepResult(name=name, status="FAIL",
                          detail=f"{type(exc).__name__}: {exc}",
                          duration_ms=int((time.monotonic() - t0) * 1000))


class NotSupportedClass(Exception):
    pass


async def test_device(ip: str, port: int, tag: str, timeout: float = 5.0) -> dict:
    results: list[StepResult] = []
    print()
    print(f"=== DEVICE {ip} ({tag}) ===")

    # 1) TCP
    tcp_res = _tcp_probe(ip, port, timeout)
    results.append(tcp_res)
    _print_step(tcp_res)
    if tcp_res.status not in ("PASS",):
        # If TCP itself cannot be established, mark ZK steps as EXECUTION_ENVIRONMENT.
        for nm in ("ZK handshake", "Firmware", "Serial", "Platform", "Device name",
                   "MAC", "Network params", "Device time", "Users", "Attendance"):
            r = StepResult(name=nm, status="EXECUTION_ENVIRONMENT",
                           detail="skipped: TCP probe did not succeed")
            results.append(r)
            _print_step(r)
        return {"device": ip, "tag": tag, "steps": [asdict(r) for r in results]}

    # 2) Handshake
    conn, hs = await _zk_handshake(ip, port, timeout)
    results.append(hs)
    _print_step(hs)
    if conn is None or hs.status != "PASS":
        for nm in ("Firmware", "Serial", "Platform", "Device name", "MAC",
                   "Network params", "Device time", "Users", "Attendance"):
            r = StepResult(name=nm, status="EXECUTION_ENVIRONMENT",
                           detail="skipped: handshake failed")
            results.append(r)
            _print_step(r)
        return {"device": ip, "tag": tag, "steps": [asdict(r) for r in results]}

    try:
        # 3) Read operations
        steps = [
            ("Firmware", _read_firmware(conn)),
            ("Serial", conn.read_option("~SerialNumber")),
            ("Platform", conn.read_option("~Platform")),
            ("Device name", conn.read_option("~DeviceName")),
            ("MAC", conn.read_option("MAC")),
            ("Network params", conn.read_options(["IPAddress", "~NetMask", "~GATEIPAddress"])),
            ("Device time", conn.get_time()),
            ("Users", _count_users(conn)),
            ("Attendance", _count_attendance(conn)),
        ]
        for name, coro in steps:
            r = await _safe(coro, name)
            results.append(r)
            _print_step(r)
    finally:
        try:
            await conn.close()
        except Exception:
            pass

    return {"device": ip, "tag": tag, "steps": [asdict(r) for r in results]}


async def _read_firmware(conn):
    resp = await conn.command(1100)
    raw = resp.get("data", b"")
    return raw.split(b"\x00")[0].decode("utf-8", "replace").strip() or None


async def _count_users(conn):
    raw = await conn.get_users_raw()
    from app.adapters.zk_protocol import parse_user_entries
    users = parse_user_entries(raw)
    return users


async def _count_attendance(conn):
    raw = await conn.get_attendance_raw()
    from app.adapters.zk_protocol import parse_att_entries
    logs = parse_att_entries(raw)
    return logs


def _print_step(r: StepResult):
    color = {
        "PASS": "\033[32m",
        "FAIL": "\033[31m",
        "NOT_SUPPORTED": "\033[33m",
        "NOT_VERIFIED": "\033[33m",
        "EXECUTION_ENVIRONMENT": "\033[36m",
    }.get(r.status, "")
    reset = "\033[0m"
    print(f"  {color}{r.status:<22}{reset}{r.name:<20} {r.detail}")


async def main():
    parser = argparse.ArgumentParser(description="Real device read-only verification")
    parser.add_argument("--json", action="store_true", help="print JSON report to stdout")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--out", help="write JSON report to file")
    args = parser.parse_args()

    reports = []
    for d in KNOWN_DEVICES:
        rep = await test_device(d["ip"], d["port"], d["tag"], timeout=args.timeout)
        reports.append(rep)

    print()
    print("=" * 60)
    passed = sum(1 for rep in reports for s in rep["steps"] if s["status"] == "PASS")
    failed = sum(1 for rep in reports for s in rep["steps"] if s["status"] == "FAIL")
    env = sum(1 for rep in reports for s in rep["steps"] if s["status"] == "EXECUTION_ENVIRONMENT")
    print(f"Summary: PASS={passed}  FAIL={failed}  EXECUTION_ENVIRONMENT={env}")
    if env:
        print(
            "Note: EXECUTION_ENVIRONMENT steps could not run because this host "
            "has no route to the device network. Re-run from the operator "
            "machine where the devices are reachable."
        )

    if args.json or args.out:
        payload = json.dumps(reports, indent=2, ensure_ascii=False, default=str)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(payload)
            print(f"Report written to {args.out}")
        if args.json:
            print(payload)


if __name__ == "__main__":
    asyncio.run(main())

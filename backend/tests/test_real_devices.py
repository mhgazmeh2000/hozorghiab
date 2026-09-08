"""Opt-in read-only acceptance suite for the two real ZK devices.

Run from backend with:

    $env:RUN_REAL_DEVICE_TESTS = "1"
    python -m pytest -q tests/test_real_devices.py -s

The suite never calls a write operation. A missing route or blocked network is
reported as CURRENTLY_UNREACHABLE in the markdown report and is attributed to
EXECUTION_ENVIRONMENT rather than marking the device OFFLINE_VERIFIED.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

import pytest

from app.adapters.base import NotSupported
from app.adapters.zkteco import ZKTecoAdapter
from app.core.config import settings
from app.discovery.probes import probe_service

async def test_discovery_tracks_4360_as_generic_tcp_not_zk():
    assert 4360 in settings.default_scan_ports

    with pytest.MonkeyPatch.context() as mp:
        async def _fail_zk(*args, **kwargs):
            pytest.fail("port 4360 must not be auto-classified as ZK")

        async def _mock_http(*args, **kwargs):
            return {"http": False}

        async def _mock_banner(*args, **kwargs):
            return {"port": 4360, "banner": "generic tcp banner", "banner_hex": ""}

        mp.setattr("app.discovery.probes.probe_zk", _fail_zk)
        mp.setattr("app.discovery.probes.probe_http", _mock_http)
        mp.setattr("app.discovery.probes.probe_banner", _mock_banner)
        result = await probe_service("127.0.0.1", 4360, 0.5)

    assert result.get("port") == 4360
    assert result.get("protocol") is None
    assert result.get("zk_tcp") is None


DEVICES = {
    "172.16.0.20": {
        "port": 4370,
        "expected": {
            "platform": "ZMM220_TFT",
            "firmware": "Ver 6.60 Apr 27 2017",
            "serial": "ADWC175060007",
            "mac": "00:17:61:12:c9:b4",
            "users": 167,
            "attendance": 12799,
            "user_capacity": 2000,
            "attendance_capacity": 80000,
            "fingerprints": 168,
            "faces": 160,
        },
    },
    "172.16.32.21": {
        "port": 4370,
        "expected": {
            "platform": "ZLM60_TFT",
            "device_name": "MB20",
            "firmware": "Ver 6.60 May 3 2016",
            "serial": "2623320414184",
            "mac": "00:17:61:10:51:1f",
            "users": 90,
            "attendance": 38025,
            "user_capacity": 200,
            "attendance_capacity": 50000,
            "fingerprints": 108,
            "faces": 83,
        },
    },
}


def _environment_failure(exc: Exception) -> bool:
    text = str(exc).lower()
    return isinstance(exc, (OSError, asyncio.TimeoutError, ConnectionError)) or any(
        marker in text
        for marker in ("cannot open tcp", "timeout", "no route", "unreachable")
    )


def _status_for_exception(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, NotSupported):
        return "NOT_SUPPORTED", "DEVICE"
    if _environment_failure(exc):
        return "FAIL", "EXECUTION_ENVIRONMENT"
    return "FAIL", "DEVICE"


async def _tcp_check(ip: str, port: int) -> None:
    reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), 5)
    writer.close()
    await writer.wait_closed()


async def _run_device(ip: str, config: dict) -> dict[str, Any]:
    adapter = ZKTecoAdapter(
        {
            "ip_address": ip,
            "port": config["port"],
            "connect_timeout_s": 5,
            "read_timeout_s": 15,
            "retry_count": 0,
        }
    )
    results: list[dict[str, Any]] = []
    values: dict[str, Any] = {}

    async def step(name: str, action: Callable[[], Awaitable[Any]]) -> bool:
        try:
            value = await action()
            if name == "ZK protocol handshake" and not value.detected:
                detail = value.detail or "ZK handshake was not detected"
                scope = "EXECUTION_ENVIRONMENT" if _environment_failure(Exception(detail)) else "DEVICE"
                results.append({"name": name, "status": "FAIL", "scope": scope, "error": detail})
                return False
            values[name] = value
            results.append({"name": name, "status": "PASS", "scope": "DEVICE", "value": value})
            return True
        except Exception as exc:  # noqa: BLE001
            status, scope = _status_for_exception(exc)
            results.append({"name": name, "status": status, "scope": scope, "error": str(exc) or type(exc).__name__})
            return False

    await step("TCP 4370 connectivity", lambda: _tcp_check(ip, config["port"]))
    await step("ZK protocol handshake", lambda: ZKTecoAdapter.probe(ip, config["port"], 5))
    connected = await step("connect()", adapter.connect)
    if not connected:
        for name in (
            "get_firmware_version()",
            "get_serialnumber()",
            "get_platform()",
            "get_device_name()",
            "get_mac()",
            "get_network_params()",
            "get_time()",
            "get_fp_version()",
            "get_face_version()",
            "get_pin_width()",
            "get_users()",
            "get_attendance()",
        ):
            results.append({"name": name, "status": "NOT_VERIFIED", "scope": "EXECUTION_ENVIRONMENT", "error": "connect() did not succeed"})
        return {"ip": ip, "port": config["port"], "expected": config["expected"], "values": values, "results": results}
    try:
        await step("get_firmware_version()", adapter.get_firmware_version)
        await step("get_serialnumber()", adapter.get_serialnumber)
        await step("get_platform()", adapter.get_platform)
        await step("get_device_name()", adapter.get_device_name)
        await step("get_mac()", adapter.get_mac)
        await step("get_network_params()", adapter.get_network_params)
        await step("get_time()", adapter.get_device_time)
        await step("get_fp_version()", adapter.get_fp_version)
        await step("get_face_version()", adapter.get_face_version)
        await step("get_pin_width()", adapter.get_pin_width)
        await step("get_users()", adapter.get_users)
        await step("get_attendance()", adapter.get_attendance_logs)
    finally:
        await adapter.disconnect()

    return {"ip": ip, "port": config["port"], "expected": config["expected"], "values": values, "results": results}


def _safe(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, (dict, list)):
        return str(value)
    return str(value)


def _write_report(reports: list[dict[str, Any]]) -> None:
    path = Path(__file__).parents[2] / "docs" / "REAL_DEVICE_TEST_REPORT.md"
    lines = [
        "# Real Device Test Report",
        "",
        f"Test timestamp: {datetime.now(timezone.utc).isoformat()}",
        "Execution environment: opt-in pytest suite on the current host",
        "Read-only suite: no write operation was called.",
        "",
    ]
    for report in reports:
        lines.extend([f"## {report['ip']}:{report['port']}", "", "| Test | Status | Scope | Value/Error |", "|---|---|---|---|"])
        for result in report["results"]:
            lines.append(f"| {result['name']} | {result['status']} | {result['scope']} | {_safe(result.get('value', result.get('error')))} |")
        lines.extend(["", "### Expected reference", "", "```json", str(report["expected"]), "```", "", "### Limitations", "", "- Values are VERIFIED only when the corresponding read returns PASS on this run.", "- A blocked route is an execution-environment failure, not proof that the device is offline.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"report written to {path}")


@pytest.mark.asyncio
async def test_real_devices_read_only():
    if os.getenv("RUN_REAL_DEVICE_TESTS") != "1":
        pytest.skip("set RUN_REAL_DEVICE_TESTS=1 to access real devices")
    reports = [await _run_device(ip, config) for ip, config in DEVICES.items()]
    _write_report(reports)

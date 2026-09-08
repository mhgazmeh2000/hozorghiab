"""Run the real read-only ZK check and sync for the configured devices.

Usage (from backend):

    $env:REAL_DEVICE_SYNC = "1"
    $env:DATABASE_URL = "postgresql+psycopg://..."
    python scripts/real_device_sync.py --full

The command never calls device write operations. It only persists values that
were returned by the device. A blocked route is recorded as an execution
environment failure and does not change the device to OFFLINE_VERIFIED.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if os.getenv("REAL_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["REAL_DATABASE_URL"]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.adapters.base import NotSupported
from app.adapters.zkteco import ZKTecoAdapter
from app.database import get_session_factory, init_db
from app.models import AttendanceLog, Device, DeviceUser
from app.services import attendance_service, device_service

TARGETS = ("172.16.0.20", "172.16.32.21")
PORT = 4370


def is_environment_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return isinstance(exc, (OSError, TimeoutError, ConnectionError)) or any(
        item in text for item in ("cannot open tcp", "timeout", "unreachable", "no route")
    )


def fail_scope(exc: Exception) -> str:
    return "EXECUTION_ENVIRONMENT" if is_environment_error(exc) else "DEVICE"


async def tcp_check(ip: str) -> None:
    reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, PORT), 5)
    writer.close()
    await writer.wait_closed()


async def ensure_device(db, ip: str) -> Device:
    device = await db.scalar(select(Device).where(Device.ip_address == ip))
    if device is None:
        device = Device(ip_address=ip, port=PORT, adapter_name="zkteco", protocol_name="zk_tcp")
        db.add(device)
    else:
        device.port = PORT
        device.adapter_name = "zkteco"
        device.protocol_name = "zk_tcp"
    await db.commit()
    await db.refresh(device)
    return device


async def run_device(db, ip: str, full: bool) -> dict[str, Any]:
    device = await ensure_device(db, ip)
    if full:
        extra = dict(device.extra_config or {})
        extra.pop("attendance_sync", None)
        device.extra_config = extra
        await db.commit()

    result: dict[str, Any] = {
        "ip": ip,
        "port": PORT,
        "protocol": "ZK TCP",
        "connection": {"status": "NOT_VERIFIED"},
        "handshake": {"status": "NOT_VERIFIED"},
        "communication_key": "CONFIGURED" if await device_service.get_device_credentials(db, device.id) else "NOT_CONFIGURED",
        "errors": [],
        "execution_environment": "CURRENT_HOST",
    }

    try:
        await tcp_check(ip)
        result["connection"] = {"status": "PASS"}
    except Exception as exc:  # noqa: BLE001
        result["connection"] = {"status": "FAIL", "scope": fail_scope(exc), "error": str(exc) or type(exc).__name__}
        result["execution_environment"] = fail_scope(exc)
        return result

    probe = await ZKTecoAdapter.probe(ip, PORT, 5)
    if not probe.detected:
        result["handshake"] = {"status": "FAIL", "scope": "DEVICE", "error": probe.detail or "ZK handshake not detected"}
        return result
    result["handshake"] = {"status": "PASS", "evidence": probe.evidence}

    adapter = ZKTecoAdapter({"ip_address": ip, "port": PORT, "connect_timeout_s": 5, "read_timeout_s": 15})
    try:
        await adapter.connect()
        result["connection"] = {"status": "PASS", "detail": "ZK session connected"}
        info = await device_service.fetch_and_store_device_info(db, device)
        users = await device_service.read_and_store_users(db, device)
        attendance = await attendance_service.pull_attendance_logs(db, device)
        result.update(
            {
                "firmware": info.get("firmware_version"),
                "serial": info.get("serial_number"),
                "platform": info.get("platform"),
                "device_name": info.get("device_name"),
                "mac": info.get("mac_address"),
                "network": info.get("network_params", "UNKNOWN"),
                "device_time": info.get("device_time"),
                "user_count": len(users),
                "attendance_count": attendance.get("device_count"),
                "sync_result": "PASS",
                "db_result": {
                    "users_inserted_or_updated": len(users),
                    "attendance_inserted": attendance.get("inserted", 0),
                    "attendance_duplicates": attendance.get("duplicates", 0),
                    "cursor": (device.extra_config.get("attendance_sync") or {}).get("cursor"),
                },
                "dashboard_result": "AVAILABLE_VIA_REST_API",
            }
        )
        counts = (device.extra_config or {}).get("counts") or {}
        result["storage"] = {
            "attendance_used": counts.get("attendance_count"),
            "attendance_capacity": counts.get("attendance_capacity"),
            "attendance_free": counts.get("attendance_free"),
        }
    except NotSupported as exc:
        result["sync_result"] = "NOT_SUPPORTED"
        result["errors"].append(str(exc))
    except Exception as exc:  # noqa: BLE001
        result["sync_result"] = "FAIL"
        result["errors"].append({"scope": fail_scope(exc), "error": str(exc) or type(exc).__name__})
    finally:
        await adapter.disconnect()
    return result


def markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Real Device Integration Result",
        "",
        f"Timestamp: {datetime.now(timezone.utc).isoformat()}",
        "Execution environment: current host; read-only integration only.",
        "",
    ]
    for item in results:
        lines.extend([f"## {item['ip']}:{item['port']}", ""])
        for key in (
            "protocol", "connection", "handshake", "firmware", "serial", "platform",
            "device_name", "mac", "network", "device_time", "user_count",
            "attendance_count", "storage", "sync_result", "db_result",
            "dashboard_result", "communication_key", "execution_environment", "errors",
        ):
            lines.append(f"- **{key}**: `{item.get(key, 'NOT_VERIFIED')}`")
        lines.append("")
    lines.extend([
        "## Write operations",
        "",
        "All write operations remain `NOT_VERIFIED` and were not executed: set_user, delete_user, clear_attendance, clear_data, restart, poweroff, disable_device, set_time.",
        "",
    ])
    return "\n".join(lines)


async def main(full: bool) -> None:
    if os.getenv("REAL_DEVICE_SYNC") != "1":
        raise SystemExit("Set REAL_DEVICE_SYNC=1 before running this command")
    if os.getenv("DATABASE_URL", "").startswith("sqlite"):
        await init_db()
    sf = get_session_factory()
    async with sf() as db:
        results = [await run_device(db, ip, full) for ip in TARGETS]
    report_path = Path(__file__).parents[2] / "docs" / "REAL_DEVICE_INTEGRATION_RESULT.md"
    report_path.write_text(markdown(results), encoding="utf-8")
    print(f"wrote {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="reset the attendance cursor before initial sync")
    args = parser.parse_args()
    asyncio.run(main(args.full))

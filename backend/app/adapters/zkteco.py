"""ZKTeco / ZK-standalone-protocol adapter (TCP, port 4370).

This is the protocol family used by ZKTeco terminals and by the many OEM
brands built on ZK boards (identified only after reading ``~OEMVendor`` /
``~DeviceName`` - never assumed).

Wire protocol: see ``zk_protocol.py`` (public spec by A. Marin based on
ZKTeco "Standalone series communication protocol" documentation).
Capabilities declared here describe what the *documented protocol* provides;
per-device verification happens at runtime and is stored on the device row.
"""
from __future__ import annotations

import datetime as dt
import struct
from typing import Optional

from app.adapters.base import (
    AdapterProbeResult,
    AttendanceAdapter,
    AttendanceRecord,
    DeviceConnectionError,
    DeviceInfo,
    DeviceProtocolError,
    DeviceUserRecord,
    NotSupported,
)
from app.adapters.zk_protocol import (
    CMD_REG_EVENT,
    ZKConnection,
    encode_packet,
    parse_att_entries,
    parse_user_entries,
)


def _clean_str(b: bytes) -> str:
    return b.split(b"\x00")[0].decode("utf-8", "replace").strip()


class ZKTecoAdapter(AttendanceAdapter):
    id_ = "zkteco"
    display_name = "ZKTeco (ZK TCP protocol)"
    description = (
        "ZKTeco standalone terminals over the documented ZK TCP protocol on "
        "port 4370 (also covers OEM devices on ZK platforms)."
    )
    priority = 10

    def __init__(self, device_cfg: Optional[dict] = None):
        super().__init__(device_cfg)
        self.host = (device_cfg or {}).get("ip_address", "")
        self.port = int((device_cfg or {}).get("port") or 4370)
        self.comm_key = (device_cfg or {}).get("communication_key")
        self.conn: Optional[ZKConnection] = None

    # ------------------------------------------------------------------
    @classmethod
    async def probe(cls, ip: str, port: int, timeout_s: float) -> AdapterProbeResult:
        """Attempt a real ZK CMD_CONNECT handshake."""
        conn = ZKConnection(ip, port, connect_timeout=timeout_s, read_timeout=timeout_s)
        try:
            await conn.connect()
            if conn.session_id is not None:
                return AdapterProbeResult(
                    protocol="zk_tcp",
                    detected=True,
                    confidence=0.98,
                    source="ZK CMD_CONNECT handshake (CMD_ACK_OK + session id)",
                    evidence={
                        "port": port,
                        "session_id": conn.session_id,
                        "commands": ["CMD_CONNECT", "CMD_ACK_OK"],
                    },
                    detail="ZK protocol handshake succeeded",
                )
            return AdapterProbeResult(
                protocol="zk_tcp", detected=False, confidence=0.0,
                source="ZK handshake", detail="no session id returned",
            )
        except (DeviceConnectionError, DeviceProtocolError, Exception) as exc:  # noqa: BLE001
            return AdapterProbeResult(
                protocol="zk_tcp",
                detected=False,
                confidence=0.0,
                source="ZK handshake",
                detail=str(exc)[:300],
            )
        finally:
            await conn.close()

    async def _session(self) -> ZKConnection:
        if self.conn is None:
            self.conn = ZKConnection(
                self.host,
                self.port,
                connect_timeout=float(self.device_cfg.get("connect_timeout_s", 3.0)),
                read_timeout=float(self.device_cfg.get("read_timeout_s", 10.0)),
                comm_key=self.comm_key,
            )
            await self.conn.connect()
        return self.conn

    async def connect(self) -> None:
        await self._session()

    async def disconnect(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    async def test_connection(self) -> dict:
        try:
            c = await self._session()
            return {
                "ok": True,
                "detail": f"ZK session established (session id {c.session_id})",
                "session_id": c.session_id,
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": str(exc)[:500]}

    async def get_firmware_version(self) -> str | None:
        response = await (await self._session()).command(1100)
        return _clean_str(response["data"]) or None

    async def get_serialnumber(self) -> str | None:
        return await (await self._session()).read_option("~SerialNumber")

    async def get_platform(self) -> str | None:
        return await (await self._session()).read_option("~Platform")

    async def get_device_name(self) -> str | None:
        return await (await self._session()).read_option("~DeviceName")

    async def get_mac(self) -> str | None:
        return await (await self._session()).read_option("MAC")

    async def get_network_params(self) -> dict:
        values = await (await self._session()).read_options(
            ["IPAddress", "~NetMask", "~GATEIPAddress", "DNS", "~DNS", "~DHCP"]
        )
        if not values:
            raise NotSupported("device did not expose network parameters")
        return values

    async def get_device_time(self) -> dt.datetime:
        return await (await self._session()).get_time()

    async def get_fp_version(self) -> str | None:
        return await (await self._session()).read_option("~ZKFPVersion")

    async def get_face_version(self) -> str | None:
        return await (await self._session()).read_option("~FaceVersion")

    async def get_pin_width(self) -> str | None:
        return await (await self._session()).read_option("~PIN2Width")

    # ------------------------------------------------------------------
    async def get_device_info(self) -> DeviceInfo:
        c = await self._session()
        opts = await c.read_options(
            [
                "~Platform",
                "~SerialNumber",
                "~DeviceName",
                "~OEMVendor",
                "MAC",
                "~ProductTime",
                "~ZKFPVersion",
                "~FaceFunOn",
                "FingerFunOn",
                "WorkCode",
                "~PIN2Width",
                "~IsOnlyRFMachine",
            ]
        )
        # IMPORTANT: ZK TCP protocol ≠ ZKTeco brand. Many OEM boards use this
        # protocol. We leave vendor/brand as UNKNOWN unless the device itself
        # reports an OEM vendor via ~OEMVendor. Do NOT guess.
        vendor = (opts.get("~OEMVendor") or "").strip() or None
        brand = None
        model = opts.get("~DeviceName")
        if vendor:
            v = vendor.lower()
            if v in ("zkteco", "zksoftware", "zk-teco"):
                brand = "ZKTeco"
            else:
                # OEM brand explicitly reported by the device (still ZK-protocol)
                brand = vendor
        # If platform strings strongly hint ZKTeco ("ZMM" is ZKTeco's platform
        # prefix) we still do NOT claim brand=ZKTeco because many clones use
        # those platforms. Protocol is verified, brand stays UNKNOWN.
        info = DeviceInfo(
            platform=opts.get("~Platform"),
            serial_number=opts.get("~SerialNumber"),
            device_name=opts.get("~DeviceName"),
            vendor=vendor if vendor else None,
            mac_address=opts.get("MAC"),
            firmware_version=None,
            brand=brand,  # None (UNKNOWN) unless OEMVendor reports it
            model=model,
            raw=opts,
            source="device (ZK OPTIONS_RRQ) - protocol verified; vendor UNKNOWN unless OEMVendor set",
        )
        # firmware: CMD_GET_VERSION
        try:
            resp = await c.command(1100)
            info.firmware_version = _clean_str(resp["data"])
        except DeviceProtocolError:
            pass
        # time + counts
        try:
            info.device_time = await c.get_time()
        except DeviceProtocolError:
            pass
        try:
            sizes = await c.get_free_sizes()
            info.user_count = sizes.get("user_count")
            info.user_capacity = sizes.get("user_capacity")
            info.fingerprint_count = sizes.get("fingerprint_count")
            info.fingerprint_capacity = sizes.get("fingerprint_capacity")
            info.face_count = sizes.get("face_count")
            info.face_capacity = sizes.get("face_capacity")
            info.attendance_count = sizes.get("attendance_count")
            info.attendance_capacity = sizes.get("attendance_capacity")
            info.raw["free_sizes"] = sizes
        except (DeviceProtocolError, DeviceConnectionError):
            pass
        return info

    async def get_users(self, **kwargs) -> list[DeviceUserRecord]:
        c = await self._session()
        raw = await c.get_users_raw()
        entries = parse_user_entries(raw)
        users: list[DeviceUserRecord] = []
        for e in entries:
            users.append(
                DeviceUserRecord(
                    user_id_on_device=e["user_id"],
                    device_user_sn=e["user_sn"],
                    name=e["name"] or None,
                    card_number=e["card_number"],
                    password_status=(
                        "SET" if e["password_present"] else "NONE"
                    ),
                    privilege_level=e["privilege"],
                    group_number=e["group"],
                    enabled=e["enabled"],
                    password_enabled=e["password_present"],
                    card_enabled=bool(e["card_number"]),
                    raw=e,
                )
            )
        return users

    async def get_attendance_logs(self, **kwargs) -> list[AttendanceRecord]:
        c = await self._session()
        raw = await c.get_attendance_raw()
        entries = parse_att_entries(raw)
        records: list[AttendanceRecord] = []
        for e in entries:
            records.append(
                AttendanceRecord(
                    user_id_on_device=e["user_id"] or None,
                    user_sn=e["user_sn"],
                    event_time=e["event_time"],
                    verification_type=e["verification_type"],
                    event_type=e["event_state"],
                    raw_state=e.get("raw_state"),
                    raw_punch=e.get("raw_punch"),
                    raw=e,
                )
            )
        return records

    async def get_attendance_log_count(self) -> int:
        c = await self._session()
        sizes = await c.get_free_sizes()
        return int(sizes.get("attendance_count") or 0)

    async def create_user(self, user: DeviceUserRecord) -> dict:
        return await self._write_user(user)

    async def update_user(self, user: DeviceUserRecord) -> dict:
        return await self._write_user(user)

    async def _write_user(self, user: DeviceUserRecord) -> dict:
        c = await self._session()
        existing = await self.get_users()
        sn = user.device_user_sn
        if sn is None:
            for u in existing:
                if u.user_id_on_device == user.user_id_on_device:
                    sn = u.device_user_sn
                    break
        if sn is None:
            used = {u.device_user_sn for u in existing}
            sn = max(used, default=0) + 1
        entry = bytearray(72)
        struct.pack_into("<H", entry, 0, sn & 0xFFFF)
        privilege = user.privilege_level if user.privilege_level is not None else 0
        enabled_bit = 0 if user.enabled else 1
        entry[2] = (privilege << 1) | enabled_bit
        pw = (user.raw or {}).get("password") or ""
        pw_bytes = pw.encode("latin-1", "replace")[:7]  # 8 bytes incl NUL
        entry[3 : 3 + len(pw_bytes)] = pw_bytes
        name = (user.name or "")[:23].encode("utf-8", "replace")
        entry[11 : 11 + len(name)] = name
        card = int(user.card_number or 0)
        struct.pack_into("<I", entry, 35, card)
        entry[39] = user.group_number if user.group_number is not None else 1
        uid = user.user_id_on_device[:9].encode("latin-1", "replace")
        entry[48 : 48 + len(uid)] = uid
        await c.disable_device()
        try:
            await c.command(8, bytes(entry))  # CMD_USER_WRQ
            await c.command(1013)  # CMD_REFRESHDATA
        finally:
            await c.enable_device()
        return {"user_sn": sn, "user_id": user.user_id_on_device}

    async def delete_user(self, user_id_on_device: str) -> dict:
        c = await self._session()
        existing = await self.get_users()
        sn = None
        for u in existing:
            if u.user_id_on_device == user_id_on_device:
                sn = u.device_user_sn
                break
        if sn is None:
            raise NotSupported(
                f"user {user_id_on_device!r} not present on device", supported=False
            )
        await c.disable_device()
        try:
            await c.command(18, struct.pack("<H", sn))  # CMD_DELETE_USER
            await c.command(1013)  # CMD_REFRESHDATA
        finally:
            await c.enable_device()
        return {"deleted_user_id": user_id_on_device, "user_sn": sn}

    async def clear_attendance_logs(self) -> dict:
        c = await self._session()
        await c.disable_device()
        try:
            await c.command(15)  # CMD_CLEAR_ATTLOG
            await c.command(1013)  # CMD_REFRESHDATA
        finally:
            await c.enable_device()
        return {"cleared": True}

    async def set_time(self, when: dt.datetime) -> dict:
        c = await self._session()
        await c.set_time(when)
        return {"set_time": when.isoformat()}

    # ------------------------------------------------------------------
    def supports_realtime(self) -> bool:
        return True

    async def stream_realtime_events(self, event_cb, run_forever: bool = True):
        """Subscribe to CMD_REG_EVENT and forward parsed attendance events.

        ``event_cb(AttendanceRecord | dict)`` is awaited for each packet.
        Keeps the session open; the device pushes packets whenever a punch
        happens.  Only documented behaviour is parsed; unknown event codes
        are forwarded verbatim in a dict.
        """
        c = await self._session()
        await c.command(CMD_REG_EVENT, b"\xff\xff\x00\x00", manage_reply=False)
        import asyncio

        while True:
            try:
                frame = await c._recv_frame()
            except (
                DeviceConnectionError,
                DeviceProtocolError,
                asyncio.TimeoutError,
                ConnectionError,
                OSError,
            ):
                break
            if frame["command"] == CMD_REG_EVENT:
                event_code = frame["session_id"]
                data = frame["data"]
                # acknowledge per spec
                ack = encode_packet(2000, c.session_id, 0, b"")
                await c._send(ack)
                if event_code == 1 and len(data) >= 32:  # EF_ATTLOG
                    user_id = _clean_str(data[0:9])
                    verify = data[24]
                    year, mon, day, hh, mm, ss = data[26:32]
                    try:
                        when = dt.datetime(
                            2000 + year, mon, day, hh, mm, ss
                        )
                    except ValueError:
                        when = None
                    record = AttendanceRecord(
                        user_id_on_device=user_id,
                        verification_type={
                            0: "PASSWORD", 1: "FINGERPRINT", 2: "CARD",
                        }.get(verify, "UNKNOWN"),
                        event_time=when,
                        raw={"event_code": event_code, "data": data.hex()},
                    )
                    await event_cb(record)
                else:
                    await event_cb(
                        {"event_code": event_code, "raw": data.hex()}
                    )
            elif frame["command"] == 2000:
                continue
            if not run_forever:
                break

    # ------------------------------------------------------------------
    def declare_capabilities(self) -> dict[str, dict]:
        # Support statements below describe the *documented protocol*; each
        # capability is additionally marked verified only after a real
        # device answers (the discovery/verify flow sets that flag).
        return {
            "device_info": {"supported": True, "source": "ZK protocol spec (OPTIONS_RRQ)"},
            "read_users": {"supported": True, "source": "ZK protocol spec (DATA_WRRQ 01090005)"},
            "read_user": {"supported": False, "reason": "implemented via full list read", "source": "adapter"},
            "create_users": {"supported": True, "source": "ZK protocol spec (USER_WRQ)"},
            "update_users": {"supported": True, "source": "ZK protocol spec (USER_WRQ overwrite)"},
            "delete_users": {"supported": True, "source": "ZK protocol spec (DELETE_USER)"},
            "read_logs": {"supported": True, "source": "ZK protocol spec (DATA_WRRQ 010d0000)"},
            "delete_logs": {"supported": True, "source": "ZK protocol spec (CLEAR_ATTLOG)"},
            "get_log_count": {"supported": True, "source": "ZK protocol spec (GET_FREE_SIZES)"},
            "sync_users_to_device": {"supported": True, "source": "built on create/update/delete"},
            "sync_users_from_device": {"supported": True, "source": "built on read_users"},
            "realtime_events": {"supported": True, "source": "ZK protocol spec (REG_EVENT)"},
            "fingerprint": {"supported": True, "source": "ZK platform biometric devices"},
            "face": {"supported": False, "source": "device-dependent (check ~FaceFunOn)"},
            "card": {"supported": True, "source": "ZK platform card support"},
            "password": {"supported": True, "source": "ZK platform PIN/password"},
            "set_time": {"supported": True, "source": "ZK protocol spec (SET_TIME)"},
            "get_time": {"supported": True, "source": "ZK protocol spec (GET_TIME)"},
            "clear_data": {"supported": True, "source": "ZK protocol spec (CLEAR_DATA)"},
            "read_templates": {"supported": False, "reason": "template sync intentionally not enabled", "source": "adapter"},
            "write_templates": {"supported": False, "reason": "not enabled", "source": "adapter"},
            "read_operational_logs": {"supported": True, "source": "ZK protocol spec (DATA_WRRQ 01220000)"},
        }



"""Generic SNMP adapter (SNMPv1/v2c system query).

Implements just enough real SNMP (BER-encoded GET requests, v1 + v2c framing)
to collect sysDescr / sysName / sysObjectID evidence from unknown devices.
Attendance operations are not supported through generic SNMP - there is no
standard MIB for attendance records, so the adapter says so instead of
guessing vendor MIBs.
"""
from __future__ import annotations

import asyncio
import struct
from typing import Optional

from app.adapters.base import (
    AdapterProbeResult,
    AttendanceAdapter,
    DeviceInfo,
)

OID_SYS_DESCR = (1, 3, 6, 1, 2, 1, 1, 1, 0)
OID_SYS_OBJECT_ID = (1, 3, 6, 1, 2, 1, 1, 2, 0)
OID_SYS_NAME = (1, 3, 6, 1, 2, 1, 1, 5, 0)


# --- minimal BER helpers -------------------------------------------------

def _encode_length(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    out = b""
    while n:
        out = bytes([n & 0xFF]) + out
        n >>= 8
    return bytes([0x80 | len(out)]) + out


def _tlv(tag: int, content: bytes) -> bytes:
    return bytes([tag]) + _encode_length(len(content)) + content


def _oid_bytes(oid: tuple) -> bytes:
    if len(oid) < 2:
        raise ValueError("oid too short")
    first = oid[0] * 40 + oid[1]
    out = bytearray([first])
    for n in oid[2:]:
        chunks = []
        while True:
            chunks.insert(0, n & 0x7F)
            n >>= 7
            if n == 0:
                break
        for i, c in enumerate(chunks):
            if i != len(chunks) - 1:
                c |= 0x80
            out.append(c)
    return bytes(out)


def _int_bytes(value: int) -> bytes:
    if value < 0:
        return b"\xff"  # -1 (as used for timeouts) - only for small negatives
    out = bytearray()
    while value:
        out.insert(0, value & 0xFF)
        value >>= 8
    return bytes(out) or b"\x00"


def _build_get(community: str, oids: list[tuple], version: int = 1, reqid: int = 1) -> bytes:
    varbinds = b"".join(
        _tlv(0x30, _tlv(0x06, _oid_bytes(oid)) + _tlv(0x05, b"")) for oid in oids
    )
    pdu_body = _tlv(0x02, _int_bytes(reqid)) + _tlv(0x02, b"\x00") + _tlv(0x02, b"\x00") + _tlv(0x30, varbinds)
    pdu_tag = 0xA0 if version == 0 else 0xA0  # GET request same tag for v1/v2c
    msg = (
        _tlv(0x02, _int_bytes(version))
        + _tlv(0x04, community.encode("utf-8"))
        + _tlv(pdu_tag, pdu_body)
    )
    return _tlv(0x30, msg)


def _parse_response(data: bytes, reqid: int) -> dict:
    """Parse a minimal v1/v2c GetResponse and return oid->value strings."""
    out: dict[str, str] = {}
    if len(data) < 2 or data[0] != 0x30:
        return out
    # skip outer seq header quickly using a cursor-based decoder
    def read_len(buf: bytes, pos: int):
        first = buf[pos]
        pos += 1
        if first < 0x80:
            return first, pos
        n = first & 0x7F
        ln = int.from_bytes(buf[pos : pos + n], "big")
        return ln, pos + n

    _, pos = read_len(data, 1)
    # version
    if data[pos] != 0x02:
        return out
    pos += 2 + data[pos + 1]
    # community
    if data[pos] != 0x04:
        return out
    clen = data[pos + 1]
    pos += 2 + clen
    # pdu
    if data[pos] not in (0xA0, 0xA2):
        return out
    _, pos = read_len(data, pos + 1)
    pos += 1 + data[pos] + 1  # req-id int
    pos += 1 + data[pos] + 1  # error-status int
    pos += 1 + data[pos] + 1  # error-index int
    # varbind list
    if data[pos] != 0x30:
        return out
    vblen, pos = read_len(data, pos + 1)
    end = pos + vblen
    while pos < end:
        if data[pos] != 0x30:
            break
        _, pos = read_len(data, pos + 1)
        if data[pos] != 0x06:
            break
        olen = data[pos + 1]
        raw_oid = data[pos + 2 : pos + 2 + olen]
        pos += 2 + olen
        tag = data[pos]
        vlen = data[pos + 1]
        value = data[pos + 2 : pos + 2 + vlen]
        pos += 2 + vlen
        oid = _decode_oid(raw_oid)
        if tag == 0x05:  # noSuchInstance / endOfMib
            out[oid] = ""
        elif tag == 0x04:
            out[oid] = value.decode("utf-8", "replace")
        elif tag == 0x02:
            out[oid] = str(int.from_bytes(value, "big", signed=True))
        elif tag == 0x41:
            out[oid] = str(int.from_bytes(value, "big", signed=True))
        elif tag == 0x06:
            out[oid] = ".".join(map(str, _decode_oid(value)))
        else:
            out[oid] = value.hex()
    return out


def _decode_oid(raw: bytes) -> str:
    if not raw:
        return ""
    parts = [raw[0] // 40, raw[0] % 40]
    val = 0
    for b in raw[1:]:
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            parts.append(val)
            val = 0
    return ".".join(map(str, parts))


def _oid_str(t: tuple) -> str:
    return ".".join(map(str, t))


# -------------------------------------------------------------------------


class GenericSnmpAdapter(AttendanceAdapter):
    id_ = "generic_snmp"
    display_name = "Generic SNMP"
    description = "Minimal SNMPv1/v2c evidence adapter (system MIB only)."
    priority = 200

    def __init__(self, device_cfg: Optional[dict] = None):
        super().__init__(device_cfg)
        cfg = device_cfg or {}
        self.host = cfg.get("ip_address", "")
        self.port = int(cfg.get("port") or 161)
        self.community = str(cfg.get("snmp_community") or "public")

    @classmethod
    async def probe(cls, ip: str, port: int, timeout_s: float) -> AdapterProbeResult:
        adapter = cls({"ip_address": ip, "port": port})
        result = await adapter._query([OID_SYS_DESCR])
        if result:
            return AdapterProbeResult(
                protocol="snmp",
                detected=True,
                confidence=0.8,
                source="SNMPv1/v2c GET sysDescr",
                evidence=result,
                detail="SNMP system query answered",
            )
        return AdapterProbeResult(
            protocol="snmp", detected=False, confidence=0.0,
            source="SNMP GET", detail="no SNMP response",
        )

    async def _query(self, oids: list[tuple]) -> dict:
        def blocking_query() -> dict:
            import socket

            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(float(self.device_cfg.get("read_timeout_s", 2.0)))
            try:
                pkt = _build_get(self.community, oids, version=1, reqid=12345)
                s.sendto(pkt, (self.host, self.port))
                data, _ = s.recvfrom(65535)
                parsed = _parse_response(data, 12345)
                return {_oid_str(oid): parsed[_oid_str(oid)] for oid in oids if _oid_str(oid) in parsed}
            except (OSError, Exception):  # noqa: BLE001
                return {}
            finally:
                s.close()

        return await asyncio.to_thread(blocking_query)

    async def test_connection(self) -> dict:
        res = await self._query([OID_SYS_DESCR, OID_SYS_NAME])
        return {"ok": bool(res), "detail": "SNMP system query answered" if res else "no SNMP response", "evidence": res}

    async def connect(self) -> None:
        pass

    async def get_device_info(self) -> DeviceInfo:
        res = await self._query([OID_SYS_DESCR, OID_SYS_NAME, OID_SYS_OBJECT_ID])
        if not res:
            raise DeviceInfoError("no SNMP response")
        info = DeviceInfo(
            raw={
                "sysDescr": res.get("1.3.6.1.2.1.1.1.0"),
                "sysName": res.get("1.3.6.1.2.1.1.5.0"),
                "sysObjectID": res.get("1.3.6.1.2.1.1.2.0"),
            },
            source="snmp",
            hostname=res.get("1.3.6.1.2.1.1.5.0"),
        )
        return info

    def declare_capabilities(self) -> dict[str, dict]:
        return {
            "device_info": {"supported": True, "source": "SNMP system MIB"},
            "read_users": {"supported": False, "reason": "no standard attendance MIB"},
            "read_logs": {"supported": False, "reason": "no standard attendance MIB"},
            "create_users": {"supported": False, "reason": "no standard attendance MIB"},
            "update_users": {"supported": False, "reason": "no standard attendance MIB"},
            "delete_users": {"supported": False, "reason": "no standard attendance MIB"},
            "delete_logs": {"supported": False, "reason": "no standard attendance MIB"},
            "get_log_count": {"supported": False, "reason": "no standard attendance MIB"},
            "sync_users_to_device": {"supported": False, "reason": "no standard attendance MIB"},
            "sync_users_from_device": {"supported": False, "reason": "no standard attendance MIB"},
            "realtime_events": {"supported": False, "reason": "no standard trap semantics for attendance"},
            "fingerprint": {"supported": False, "source": "unknown"},
            "face": {"supported": False, "source": "unknown"},
            "card": {"supported": False, "source": "unknown"},
            "password": {"supported": False, "source": "unknown"},
            "set_time": {"supported": False, "reason": "no attendance MIB"},
            "get_time": {"supported": False, "reason": "no attendance MIB"},
            "clear_data": {"supported": False, "reason": "no standard MIB"},
            "read_templates": {"supported": False, "reason": "N/A"},
            "write_templates": {"supported": False, "reason": "N/A"},
            "read_operational_logs": {"supported": False, "reason": "no standard MIB"},
        }


class DeviceInfoError(Exception):
    pass

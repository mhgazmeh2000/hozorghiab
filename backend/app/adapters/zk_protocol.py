"""ZKTeco standalone-device TCP protocol (port 4370).

Implemented from the public, reverse-engineered protocol specification by
Alexander Marin (github.com/adrobinoga/zk-protocol), which is derived from
ZKTeco's own "Standalone series communication protocol" documentation and
packet captures.  Framing and the checksum algorithm are validated in unit
tests against the spec's test vectors.

Frame layout (all multi-byte integers little-endian):
    0..4   start marker           50 50 82 7d
    4..8   payload size           uint32
    8..10  command id             uint16
    10..12 checksum               uint16  (sum of payload, 1's complement)
    12..14 session id             uint16  (assigned by device on connect)
    14..16 reply number           uint16  (starts 0, increments per request)
    16..   data
"""
from __future__ import annotations

import asyncio
import datetime as dt
import struct
from typing import Optional

from app.adapters.base import (
    DeviceConnectionError,
    DeviceProtocolError,
)

START_MARKER = b"\x50\x50\x82\x7d"

# --- command ids ---------------------------------------------------------
CMD_CONNECT = 1000
CMD_EXIT = 1001
CMD_ENABLEDEVICE = 1002
CMD_DISABLEDEVICE = 1003
CMD_REFRESHDATA = 1013
CMD_GET_VERSION = 1100
CMD_AUTH = 1102
CMD_PREPARE_DATA = 1500
CMD_DATA = 1501
CMD_FREE_DATA = 1502
CMD_DATA_WRRQ = 1503
CMD_DATA_RDY = 1504
CMD_DB_RRQ = 7
CMD_USER_WRQ = 8
CMD_OPTIONS_RRQ = 11
CMD_OPTIONS_WRQ = 12
CMD_ATTLOG_RRQ = 13
CMD_CLEAR_ATTLOG = 15
CMD_DELETE_USER = 18
CMD_GET_FREE_SIZES = 50
CMD_GET_TIME = 201
CMD_SET_TIME = 202
CMD_REG_EVENT = 500
CMD_STATE_RRQ = 64

# --- reply codes ---------------------------------------------------------
CMD_ACK_OK = 2000
CMD_ACK_ERROR = 2001
CMD_ACK_DATA = 2002
CMD_ACK_UNAUTH = 2005
CMD_ACK_UNKNOWN = 65535

# read dataset request bodies (11 bytes) documented by the spec
DATAID_USERS = bytes.fromhex("0109000500000000000000")   # CMD_DB_RRQ
DATAID_ATTLOG = bytes.fromhex("010d0000000000000000")    # CMD_ATTLOG_RRQ
DATAID_TEMPLATES = bytes.fromhex("0107000200000000000000")  # CMD_USERTEMP_RRQ

VERIFY_MAP = {0: "PASSWORD", 1: "FINGERPRINT", 2: "CARD"}
VERIFY_MAP_INV = {"PASSWORD": 0, "FINGERPRINT": 1, "CARD": 2}
STATE_MAP = {
    0: "CHECK_IN",
    1: "CHECK_OUT",
    2: "BREAK_OUT",
    3: "BREAK_IN",
    4: "OVERTIME_IN",
    5: "OVERTIME_OUT",
}
PRIV_MAP = {0: "common", 1: "enroll", 3: "admin", 7: "super_admin"}

USER_ENTRY_SIZE = 72
ATT_ENTRY_SIZE = 40


def checksum(payload: bytes) -> int:
    """16-bit 1's-complement checksum over a full payload (see spec)."""
    if len(payload) % 2:
        payload = payload + b"\x00"
    total = sum(struct.unpack(f"<{len(payload) // 2}H", payload))
    total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def encode_packet(command: int, session_id: int, reply_id: int, data: bytes = b"") -> bytes:
    head = struct.pack("<H", command) + struct.pack("<H", 0) + struct.pack(
        "<H", session_id
    ) + struct.pack("<H", reply_id)
    payload = head + data
    chk = checksum(payload)
    payload = payload[:2] + struct.pack("<H", chk) + payload[4:]
    return START_MARKER + struct.pack("<I", len(payload)) + payload


def decode_frame(buf: bytes) -> dict:
    """Decode a complete frame (marker + size + payload)."""
    if len(buf) < 12:
        raise DeviceProtocolError("frame too short")
    if buf[:4] != START_MARKER:
        raise DeviceProtocolError(f"bad start marker {buf[:4].hex()}")
    (size,) = struct.unpack("<I", buf[4:8])
    if len(buf) < 8 + size:
        raise DeviceProtocolError("truncated frame")
    payload = buf[8 : 8 + size]
    command, stored_chk, session_id, reply_id = struct.unpack("<HHHH", payload[:8])
    body = payload[8:]
    expected = checksum(payload[:2] + b"\x00\x00" + payload[4:])
    return {
        "command": command,
        "session_id": session_id,
        "reply_id": reply_id,
        "data": body,
        "checksum_ok": expected == stored_chk,
    }


def encode_zk_time(when: dt.datetime) -> int:
    yy = when.year % 100
    return (
        ((yy * 12 * 31) + ((when.month - 1) * 31) + (when.day - 1)) * 86400
        + when.hour * 3600
        + when.minute * 60
        + when.second
    )


def decode_zk_time(enc: int) -> dt.datetime:
    seconds = enc % 60
    total_min = enc // 60
    minutes = total_min % 60
    total_h = total_min // 60
    hours = total_h % 24
    days = total_h // 24
    day = days % 31 + 1
    months_total = days // 31
    month = months_total % 12 + 1
    year = months_total // 12 + 2000
    try:
        return dt.datetime(year, month, day, hours, minutes, seconds)
    except ValueError:  # tolerate impossible encoded dates honestly
        return dt.datetime(1970, 1, 1)


def parse_user_entries(data: bytes) -> list[dict]:
    if len(data) < 4:
        return []
    (total,) = struct.unpack("<I", data[:4])
    body = data[4:]
    if total and total != len(body) and total != len(data) - 4 + 4:
        # some firmwares include size differently; be tolerant on entry parsing
        pass
    users = []
    if len(body) % USER_ENTRY_SIZE:
        # firmware variations exist; do not guess - require exact framing
        raise DeviceProtocolError(
            f"user dataset size {len(body)} is not a multiple of {USER_ENTRY_SIZE}"
        )
    for off in range(0, len(body), USER_ENTRY_SIZE):
        e = body[off : off + USER_ENTRY_SIZE]
        (user_sn,) = struct.unpack("<H", e[0:2])
        token = e[2]
        privilege = (token >> 1) & 0x07
        enabled = not (token & 0x01)
        password = e[3:11].split(b"\x00")[0].decode("latin-1", "replace")
        name = e[11:35].split(b"\x00")[0].decode("utf-8", "replace")
        (card,) = struct.unpack("<I", e[35:39])
        group = e[39]
        (tz_flag,) = struct.unpack("<H", e[40:42])
        user_id = e[48:57].split(b"\x00")[0].decode("latin-1", "replace")
        users.append(
            {
                "user_sn": user_sn,
                "privilege": privilege,
                "enabled": enabled,
                "password_present": bool(password),
                "name": name,
                "card_number": str(card) if card else None,
                "group": group,
                "timezone_flag": tz_flag,
                "user_id": user_id,
                "_raw": e.hex(),
            }
        )
    return users


def parse_att_entries(data: bytes) -> list[dict]:
    if len(data) < 4:
        return []
    body = data[4:]
    if len(body) % ATT_ENTRY_SIZE:
        raise DeviceProtocolError(
            f"attendance dataset size {len(body)} is not a multiple of {ATT_ENTRY_SIZE}"
        )
    logs = []
    for off in range(0, len(body), ATT_ENTRY_SIZE):
        e = body[off : off + ATT_ENTRY_SIZE]
        (user_sn,) = struct.unpack("<H", e[0:2])
        user_id = e[2:11].split(b"\x00")[0].decode("latin-1", "replace")
        verify = e[26]
        (enc_t,) = struct.unpack("<I", e[27:31])
        state = e[31]
        logs.append(
            {
                "user_sn": user_sn,
                "user_id": user_id,
                "verification_type": VERIFY_MAP.get(verify, "UNKNOWN"),
                "verify_code": verify,
                "event_time": decode_zk_time(enc_t),
                "event_state": STATE_MAP.get(state, "UNKNOWN"),
                "state_code": state,
                "raw_state": str(state),
                "raw_punch": str(verify),
                "_raw": e.hex(),
            }
        )
    return logs


# --------------------------------------------------------------------------
# Async session
# --------------------------------------------------------------------------


class ZKConnection:
    """Stateful async client for a ZK TCP session."""

    def __init__(
        self,
        host: str,
        port: int = 4370,
        connect_timeout: float = 3.0,
        read_timeout: float = 10.0,
        password: int = 0,
        comm_key: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.password = password
        self.comm_key = comm_key
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.session_id = 0
        self.reply_id = 0
        self._connected = False
        self._lock = asyncio.Lock()

    # --- transport -----------------------------------------------------
    async def _read_exact(self, n: int) -> bytes:
        data = await asyncio.wait_for(self.reader.readexactly(n), self.read_timeout)
        return data

    async def _recv_frame(self) -> dict:
        head = await self._read_exact(8)
        (size,) = struct.unpack("<I", head[4:8])
        if size > 1024 * 1024 * 16:  # sanity guard against garbage streams
            raise DeviceProtocolError(f"implausible payload size {size}")
        payload = await self._read_exact(size)
        return decode_frame(head + payload)

    async def _send(self, frame: bytes) -> None:
        self.writer.write(frame)
        await self.writer.drain()

    async def command(
        self,
        command: int,
        data: bytes = b"",
        *,
        expect: int = CMD_ACK_OK,
        manage_reply: bool = True,
        expect_reply_commands: Optional[list[int]] = None,
    ) -> dict:
        """Send one command and read the immediate reply frame."""
        if not self._connected:
            raise DeviceConnectionError("ZK connection is not open")
        async with self._lock:
            frame = encode_packet(
                command, self.session_id, self.reply_id, data
            )
            await self._send(frame)
            if manage_reply:
                self.reply_id += 1
            resp = await self._recv_frame()
            allowed = [expect] if expect_reply_commands is None else expect_reply_commands
            if resp["command"] not in allowed:
                if resp["command"] == CMD_ACK_UNAUTH:
                    raise DeviceConnectionError(
                        "device refused connection (communication key required)"
                    )
                if resp["command"] in (CMD_ACK_ERROR, CMD_ACK_UNKNOWN):
                    raise DeviceProtocolError(
                        f"device returned error for command {command} "
                        f"(reply {resp['command']})"
                    )
                raise DeviceProtocolError(
                    f"unexpected reply command {resp['command']} for {command}"
                )
            if not resp["checksum_ok"]:
                raise DeviceProtocolError("bad checksum in device reply")
            return resp

    # --- session --------------------------------------------------------
    async def connect(self) -> None:
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                self.connect_timeout,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise DeviceConnectionError(
                f"cannot open TCP connection to {self.host}:{self.port}: {exc}"
            ) from exc
        self._connected = True
        self.session_id = 0
        self.reply_id = 0
        try:
            resp = await self.command(CMD_CONNECT, manage_reply=False)
            if resp["command"] == CMD_ACK_UNAUTH:
                raise DeviceConnectionError(
                    "connection refused: device has a communication key set"
                )
            self.session_id = resp["session_id"]
            # After connect, spec: set SDKBuild=1 via OPTIONS_WRQ
            try:
                await self.command(CMD_OPTIONS_WRQ, b"SDKBuild=1\x00")
            except DeviceProtocolError:
                pass  # some firmwares ignore SDKBuild
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        if self._connected and self.writer is not None:
            try:
                await self.command(CMD_EXIT)
            except Exception:
                pass
        if self.writer is not None:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        self._connected = False

    async def __aenter__(self) -> "ZKConnection":
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    # --- helpers ---------------------------------------------------------
    async def disable_device(self) -> None:
        await self.command(CMD_DISABLEDEVICE)

    async def enable_device(self) -> None:
        try:
            await self.command(CMD_ENABLEDEVICE)
        except DeviceProtocolError:
            pass

    async def read_option(self, name: str) -> Optional[str]:
        """Read a single parameter (e.g. ~SerialNumber)."""
        try:
            resp = await self.command(CMD_OPTIONS_RRQ, name.encode("latin-1") + b"\x00")
        except DeviceProtocolError:
            return None
        data = resp["data"].rstrip(b"\x00").decode("latin-1", "replace")
        if "=" in data:
            return data.split("=", 1)[1]
        return data

    async def read_options(self, names: list[str]) -> dict:
        out = {}
        for name in names:
            value = await self.read_option(name)
            if value is not None:
                out[name] = value
        return out

    async def get_time(self) -> dt.datetime:
        resp = await self.command(CMD_GET_TIME)
        (enc_t,) = struct.unpack("<I", resp["data"][:4])
        return decode_zk_time(enc_t)

    async def set_time(self, when: dt.datetime) -> None:
        await self.command(CMD_SET_TIME, struct.pack("<I", encode_zk_time(when)))
        await self.command(CMD_REFRESHDATA)

    async def get_free_sizes(self) -> dict:
        """Read the 92-byte status structure (needs disable/enable wrapper)."""
        await self.disable_device()
        try:
            resp = await self.command(CMD_GET_FREE_SIZES)
            data = resp["data"]
            if len(data) < 92:
                raise DeviceProtocolError("short GET_FREE_SIZES payload")
            vals = struct.unpack("<23I", data[:92])
            # offsets per spec (bytes / 4)
            return {
                "user_count": vals[4],
                "fingerprint_count": vals[6],
                "attendance_count": vals[8],
                "oplog_count": vals[10],
                "admin_count": vals[12],
                "password_count": vals[13],
                "fingerprint_capacity": vals[14],
                "user_capacity": vals[15],
                "attendance_capacity": vals[16],
                "remaining_fingerprint": vals[17],
                "remaining_user": vals[18],
                "remaining_attendance": vals[19],
                "face_count": vals[20],
                "face_capacity": vals[22],
            }
        finally:
            await self.enable_device()

    async def read_dataset(self, data_id: bytes) -> bytes:
        """Generic dataset read following the spec's small/large flows."""
        await self.disable_device()
        try:
            try:
                resp = await self.command(
                    CMD_DATA_WRRQ,
                    data_id,
                    expect=CMD_DATA,
                    expect_reply_commands=[CMD_DATA, CMD_ACK_OK],
                )
            except DeviceProtocolError as exc:
                # Some ZK/OEM firmware rejects DATA_WRRQ but accepts the
                # legacy database-read command for the same dataset.
                if "command 1503" not in str(exc):
                    raise
                try:
                    resp = await self.command(
                        CMD_DB_RRQ,
                        data_id,
                        expect=CMD_DATA,
                        expect_reply_commands=[CMD_DATA, CMD_ACK_OK],
                    )
                except DeviceProtocolError as fallback_exc:
                    raise DeviceProtocolError(
                        "device rejected dataset read via CMD_DATA_WRRQ (1503) "
                        "and CMD_DB_RRQ (7); dataset is not supported by this firmware"
                    ) from fallback_exc
            if resp["command"] == CMD_DATA:
                return resp["data"]
            # large dataset flow: resp carries data-stat (9 bytes)
            stat = resp["data"]
            if len(stat) < 9:
                raise DeviceProtocolError("short data-stat reply")
            size = struct.unpack("<I", stat[1:5])[0]
            rdy = b"\x00\x00\x00\x00" + struct.pack("<I", size)
            await self.command(CMD_DATA_RDY, rdy, manage_reply=False)
            # device sends PREPARE_DATA, DATA, then ACK_OK with same reply num
            chunks: list[bytes] = []
            collected = 0
            deadline = asyncio.get_event_loop().time() + self.read_timeout * 4
            while collected < size and asyncio.get_event_loop().time() < deadline:
                frame = await self._recv_frame()
                if frame["command"] == CMD_PREPARE_DATA:
                    continue
                if frame["command"] == CMD_DATA:
                    chunks.append(frame["data"])
                    collected += len(frame["data"])
                    continue
                if frame["command"] == CMD_ACK_OK:
                    break
            self.reply_id += 1
            try:
                await self.command(CMD_FREE_DATA)
            except DeviceProtocolError:
                pass
            return b"".join(chunks)[:size]
        finally:
            await self.enable_device()

    # --- high-level reads -------------------------------------------------
    async def get_users_raw(self) -> bytes:
        return await self.read_dataset(DATAID_USERS)

    async def get_attendance_raw(self) -> bytes:
        return await self.read_dataset(DATAID_ATTLOG)

    async def get_templates_raw(self) -> bytes:
        return await self.read_dataset(DATAID_TEMPLATES)

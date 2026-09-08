"""Mock devices used by tests (and the demo).

ZK mock speaks the same documented wire protocol as the real adapter client,
so adapter <-> mock exchanges exercise the real framing/parsing code paths.
"""
from __future__ import annotations

import datetime as dt
import socket
import struct
import threading

from app.adapters.zk_protocol import (
    CMD_ACK_OK,
    CMD_CONNECT,
    CMD_DATA,
    CMD_DATA_RDY,
    CMD_DATA_WRRQ,
    CMD_DISABLEDEVICE,
    CMD_ENABLEDEVICE,
    CMD_EXIT,
    CMD_FREE_DATA,
    CMD_GET_FREE_SIZES,
    CMD_GET_TIME,
    CMD_GET_VERSION,
    CMD_OPTIONS_RRQ,
    CMD_OPTIONS_WRQ,
    CMD_PREPARE_DATA,
    CMD_REFRESHDATA,
    CMD_SET_TIME,
    CMD_USER_WRQ,
    CMD_DELETE_USER,
    CMD_CLEAR_ATTLOG,
    DATAID_ATTLOG,
    DATAID_USERS,
    USER_ENTRY_SIZE,
    ATT_ENTRY_SIZE,
    checksum,
    encode_packet,
)


def build_user_entry(
    user_sn: int,
    user_id: str,
    name: str = "Ned",
    password: str = "444",
    card: int = 0xDE,
    group: int = 2,
    privilege: int = 0,
    enabled: bool = True,
) -> bytes:
    e = bytearray(USER_ENTRY_SIZE)
    struct.pack_into("<H", e, 0, user_sn)
    e[2] = (privilege << 1) | (0 if enabled else 1)
    pw = password.encode("latin-1")[:7]
    e[3 : 3 + len(pw)] = pw
    nm = name.encode("utf-8")[:23]
    e[11 : 11 + len(nm)] = nm
    struct.pack_into("<I", e, 35, card)
    e[39] = group
    uid = user_id.encode("latin-1")[:9]
    e[48 : 48 + len(uid)] = uid
    return bytes(e)


def build_att_entry(
    user_sn: int,
    user_id: str,
    verify: int,
    when: dt.datetime,
    state: int = 0,
) -> bytes:
    e = bytearray(ATT_ENTRY_SIZE)
    struct.pack_into("<H", e, 0, user_sn)
    uid = user_id.encode("latin-1")[:9]
    e[2 : 2 + len(uid)] = uid
    e[26] = verify
    enc = (
        (((when.year % 100) * 12 * 31) + ((when.month - 1) * 31) + (when.day - 1))
        * 86400
        + when.hour * 3600
        + when.minute * 60
        + when.second
    )
    struct.pack_into("<I", e, 27, enc)
    e[31] = state
    return bytes(e)


class MockZKDevice:
    """Threaded ZK TCP mock device on 127.0.0.1."""

    def __init__(
        self,
        users=None,
        attendance=None,
        serial: str = "ZK-MOCK-0001",
        device_name: str = "K14",
        platform: str = "ZEM760",
        vendor: str = "ZKTeco",
        firmware: str = "Ver 6.60 Apr 28 2015",
        commkey_protected: bool = False,
    ):
        self.users = users or [
            {
                "sn": 13,
                "user_id": "555",
                "name": "Ned",
                "password": "444",
                "card": 0xDE,
            },
            {
                "sn": 14,
                "user_id": "1002",
                "name": "محمد احمدی",
                "password": "",
                "card": 0,
            },
        ]
        self.attendance = attendance or [
            {
                "sn": 13,
                "user_id": "555",
                "verify": 1,
                "when": dt.datetime(2018, 6, 25, 17, 41, 5),
                "state": 0,
            },
            {
                "sn": 14,
                "user_id": "1002",
                "verify": 2,
                "when": dt.datetime(2024, 2, 10, 8, 2, 33),
                "state": 0,
            },
            {
                "sn": 13,
                "user_id": "555",
                "verify": 1,
                "when": dt.datetime(2024, 2, 10, 17, 30, 0),
                "state": 1,
            },
        ]
        self.serial = serial
        self.device_name = device_name
        self.platform = platform
        self.vendor = vendor
        self.firmware = firmware
        self.commkey_protected = commkey_protected
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.port: int = 0
        self._connections = 0

    def start(self) -> int:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()
        return self.port

    def stop(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    # -- server ----------------------------------------------------------
    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self._connections += 1
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _read_frame(self, conn: socket.socket) -> dict | None:
        head = b""
        while len(head) < 8:
            chunk = conn.recv(8 - len(head))
            if not chunk:
                return None
            head += chunk
        (size,) = struct.unpack("<I", head[4:8])
        payload = b""
        while len(payload) < size:
            chunk = conn.recv(size - len(payload))
            if not chunk:
                return None
            payload += chunk
        return {
            "payload": payload,
            "command": struct.unpack("<H", payload[0:2])[0],
            "session_id": struct.unpack("<H", payload[4:6])[0],
            "reply_id": struct.unpack("<H", payload[6:8])[0],
            "data": payload[8:],
        }

    def _handle(self, conn: socket.socket):
        session_id = 0x8DF3
        reply = 0
        try:
            conn.settimeout(10)
            while True:
                frame = self._read_frame(conn)
                if frame is None:
                    break
                cmd = frame["command"]
                data = frame["data"]
                reply_out = reply
                body = b""

                def send(code: int, payload: bytes = b"", r: int | None = None):
                    pkt = encode_packet(code, session_id, reply if r is None else r, payload)
                    conn.sendall(pkt)

                if cmd == CMD_CONNECT:
                    session_id = 0x8DF3
                    send(CMD_ACK_OK)
                    reply += 1
                elif cmd == CMD_EXIT:
                    send(CMD_ACK_OK)
                    break
                elif cmd == CMD_OPTIONS_WRQ:
                    send(CMD_ACK_OK)
                    reply += 1
                elif cmd == CMD_OPTIONS_RRQ:
                    name = data.rstrip(b"\x00").decode("latin-1")
                    values = {
                        "~Platform": self.platform,
                        "~SerialNumber": self.serial,
                        "~DeviceName": self.device_name,
                        "~OEMVendor": self.vendor,
                        "MAC": "00:1C:B3:AA:BB:CC",
                        "~ProductTime": "2023-01-01 00:00:00",
                        "~ZKFPVersion": "10.0.2.2",
                        "FingerFunOn": "1",
                        "WorkCode": "0",
                    }
                    if name in values:
                        body = f"{name}={values[name]}\x00".encode("latin-1")
                        send(CMD_ACK_OK, body)
                    else:
                        send(2001)  # CMD_ACK_ERROR
                    reply += 1
                elif cmd == CMD_GET_VERSION:
                    send(CMD_ACK_OK, self.firmware.encode("latin-1") + b"\x00")
                    reply += 1
                elif cmd == CMD_GET_TIME:
                    now = dt.datetime(2024, 2, 10, 12, 0, 0)
                    enc = (
                        (((now.year % 100) * 12 * 31) + ((now.month - 1) * 31) + (now.day - 1))
                        * 86400
                        + now.hour * 3600
                        + now.minute * 60
                        + now.second
                    )
                    send(CMD_ACK_OK, struct.pack("<I", enc))
                    reply += 1
                elif cmd == CMD_SET_TIME:
                    send(CMD_ACK_OK)
                    reply += 1
                elif cmd in (CMD_DISABLEDEVICE, CMD_ENABLEDEVICE, CMD_REFRESHDATA):
                    send(CMD_ACK_OK)
                    reply += 1
                elif cmd == CMD_GET_FREE_SIZES:
                    buf = bytearray(92)
                    struct.pack_into("<I", buf, 16, len(self.users))
                    struct.pack_into("<I", buf, 32, len(self.attendance))
                    struct.pack_into("<I", buf, 48, 0)
                    send(CMD_ACK_OK, bytes(buf))
                    reply += 1
                elif cmd == CMD_DATA_WRRQ:
                    if data[:11] == DATAID_USERS:
                        entries = b"".join(
                            build_user_entry(
                                u["sn"], u["user_id"], u.get("name", "Ned"),
                                u.get("password", ""), u.get("card", 0),
                                u.get("group", 1), u.get("privilege", 0),
                            )
                            for u in self.users
                        )
                        body = struct.pack("<I", len(entries)) + entries
                        send(CMD_DATA, body)
                    elif data[:11] == DATAID_ATTLOG:
                        entries = b"".join(
                            build_att_entry(
                                a["sn"], a["user_id"], a["verify"], a["when"],
                                a.get("state", 0),
                            )
                            for a in self.attendance
                        )
                        body = struct.pack("<I", len(entries)) + entries
                        send(CMD_DATA, body)
                    else:
                        send(2001)
                    reply += 1
                elif cmd == CMD_USER_WRQ:
                    # accept user writes (store count unchanged)
                    send(CMD_ACK_OK)
                    reply += 1
                elif cmd == CMD_DELETE_USER:
                    send(CMD_ACK_OK)
                    reply += 1
                elif cmd == CMD_CLEAR_ATTLOG:
                    send(CMD_ACK_OK)
                    reply += 1
                elif cmd in (CMD_DATA_RDY, CMD_PREPARE_DATA, CMD_FREE_DATA):
                    send(CMD_ACK_OK)
                    reply += 1
                else:
                    send(2001)
                    reply += 1
        except (OSError, struct.error):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass


class MockHttpDevice:
    """Minimal HTTP server returning controllable headers/title."""

    def __init__(self, server_header: str = "nginx", title: str = "Device"):
        self.server_header = server_header
        self.title = title
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.port = 0

    def start(self) -> int:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()
        return self.port

    def stop(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        try:
            conn.settimeout(3)
            data = conn.recv(4096)
            if not data:
                return
            body = (
                f"<html><head><title>{self.title}</title></head>"
                f"<body>device</body></html>"
            ).encode()
            resp = (
                b"HTTP/1.1 200 OK\r\n"
                + f"Server: {self.server_header}\r\n".encode()
                + b"Content-Type: text/html\r\n"
                + f"Content-Length: {len(body)}\r\n".encode()
                + b"Connection: close\r\n\r\n"
                + body
            )
            conn.sendall(resp)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

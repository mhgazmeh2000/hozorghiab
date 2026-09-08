"""Neutral adapter interface and result types.

Rule of the project: never fabricate.  Every method that a device cannot
perform raises ``NotSupported`` carrying a human reason, and every value an
adapter returns must have been read from (or derived from evidence about) a
real device.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


class NotSupported(Exception):
    """Raised when the device/adapter does not support an operation."""

    def __init__(self, reason: str, supported: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.supported = supported

    def to_dict(self) -> dict:
        return {"supported": False, "reason": self.reason}


class DeviceConnectionError(Exception):
    """Transport-level failure talking to the device (offline, timeout...)."""


class DeviceProtocolError(Exception):
    """Device answered but with an unexpected/undecodable payload."""


# --------------------------------------------------------------------------
# Domain values
# --------------------------------------------------------------------------


@dataclass
class DeviceInfo:
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    platform: Optional[str] = None
    device_name: Optional[str] = None
    vendor: Optional[str] = None
    device_id: Optional[str] = None
    mac_address: Optional[str] = None
    device_time: Optional[datetime] = None
    user_count: Optional[int] = None
    fingerprint_count: Optional[int] = None
    face_count: Optional[int] = None
    attendance_count: Optional[int] = None
    raw: dict = field(default_factory=dict)
    source: str = "device"


@dataclass
class DeviceUserRecord:
    user_id_on_device: str
    device_user_sn: Optional[int] = None
    employee_code: Optional[str] = None
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    card_number: Optional[str] = None
    password_status: Optional[str] = None
    privilege_level: Optional[int] = None
    role: Optional[str] = None
    department: Optional[str] = None
    group_number: Optional[int] = None
    enabled: bool = True
    verification_mode: Optional[str] = None
    fingerprint_count: Optional[int] = None
    face_enabled: Optional[bool] = None
    card_enabled: Optional[bool] = None
    password_enabled: Optional[bool] = None
    raw: dict = field(default_factory=dict)


@dataclass
class AttendanceRecord:
    user_id_on_device: Optional[str] = None
    user_sn: Optional[int] = None
    event_time: Optional[datetime] = None
    verification_type: Optional[str] = None  # normalized enum value
    event_type: Optional[str] = None
    status: Optional[str] = None
    raw_state: Optional[str] = None
    raw_punch: Optional[str] = None
    work_code: Optional[int] = None
    door_id: Optional[str] = None
    device_event_id: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class AdapterProbeResult:
    """Outcome of a cheap protocol probe (used by discovery)."""

    protocol: str
    detected: bool
    confidence: float = 0.0
    source: str = ""
    evidence: dict = field(default_factory=dict)
    detail: str = ""


# --------------------------------------------------------------------------
# Capability matrix
# --------------------------------------------------------------------------

CAPABILITY_KEYS = [
    "device_info",
    "read_users",
    "read_user",
    "create_users",
    "update_users",
    "delete_users",
    "read_logs",
    "delete_logs",
    "get_log_count",
    "sync_users_to_device",
    "sync_users_from_device",
    "realtime_events",
    "fingerprint",
    "face",
    "card",
    "password",
    "set_time",
    "get_time",
    "clear_data",
    "read_templates",
    "write_templates",
    "read_operational_logs",
]


# --------------------------------------------------------------------------
# Adapter interface
# --------------------------------------------------------------------------


class AttendanceAdapter(ABC):
    """Interface implemented by every brand adapter.

    ``id_``       stable identifier used in the registry (e.g. "zkteco")
    ``display_name`` human readable name
    ``description`` protocol summary
    ``priority``   order used when multiple adapters could handle a device
    """

    id_: str = "base"
    display_name: str = "Base"
    description: str = ""
    priority: int = 100

    def __init__(self, device_cfg: Optional[dict] = None):
        self.device_cfg = device_cfg or {}

    # -- lifecycle -----------------------------------------------------
    @abstractmethod
    async def test_connection(self) -> dict:
        """Return {'ok': bool, 'detail': str, ...} evidence dict."""

    @abstractmethod
    async def connect(self) -> None:
        """Open a working session; raises DeviceConnectionError on failure."""

    async def disconnect(self) -> None:  # noqa: B027
        """Close the session (default no-op)."""

    # -- probes ---------------------------------------------------------
    @classmethod
    @abstractmethod
    async def probe(cls, ip: str, port: int, timeout_s: float) -> AdapterProbeResult:
        """Stateless one-shot probe used by the discovery engine.

        Must not require credentials or device configuration.
        """

    # -- reads ----------------------------------------------------------
    @abstractmethod
    async def get_device_info(self) -> DeviceInfo: ...

    @abstractmethod
    async def get_users(self, **kwargs) -> list[DeviceUserRecord]: ...

    @abstractmethod
    async def get_attendance_logs(self, **kwargs) -> list[AttendanceRecord]: ...

    async def get_user(self, user_id_on_device: str) -> DeviceUserRecord:  # noqa: B027
        raise NotSupported("Adapter does not implement single-user reads")

    async def get_attendance_log_count(self) -> int:  # noqa: B027
        raise NotSupported("Adapter does not expose a log counter")

    # -- writes ---------------------------------------------------------
    async def create_user(self, user: DeviceUserRecord) -> dict:  # noqa: B027
        raise NotSupported("Device does not provide a user creation API")

    async def update_user(self, user: DeviceUserRecord) -> dict:  # noqa: B027
        raise NotSupported("Device does not provide a user update API")

    async def delete_user(self, user_id_on_device: str) -> dict:  # noqa: B027
        raise NotSupported("Device does not provide a user deletion API")

    async def clear_attendance_logs(self) -> dict:  # noqa: B027
        raise NotSupported("Device does not allow clearing attendance logs")

    async def set_time(self, when: datetime) -> dict:  # noqa: B027
        raise NotSupported("Device does not allow setting its clock")

    # -- realtime -------------------------------------------------------
    def supports_realtime(self) -> bool:  # noqa: B027
        return False

    # -- capabilities ----------------------------------------------------
    @abstractmethod
    def declare_capabilities(self) -> dict[str, dict]:
        """Return {capability: {supported: bool, source: str, reason?: str}}.

        ``source`` documents where support was established
        (e.g. "zk-protocol spec", "vendor SDK docs", "verified on device").
        """

    def get_capabilities(self) -> dict:
        caps = self.declare_capabilities()
        out = {}
        for key, val in caps.items():
            out[key] = val.get("supported", False) if isinstance(val, dict) else bool(val)
        return out

    def info_fingerprint(self) -> dict:
        """Optional adapter-level fingerprint: which evidence makes this
        adapter the right one (vendor ids, http patterns, port defaults)."""
        return {}

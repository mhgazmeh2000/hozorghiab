"""Enum definitions used across the schema.

Note about DeviceStatus
-----------------------
The status is *liveness and evidence* oriented. It separates:

* Network reachability (could we open a TCP connection / get a reply?)
* Protocol verification (did the expected protocol actually handshake?)
* Human/operator label (VERIFIED = a human has confirmed this device).

We deliberately avoid fabricating OFFLINE from transient errors in the
execution environment. States:

* UNKNOWN                - never probed, no evidence
* PROBE_UNREACHABLE      - TCP connect failed in *this* environment; may be a
                          firewall/routing issue, not a real device outage.
* OFFLINE_VERIFIED       - protocol previously worked; recent probe failed
                          consistently from the production network.
* ONLINE_PROTOCOL_OPEN   - TCP port(s) reachable but protocol not yet
                          verified (open-port detection only).
* ONLINE_PROTOCOL_VERIFIED - protocol handshake + at least one read op
                             succeeded.
* VERIFIED               - operator explicitly accepted the device as
                           trusted (strongest level; enables write-side).
* DISABLED               - operator has disabled management of this device.
"""
from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover
        return self.value


class DeviceStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    PROBE_UNREACHABLE = "PROBE_UNREACHABLE"
    OFFLINE_VERIFIED = "OFFLINE_VERIFIED"
    ONLINE_PROTOCOL_OPEN = "ONLINE_PROTOCOL_OPEN"
    ONLINE_PROTOCOL_VERIFIED = "ONLINE_PROTOCOL_VERIFIED"
    VERIFIED = "VERIFIED"
    DISABLED = "DISABLED"

    # Back-compat aliases (older code used OFFLINE/ONLINE):
    @classmethod
    def _missing_(cls, value):
        aliases = {
            "OFFLINE": cls.PROBE_UNREACHABLE,
            "ONLINE": cls.ONLINE_PROTOCOL_OPEN,
        }
        return aliases.get(value)


class DetectionState(StrEnum):
    """Evidence state for discovery results (staged: ping -> port -> protocol)."""
    UNKNOWN = "UNKNOWN"               # nothing discovered
    PING_REACHED = "PING_REACHED"     # ICMP ping succeeded
    PORT_OPEN = "PORT_OPEN"           # TCP connect succeeded (no protocol)
    PROTOCOL_CANDIDATE = "PROTOCOL_CANDIDATE"  # port matches known protocol
    PROTOCOL_VERIFIED = "PROTOCOL_VERIFIED"    # handshake + reply confirmed
    DEVICE_VERIFIED = "DEVICE_VERIFIED"        # operator confirmed / full info read

    # Back-compat
    POSSIBLE = "PORT_OPEN"
    DETECTED = "PROTOCOL_CANDIDATE"
    VERIFIED = "PROTOCOL_VERIFIED"


class DiscoveryStage(StrEnum):
    PENDING = "PENDING"
    SCANNING = "SCANNING"
    FINGERPRINTING = "FINGERPRINTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SyncDirection(StrEnum):
    DEVICE_TO_SERVER = "device_to_server"
    SERVER_TO_DEVICE = "server_to_device"
    BIDIRECTIONAL = "bidirectional"


class SyncStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class EventType(StrEnum):
    """Normalized punch direction. We map these ONLY when there is verified
    evidence (e.g. a work-code table or explicit mapping per device).
    Otherwise we keep UNKNOWN and preserve raw_state/raw_punch verbatim."""
    CHECK_IN = "CHECK_IN"
    CHECK_OUT = "CHECK_OUT"
    BREAK_IN = "BREAK_IN"
    BREAK_OUT = "BREAK_OUT"
    OVERTIME_IN = "OVERTIME_IN"
    OVERTIME_OUT = "OVERTIME_OUT"
    UNKNOWN = "UNKNOWN"


class VerificationType(StrEnum):
    PASSWORD = "PASSWORD"
    FINGERPRINT = "FINGERPRINT"
    CARD = "CARD"
    FACE = "FACE"
    PIN = "PIN"
    UNKNOWN = "UNKNOWN"


class UserRole(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class OperationAction(StrEnum):
    LOGIN = "login"
    LOGOUT = "logout"
    SCAN = "scan"
    DISCOVERY = "discovery"
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    SYNC = "sync"
    USER_IMPORT = "user_import"
    USER_EXPORT = "user_export"
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    ATTENDANCE_IMPORT = "attendance_import"
    ATTENDANCE_EXPORT = "attendance_export"
    DEVICE_CONFIG = "device_config"
    NETWORK_CONFIG = "network_config"
    SETTINGS_UPDATE = "settings_update"
    READ = "read"
    DESTRUCTIVE_WRITE = "destructive_write"
    OTHER = "other"


class CredentialKind(StrEnum):
    PASSWORD = "password"
    API_KEY = "api_key"
    TOKEN = "token"
    SNMP_COMMUNITY = "snmp_community"
    COMMUNICATION_KEY = "communication_key"


class CapabilityState(StrEnum):
    """Per-capability tri-state. Critical: never expose an unverified
    destructive operation as active in the UI."""
    IMPLEMENTED = "IMPLEMENTED"   # code exists, per spec
    VERIFIED = "VERIFIED"         # actually tested against a real device
    NOT_VERIFIED = "NOT_VERIFIED" # declared implemented, not yet tested live
    NOT_SUPPORTED = "NOT_SUPPORTED"  # protocol doesn't support this
    DISABLED = "DISABLED"         # operator explicitly disabled


class CredentialVerificationState(StrEnum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    FAILED = "FAILED"

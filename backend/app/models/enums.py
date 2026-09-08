"""Enum definitions used across the schema."""
from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover
        return self.value


class DeviceStatus(StrEnum):
    UNKNOWN = "UNKNOWN"  # never probed / no evidence
    OFFLINE = "OFFLINE"
    ONLINE = "ONLINE"  # reachable, no verified protocol identity
    POSSIBLE = "POSSIBLE"  # partial evidence (e.g. http title only)
    DETECTED = "DETECTED"  # strong fingerprint evidence
    VERIFIED = "VERIFIED"  # protocol handshake/read completed


class DetectionState(StrEnum):
    UNKNOWN = "UNKNOWN"
    POSSIBLE = "POSSIBLE"
    DETECTED = "DETECTED"
    VERIFIED = "VERIFIED"


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
    OTHER = "other"


class CredentialKind(StrEnum):
    PASSWORD = "password"
    API_KEY = "api_key"
    TOKEN = "token"
    SNMP_COMMUNITY = "snmp_community"
    COMMUNICATION_KEY = "communication_key"  # ZK commkey

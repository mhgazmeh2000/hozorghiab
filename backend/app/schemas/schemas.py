"""API request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth -----------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _trim_username(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("password")
    @classmethod
    def _trim_password(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    display_name: Optional[str] = None
    username: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class MeResponse(ORMModel):
    id: str
    username: str
    display_name: Optional[str] = None
    role: str
    must_change_password: bool = False


# --- networks --------------------------------------------------------------

class NetworkCreate(BaseModel):
    cidr: str
    label: Optional[str] = None
    exclude_ips: list[str] = []
    note: Optional[str] = None


class NetworkUpdate(BaseModel):
    cidr: Optional[str] = None
    label: Optional[str] = None
    exclude_ips: Optional[list[str]] = None
    enabled: Optional[bool] = None
    note: Optional[str] = None


class NetworkOut(ORMModel):
    id: str
    cidr: str
    label: Optional[str] = None
    enabled: bool
    is_default: bool
    is_single_ip: bool
    exclude_ips: list[Any]
    last_scan_at: Optional[datetime] = None
    created_at: datetime


# --- devices ---------------------------------------------------------------

class DeviceCredentialIn(BaseModel):
    kind: str = "password"
    username: Optional[str] = None
    secret: str
    note: Optional[str] = None


class DeviceCredentialOut(ORMModel):
    id: str
    kind: str
    username: Optional[str] = None
    secret_masked: Optional[str] = None
    note: Optional[str] = None
    is_active: bool


class DeviceUpdate(BaseModel):
    hostname: Optional[str] = None
    port: Optional[int] = None
    enabled: Optional[bool] = None
    auto_sync_enabled: Optional[bool] = None
    sync_interval_min: Optional[int] = None
    connect_timeout_s: Optional[float] = None
    read_timeout_s: Optional[float] = None
    retry_count: Optional[int] = None
    adapter_name: Optional[str] = None
    note: Optional[str] = None


class DeviceCreate(BaseModel):
    ip_address: str
    network_cidr: Optional[str] = None
    port: Optional[int] = None
    hostname: Optional[str] = None
    adapter_name: Optional[str] = "generic_http"


class DeviceOut(ORMModel):
    id: str
    ip_address: str
    hostname: Optional[str] = None
    mac_address: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    platform: Optional[str] = None
    device_name: Optional[str] = None
    vendor: Optional[str] = None
    status: str
    detection_state: str
    confidence: float
    protocol_name: Optional[str] = None
    adapter_name: Optional[str] = None
    port: Optional[int] = None
    is_attendance_candidate: bool
    is_manual: bool
    last_seen_at: Optional[datetime] = None
    last_online_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_error: Optional[str] = None
    auto_sync_enabled: bool
    sync_interval_min: Optional[int] = None
    verified_at: Optional[datetime] = None
    created_at: datetime


class DeviceDetailOut(DeviceOut):
    detection_evidence: list[Any] = []
    extra_config: dict = {}
    capabilities: list[Any] = []
    protocols: list[Any] = []
    user_count: Optional[int] = None
    attendance_count: Optional[int] = None
    device_time: Optional[datetime] = None


class DeviceUserOut(ORMModel):
    id: str
    device_id: str
    user_id_on_device: str
    device_user_sn: Optional[int] = None
    employee_code: Optional[str] = None
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    card_number: Optional[str] = None
    password_status: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    privilege_level: Optional[int] = None
    group_number: Optional[int] = None
    enabled: bool
    fingerprint_count: Optional[int] = None
    face_enabled: bool
    card_enabled: bool
    password_enabled: bool
    verification_mode: Optional[str] = None
    status: Optional[str] = None
    last_sync_at: Optional[datetime] = None


class DeviceUserCreate(BaseModel):
    user_id_on_device: str
    employee_code: Optional[str] = None
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    card_number: Optional[str] = None
    department: Optional[str] = None
    role: Optional[str] = None
    privilege_level: Optional[int] = 0
    group_number: Optional[int] = 1
    enabled: bool = True
    password: Optional[str] = None


class AttendanceLogOut(ORMModel):
    id: str
    device_id: str
    user_id_on_device: Optional[str] = None
    user_sn: Optional[int] = None
    employee_code: Optional[str] = None
    event_time: datetime
    raw_state: Optional[str] = None
    raw_punch: Optional[str] = None
    event_type: str
    verification_type: str
    status: Optional[str] = None
    work_code: Optional[int] = None
    door_id: Optional[str] = None
    source: str
    created_at: datetime


# --- jobs ------------------------------------------------------------------

class DiscoveryJobOut(ORMModel):
    id: str
    kind: str
    target: str
    requested_by: Optional[str] = None
    status: str
    stage: Optional[str] = None
    progress: float
    total_hosts: int
    scanned_hosts: int
    found_hosts: int
    errors: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    summary: dict = {}
    created_at: datetime


class SyncJobOut(ORMModel):
    id: str
    device_id: str
    direction: str
    scope: str
    requested_by: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    stats: dict = {}
    created_at: datetime


class DiscoveryResultOut(ORMModel):
    id: str
    ip_address: str
    reachable: bool
    open_ports: list[Any]
    hostname: Optional[str] = None
    detection_state: str
    confidence: float
    source: Optional[str] = None
    evidence: dict = {}
    probed_at: datetime


# --- audit / dashboard / settings -----------------------------------------

class AuditLogOut(ORMModel):
    id: str
    created_at: datetime
    username: Optional[str] = None
    action: str
    device_id: Optional[str] = None
    device_ip: Optional[str] = None
    result: str
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    source_ip: Optional[str] = None
    details: dict = {}


class DashboardStats(BaseModel):
    total_devices: int = 0
    online_devices: int = 0
    offline_devices: int = 0
    unknown_devices: int = 0
    probe_unreachable_devices: int = 0
    last_known_online_devices: int = 0
    execution_environment_unreachable: int = 0
    verified_devices: int = 0
    attendance_candidates: int = 0
    total_users: int = 0
    today_attendance: int = 0
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    server_time: Optional[datetime] = None
    failed_operations_24h: int = 0
    networks_count: int = 0
    pending_jobs: int = 0
    storage_alerts: list[dict] = []


class SyncRequest(BaseModel):
    direction: str = "device_to_server"
    scope: str = "full"


class ScanRequest(BaseModel):
    target: Optional[str] = None  # network id / cidr / ip / "all"


class ImportPreview(BaseModel):
    entity: str
    total_rows: int
    valid_rows: int
    issue_rows: int
    duplicate_rows: int
    preview: list[Any]
    issues: list[Any]
    read_errors: list[str] = []


class SettingUpdate(BaseModel):
    value: Any


class SettingOut(ORMModel):
    key: str
    value: Any
    description: Optional[str] = None

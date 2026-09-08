"""Devices, configured networks, capabilities, protocols, credentials, raw data."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPkMixin, utcnow
from app.models.enums import CredentialKind, DetectionState, DeviceStatus


class DeviceNetwork(Base, UUIDPkMixin, TimestampMixin):
    """A user-defined network (CIDR or single IP) eligible for scanning."""

    __tablename__ = "device_networks"

    cidr: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_single_ip: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    exclude_ips: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_scan_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Device(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "devices"

    ip_address: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    network_cidr: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    hostname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mac_address: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    brand: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    platform: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    device_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    vendor: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default=DeviceStatus.UNKNOWN.value, nullable=False, index=True
    )
    detection_state: Mapped[str] = mapped_column(
        String(20), default=DetectionState.UNKNOWN.value, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    detection_evidence: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    protocol_name: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    adapter_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_attendance_candidate: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_online_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_offline_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_probe_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_probe_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_sync_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # device time / storage usage
    device_time_offset_s: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    device_time_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    storage_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    storage_capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    storage_usage_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # operational settings (configurable per device)
    connect_timeout_s: Mapped[float] = mapped_column(Float, default=3.0)
    read_timeout_s: Mapped[float] = mapped_column(Float, default=10.0)
    retry_count: Mapped[int] = mapped_column(Integer, default=2)
    backoff_base_s: Mapped[float] = mapped_column(Float, default=0.5)
    port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sync_interval_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    auto_sync_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    extra_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    raw_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    capabilities: Mapped[list["DeviceCapability"]] = relationship(
        back_populates="device", cascade="all, delete-orphan", lazy="selectin"
    )
    protocols: Mapped[list["DeviceProtocol"]] = relationship(
        back_populates="device", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def display_name(self) -> str:
        return self.hostname or self.device_name or self.model or self.ip_address

    @property
    def capability_map(self) -> dict:
        """Back-compat: True when implemented AND verified AND enabled."""
        return {
            c.capability: (c.implemented and c.verified and c.enabled)
            for c in self.capabilities
        }

    @property
    def capability_states(self) -> dict:
        return {
            c.capability: {
                "implemented": c.implemented,
                "verified": c.verified,
                "enabled": c.enabled,
                "is_destructive": c.is_destructive,
            }
            for c in self.capabilities
        }


class DeviceCapability(Base, UUIDPkMixin, TimestampMixin):
    """Capability matrix entry for a device (evidence-derived).

    State model:
      implemented - code can speak this command per spec
      verified    - we have successfully executed it against the real device
      enabled     - operator allows it to be offered in the UI / scheduled
                    Destructive operations (delete_user, clear_attendance,
                    restart, set_time, ...) are enabled=false by default and
                    require operator acknowledgement + RBAC approval.
    """

    __tablename__ = "device_capabilities"
    __table_args__ = (UniqueConstraint("device_id", "capability", name="uq_device_cap"),)

    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
    implemented: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_destructive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    device: Mapped[Device] = relationship(back_populates="capabilities")


class DeviceProtocol(Base, UUIDPkMixin, TimestampMixin):
    """A service/protocol detected on a device port, with evidence + confidence."""

    __tablename__ = "device_protocols"
    __table_args__ = (
        UniqueConstraint("device_id", "port", "transport", name="uq_device_proto"),
    )

    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    transport: Mapped[str] = mapped_column(String(8), default="tcp", nullable=False)
    service: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    protocol_guess: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    protocol_state: Mapped[str] = mapped_column(
        String(20), default=DetectionState.UNKNOWN.value, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    banner: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    http_headers: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    html_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    device: Mapped[Device] = relationship(back_populates="protocols")


class DeviceCredential(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "device_credentials"

    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30), default=CredentialKind.PASSWORD.value)
    username: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # encrypted blob (Fernet). Never plaintext.
    secret_ciphertext: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    verification_state: Mapped[str] = mapped_column(
        String(20), default="NOT_VERIFIED", nullable=False
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DeviceRawData(Base, UUIDPkMixin, TimestampMixin):
    """Raw evidence payloads for debugging (never secrets)."""

    __tablename__ = "device_raw_data"
    __table_args__ = (Index("ix_raw_device_ts", "device_id", "captured_at"),)

    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(60), nullable=False)  # http/json/zk...
    source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_b64: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # binary
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

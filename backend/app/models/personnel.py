"""Device users, attendance logs, system users, settings, audit log."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin, utcnow


class DeviceUser(Base, UUIDPkMixin, TimestampMixin):
    """A registered user (employee) on an attendance device.

    Schema is intentionally flexible: all brands do not expose identical
    fields, and the raw payload from the device is always retained.
    """

    __tablename__ = "device_users"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "user_id_on_device", name="uq_device_user_uid"
        ),
        Index("ix_device_user_employee", "device_id", "employee_code"),
    )

    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    # user id exactly as stored on the device (string to survive leading zeros)
    user_id_on_device: Mapped[str] = mapped_column(String(64), nullable=False)
    device_user_sn: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    employee_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    card_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    password_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    privilege_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    group_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    fingerprint_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    face_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    card_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    password_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_mode: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    device_user_raw_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AttendanceLog(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "attendance_logs"
    __table_args__ = (
        UniqueConstraint("device_id", "fingerprint", name="uq_attlog_fingerprint"),
        Index("ix_attlog_event_time", "event_time"),
        Index("ix_attlog_device_time", "device_id", "event_time"),
        Index("ix_attlog_employee", "employee_code"),
    )

    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    device_event_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    user_id_on_device: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_sn: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    employee_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("device_users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    raw_state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    raw_punch: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    event_type: Mapped[str] = mapped_column(
        String(30), default="UNKNOWN", nullable=False, index=True
    )
    verification_type: Mapped[str] = mapped_column(
        String(20), default="UNKNOWN", nullable=False
    )
    status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    work_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    door_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    raw_event: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="device_pull", nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SystemUser(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "system_users"

    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SystemSetting(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AuditLog(Base, UUIDPkMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_ts", "created_at"),
        Index("ix_audit_user", "username"),
        Index("ix_audit_action_device", "action", "device_id"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    device_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    result: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class AuditLogMixin:
    """Alias so `from app.models import AuditLog` works everywhere."""

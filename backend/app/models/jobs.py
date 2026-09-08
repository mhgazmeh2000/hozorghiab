"""Background jobs: discovery runs, sync jobs and per-host discovery results."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPkMixin, utcnow
from app.models.enums import JobStatus


class DiscoveryJob(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "discovery_jobs"
    __table_args__ = (Index("ix_discjob_ts", "started_at"),)

    kind: Mapped[str] = mapped_column(String(20), default="scan", nullable=False)
    # "network:<cidr>" | "ip:<addr>" | "all"
    target: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    requested_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=JobStatus.PENDING.value, nullable=False, index=True
    )
    stage: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    total_hosts: Mapped[int] = mapped_column(Integer, default=0)
    scanned_hosts: Mapped[int] = mapped_column(Integer, default=0)
    found_hosts: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    cancel_requested: Mapped[bool] = mapped_column(default=False)


class DiscoveryResult(Base, UUIDPkMixin, TimestampMixin):
    """Evidence record for one host discovered during a run."""

    __tablename__ = "discovery_results"
    __table_args__ = (
        Index("ix_discres_job_host", "discovery_job_id", "ip_address"),
        Index("ix_discres_ts", "probed_at"),
    )

    discovery_job_id: Mapped[str] = mapped_column(
        ForeignKey("discovery_jobs.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    reachable: Mapped[bool] = mapped_column(default=False)
    open_ports: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    icmp_reachable: Mapped[Optional[bool]] = mapped_column(default=None, nullable=True)
    hostname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mac_address: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    http_headers: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    html_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    banners: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    detection_state: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    probed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SyncJob(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "sync_jobs"
    __table_args__ = (Index("ix_syncjob_ts", "started_at"),)

    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    scope: Mapped[str] = mapped_column(String(30), default="full")  # users/logs/full
    requested_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=JobStatus.PENDING.value, nullable=False, index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stats: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

"""Base for vendor adapters whose wire protocols are not yet verified.

These adapters exist so the architecture has a home for every brand the
discovery engine might meet, but - per the project rule *never guess* - they
refuse to claim support for anything that has not been confirmed against a
real device or authoritative documentation.  Their declared capabilities are
all ``supported: false`` until the protocol research for the brand is done and
an implementation lands (see PROTOCOLS.md / ADAPTERS.md).
"""
from __future__ import annotations

from typing import Optional

from app.adapters.base import (
    AdapterProbeResult,
    AttendanceAdapter,
    DeviceInfo,
    NotSupported,
)
from app.adapters.generic_http import GenericHttpAdapter


class UnverifiedVendorAdapter(AttendanceAdapter):
    """Placeholder: vendor detected but protocol not yet implemented."""

    id_ = "vendor"
    display_name = "Vendor"
    description = ""
    priority = 150
    research_status = "unknown"  # overridden per vendor

    def __init__(self, device_cfg: Optional[dict] = None):
        super().__init__(device_cfg)

    @classmethod
    async def probe(cls, ip: str, port: int, timeout_s: float) -> AdapterProbeResult:
        # No probe can exist before a protocol is known: report honestly.
        return AdapterProbeResult(
            protocol=f"{cls.id_}_unknown",
            detected=False,
            confidence=0.0,
            source="adapter registry",
            detail=f"no verified {cls.id_} probe (research status: {cls.research_status})",
        )

    async def test_connection(self) -> dict:
        return {
            "ok": False,
            "detail": (
                f"No verified protocol implementation for {self.id_}; "
                f"research status: {self.research_status}"
            ),
        }

    async def connect(self) -> None:
        raise NotSupported(
            f"{self.id_} adapter has no verified connect procedure "
            f"(research status: {self.research_status})"
        )

    async def get_device_info(self) -> DeviceInfo:
        raise NotSupported(
            f"no verified {self.id_} protocol for reading device info "
            f"(research status: {self.research_status})"
        )

    async def get_users(self, **kwargs):
        raise NotSupported(
            f"no verified {self.id_} protocol for reading users "
            f"(research status: {self.research_status})"
        )

    async def get_attendance_logs(self, **kwargs):
        raise NotSupported(
            f"no verified {self.id_} protocol for reading logs "
            f"(research status: {self.research_status})"
        )

    def declare_capabilities(self) -> dict[str, dict]:
        reason = (
            f"Protocol implementation not verified (research status: "
            f"{self.research_status}). No capability is claimed without evidence."
        )
        return {
            "device_info": {"supported": False, "reason": reason},
            "read_users": {"supported": False, "reason": reason},
            "read_user": {"supported": False, "reason": reason},
            "create_users": {"supported": False, "reason": reason},
            "update_users": {"supported": False, "reason": reason},
            "delete_users": {"supported": False, "reason": reason},
            "read_logs": {"supported": False, "reason": reason},
            "delete_logs": {"supported": False, "reason": reason},
            "get_log_count": {"supported": False, "reason": reason},
            "sync_users_to_device": {"supported": False, "reason": reason},
            "sync_users_from_device": {"supported": False, "reason": reason},
            "realtime_events": {"supported": False, "reason": reason},
            "fingerprint": {"supported": False, "reason": reason},
            "face": {"supported": False, "reason": reason},
            "card": {"supported": False, "reason": reason},
            "password": {"supported": False, "reason": reason},
            "set_time": {"supported": False, "reason": reason},
            "get_time": {"supported": False, "reason": reason},
            "clear_data": {"supported": False, "reason": reason},
            "read_templates": {"supported": False, "reason": reason},
            "write_templates": {"supported": False, "reason": reason},
            "read_operational_logs": {"supported": False, "reason": reason},
        }


class UnverifiedHttpVendorAdapter(GenericHttpAdapter):
    """Like the generic HTTP adapter, but tied to a vendor id so it can be
    swapped for a real protocol implementation later without core changes.

    Until then it only collects HTTP evidence (its parent behaviour) and
    never claims attendance capabilities.
    """

    id_ = "vendor_http"
    display_name = "Vendor (HTTP evidence)"
    priority = 180
    research_status = "unknown"

    def declare_capabilities(self) -> dict[str, dict]:
        # parents declares read_users/read_logs as false already; keep device_info
        return super().declare_capabilities()

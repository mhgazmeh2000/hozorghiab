"""Dahua attendance devices.

Research status: no verified protocol/documentation available in this
environment; no capability is claimed.
"""
from app.adapters.vendor_base import UnverifiedHttpVendorAdapter


class DahuaAttendanceAdapter(UnverifiedHttpVendorAdapter):
    id_ = "dahua_attendance"
    display_name = "Dahua (attendance)"
    description = "Dahua attendance devices. Protocol pending verification."
    research_status = "unknown - needs device or official Dahua documentation"
    priority = 120

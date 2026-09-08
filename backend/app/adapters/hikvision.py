"""Hikvision attendance terminals (e.g. DS-K1T series).

Research status: Hikvision terminals expose an ISAPI (HTTP) interface, but
exact attendance endpoints/format require verification against a real device
or official ISAPI documentation; no capability is claimed until then.
"""
from app.adapters.vendor_base import UnverifiedHttpVendorAdapter


class HikvisionAdapter(UnverifiedHttpVendorAdapter):
    id_ = "hikvision"
    display_name = "Hikvision (attendance)"
    description = "Hikvision ISAPI terminals. Endpoints pending verification."
    research_status = "unknown - needs device or official ISAPI attendance docs"
    priority = 120

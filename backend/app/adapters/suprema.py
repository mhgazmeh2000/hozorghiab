"""Suprema attendance/admission devices.

Research status: Suprema exposes an official SDK (BioStar / BS2) and its
newer devices provide a documented REST-style HTTP API, but no device or
authoritative protocol document was available in this environment, so no
capability is claimed here.  See ADAPTERS.md for what must be validated
before this adapter becomes operational.
"""
from app.adapters.vendor_base import UnverifiedHttpVendorAdapter


class SupremaAdapter(UnverifiedHttpVendorAdapter):
    id_ = "suprema"
    display_name = "Suprema"
    description = (
        "Suprema devices (BioStar platform). Protocol details pending "
        "verification against real hardware/docs."
    )
    research_status = "unknown - needs device or official BioStar protocol documentation"
    priority = 120

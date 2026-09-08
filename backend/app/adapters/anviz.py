"""Anviz attendance devices.

Research status: Anviz documents a proprietary TCP/RS485 protocol and
provides a cross-checksum SDK, but no device/documentation was available here.
No capability is claimed until the protocol is verified against hardware.
"""
from app.adapters.vendor_base import UnverifiedHttpVendorAdapter


class AnvizAdapter(UnverifiedHttpVendorAdapter):
    id_ = "anviz"
    display_name = "Anviz"
    description = "Anviz devices. Protocol pending verification."
    research_status = "unknown - needs device or official Anviz protocol doc"
    priority = 120

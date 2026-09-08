"""Virdi biometric terminals.

Research status: Virdi publishes a communication protocol for its terminals,
but no device/documentation was available here, so no capability is claimed.
"""
from app.adapters.vendor_base import UnverifiedHttpVendorAdapter


class VirdiAdapter(UnverifiedHttpVendorAdapter):
    id_ = "virdi"
    display_name = "Virdi"
    description = "Virdi terminals. Protocol pending verification."
    research_status = "unknown - needs device or official Virdi protocol doc"
    priority = 120

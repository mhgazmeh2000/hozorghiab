"""Nitgen Fingkey devices.

Research status: Nitgen provides Windows SDKs; the wire protocol used by
their attendance terminals was not verifiable in this environment.
"""
from app.adapters.vendor_base import UnverifiedHttpVendorAdapter


class NitgenAdapter(UnverifiedHttpVendorAdapter):
    id_ = "nitgen"
    display_name = "Nitgen"
    description = "Nitgen Fingkey devices. Protocol pending verification."
    research_status = "unknown - needs device or official Nitgen documentation"
    priority = 120

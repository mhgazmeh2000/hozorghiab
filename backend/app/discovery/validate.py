"""Validation of scan targets.

Only IP literals are accepted (never hostnames/URLs) and only addresses
belonging to a user-configured network, or explicitly whitelisted manual
IPs, may be scanned.  Adapters only ever talk to addresses previously
registered in the devices table.
"""
from __future__ import annotations

import ipaddress
from typing import Optional

from pydantic import ValidationError


def validate_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise ValueError(f"'{value}' is not a valid IP address") from exc


def validate_cidr(value: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    value = value.strip()
    try:
        if "/" in value:
            net = ipaddress.ip_network(value, strict=False)
        else:
            ip = ipaddress.ip_address(value)
            net = ipaddress.ip_network(f"{ip}/32", strict=False)
        if net.prefixlen < 16 and net.version == 4:
            raise ValueError(
                "refusing networks wider than /16 (configured ranges only)"
            )
        return net
    except ValueError as exc:
        raise ValueError(f"'{value}' is not a valid CIDR or IP") from exc


def network_hosts(cidr: str) -> list[str]:
    """Expand a CIDR to host addresses (IPv4 and IPv6 safe)."""
    net = validate_cidr(cidr)
    hosts = [str(h) for h in net.hosts()]
    if net.version == 4 and net.num_addresses > 2 ** 22:
        raise ValueError("network too large to scan (max /10-ish)")
    return hosts


def ip_in_any(ip: str, cidrs: list[str]) -> bool:
    addr = validate_ip(ip)
    for cidr in cidrs:
        net = validate_cidr(cidr)
        if addr.version == net.version and addr in net:
            return True
    return False


def is_private_global(ip: str) -> bool:
    addr = validate_ip(ip)
    return addr.is_private or addr.is_link_local or addr.is_loopback


def validate_target(target: str) -> str:
    """Accept either a CIDR or a single IP; return canonical form."""
    try:
        net = validate_cidr(target)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    if net.num_addresses == 1:
        return str(net.network_address)
    return str(net)

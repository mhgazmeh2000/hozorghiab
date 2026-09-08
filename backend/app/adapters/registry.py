"""Adapter registry.

Adding a new brand = registering a class here (or anywhere importing this
module).  The core never hard-codes a vendor.
"""
from __future__ import annotations

from typing import Optional, Type

from app.adapters.base import AttendanceAdapter
from app.adapters.zkteco import ZKTecoAdapter

# Generic adapters
from app.adapters.generic_http import GenericHttpAdapter
from app.adapters.generic_snmp import GenericSnmpAdapter

# Vendor placeholders (protocols pending verification)
from app.adapters.suprema import SupremaAdapter
from app.adapters.anviz import AnvizAdapter
from app.adapters.virdi import VirdiAdapter
from app.adapters.nitgen import NitgenAdapter
from app.adapters.hikvision import HikvisionAdapter
from app.adapters.dahua import DahuaAttendanceAdapter

_REGISTRY: dict[str, Type[AttendanceAdapter]] = {}


def register(cls: Type[AttendanceAdapter]) -> Type[AttendanceAdapter]:
    _REGISTRY[cls.id_] = cls
    return cls


def _register_all():
    for cls in (
        ZKTecoAdapter,
        GenericHttpAdapter,
        GenericSnmpAdapter,
        SupremaAdapter,
        AnvizAdapter,
        VirdiAdapter,
        NitgenAdapter,
        HikvisionAdapter,
        DahuaAttendanceAdapter,
    ):
        register(cls)


_register_all()


def adapter_classes() -> dict[str, Type[AttendanceAdapter]]:
    return dict(_REGISTRY)


def get_adapter_class(adapter_id: str) -> Optional[Type[AttendanceAdapter]]:
    return _REGISTRY.get(adapter_id)


def instantiate(adapter_id: str, device_cfg: Optional[dict] = None) -> AttendanceAdapter:
    cls = get_adapter_class(adapter_id)
    if cls is None:
        raise ValueError(f"unknown adapter id: {adapter_id}")
    return cls(device_cfg or {})


def candidate_adapters_for_evidence(evidence: dict) -> list[Type[AttendanceAdapter]]:
    """Ordered candidates for a host based on collected evidence.

    Evidence keys used: ``open_ports`` (list of ints), ``protocols`` (list of
    detected protocol names), ``http_title``, ``http_headers``.
    """
    ports = set(evidence.get("open_ports") or [])
    protocols = set(evidence.get("protocols") or [])
    candidates: list[Type[AttendanceAdapter]] = []
    if 4370 in ports or "zk_tcp" in protocols:
        candidates.append(ZKTecoAdapter)
    has_http = bool(ports & {80, 443, 8080, 8000, 8081, 8443}) or "http" in protocols
    has_snmp = 161 in ports or "snmp" in protocols
    if has_http:
        candidates.append(GenericHttpAdapter)
    if has_snmp:
        candidates.append(GenericSnmpAdapter)
    if not candidates:
        candidates = [GenericHttpAdapter, GenericSnmpAdapter]
    candidates.sort(key=lambda c: c.priority)
    return candidates

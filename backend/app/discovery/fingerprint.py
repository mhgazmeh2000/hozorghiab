"""Stage 4: fingerprinting / state assignment.

Honesty rules:
- ``VERIFIED`` requires a successful *protocol* interaction with the device
  (today: the ZK CMD_CONNECT handshake, because that is the only attendance
  protocol implemented against authoritative documentation in this build).
- ``DETECTED`` requires strong but non-protocol evidence (e.g. confirmed
  open attendance port).
- ``POSSIBLE`` = partial evidence (an HTTP service, banners...).
- ``UNKNOWN`` = reachable, nothing conclusive.
- Everything else stays in those buckets - never invented.

The knowledge base of *attendance-vendor fingerprint strings* is deliberately
empty until each string can be verified against a real device (see
ADAPTERS.md).  This prevents the system from "recognising" vendors it cannot
actually prove.
"""
from __future__ import annotations

from app.models.enums import DetectionState


def fingerprint_open_port_state(open_ports: list[int]) -> dict:
    """Assign detection state purely from open-port evidence."""
    attendance_ports = {4370, 5005, 5007, 5010, 6000, 6001, 1434}
    hit = attendance_ports & set(open_ports)
    if hit:
        ports = sorted(hit)
        # Attendance TCP ports are strong evidence, but only a handshake
        # upgrades to VERIFIED/DETECTED protocol identity.
        return {
            "state": DetectionState.POSSIBLE.value,
            "confidence": 0.5,
            "source": f"open attendance port(s) {ports}",
            "candidate": True,
            "attendance_ports": ports,
        }
    return {
        "state": DetectionState.UNKNOWN.value,
        "confidence": 0.0,
        "source": "no attendance port evidence",
        "candidate": False,
        "attendance_ports": [],
    }


def fingerprint_evidence(evidence: dict) -> dict:
    """Combine all evidence into a detection verdict.

    ``evidence``:
        open_ports: [int]
        services:   {port: probe_result dict}
        zk:         {verified: bool, confidence, evidence}
        http:       list of {title, server, headers}
    """
    open_ports = evidence.get("open_ports") or []
    verdict = fingerprint_open_port_state(open_ports)
    state = verdict["state"]
    confidence = verdict["confidence"]
    sources: list[str] = []
    candidate = verdict["candidate"]
    attendance_ports = verdict["attendance_ports"]

    zk = evidence.get("zk")
    if zk and zk.get("verified"):
        # ZK handshake succeeded: protocol identity is established.
        state = DetectionState.DETECTED.value
        confidence = max(confidence, 0.95)
        sources.append("ZK CMD_CONNECT handshake (protocol verified)")
        candidate = True
        if zk.get("attendance_ports"):
            attendance_ports = zk["attendance_ports"]

    http = evidence.get("http") or []
    for h in http:
        if h.get("status_code") == 200:
            sources.append(
                f"HTTP {h.get('scheme','').upper()} {h.get('port')} "
                f"server={h.get('server') or '-'} title={h.get('title') or '-'}"
            )
            if state == DetectionState.UNKNOWN.value:
                state = DetectionState.POSSIBLE.value
                confidence = max(confidence, 0.4)

    if evidence.get("snmp"):
        sources.append("SNMP system query answered")

    return {
        "state": state,
        "confidence": round(confidence, 3),
        "source": "; ".join(sources) if sources else verdict["source"],
        "candidate": candidate,
        "attendance_ports": sorted(set(attendance_ports)),
        "adapter_candidates": evidence.get("adapter_candidates", []),
    }


def http_vendor_hint(title: Optional[str], server: Optional[str]) -> dict:
    """Best-effort vendor hint from HTTP evidence.

    Returns empty dict unless a pattern is *known*.  Currently no pattern has
    been verified against real attendance hardware, so this stays empty.
    """
    return {}

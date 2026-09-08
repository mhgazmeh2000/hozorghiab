"""Stage 4: fingerprinting / state assignment.

Stages (honest, never fabricated):

- UNKNOWN            - no evidence
- PING_REACHED       - ICMP answered, no TCP
- PORT_OPEN          - TCP connect succeeded, protocol unknown
- PROTOCOL_CANDIDATE - open port matches known attendance protocol (e.g. 4370)
- PROTOCOL_VERIFIED  - protocol handshake succeeded
- DEVICE_VERIFIED    - full device info read / operator acceptance

Task 24: Do not infer vendor from a port. TCP 4370 open -> ZK candidate;
successful ZK protocol communication -> ZK PROTOCOL_VERIFIED; vendor may
still be UNKNOWN.
"""
from __future__ import annotations

from typing import Optional

from app.models.enums import DetectionState


def fingerprint_open_port_state(open_ports: list[int]) -> dict:
    """Assign detection state purely from open-port evidence."""
    attendance_ports = {4370, 5005, 5007, 5010, 6000, 6001, 1434}
    hit = attendance_ports & set(open_ports)
    if hit:
        ports = sorted(hit)
        return {
            "state": DetectionState.PROTOCOL_CANDIDATE.value,
            "confidence": 0.5,
            "source": f"open attendance port(s) {ports} - protocol not yet verified",
            "candidate": True,
            "attendance_ports": ports,
        }
    if open_ports:
        return {
            "state": DetectionState.PORT_OPEN.value,
            "confidence": 0.2,
            "source": f"open ports {sorted(open_ports)} but none match known attendance protocols",
            "candidate": False,
            "attendance_ports": [],
        }
    return {
        "state": DetectionState.UNKNOWN.value,
        "confidence": 0.0,
        "source": "no open ports / no evidence",
        "candidate": False,
        "attendance_ports": [],
    }


def fingerprint_evidence(evidence: dict) -> dict:
    """Combine all evidence into a detection verdict."""
    open_ports = evidence.get("open_ports") or []
    verdict = fingerprint_open_port_state(open_ports)
    state = verdict["state"]
    confidence = verdict["confidence"]
    sources: list[str] = []
    candidate = verdict["candidate"]
    attendance_ports = verdict["attendance_ports"]

    # ICMP
    if evidence.get("icmp_reachable"):
        sources.append("ICMP ping replied")
        if state == DetectionState.UNKNOWN.value:
            state = DetectionState.PING_REACHED.value
            confidence = max(confidence, 0.1)

    zk = evidence.get("zk")
    if zk and zk.get("verified"):
        state = DetectionState.PROTOCOL_VERIFIED.value
        confidence = max(confidence, 0.95)
        sources.append("ZK CMD_CONNECT handshake (protocol verified on port 4370)")
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
                state = DetectionState.PORT_OPEN.value
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


# Back-compat: older code/tests may reference POSSIBLE/DETECTED/VERIFIED as
# verdicts. Map them to the new states.
def _back_compat_state(state: str) -> str:
    return {
        "POSSIBLE": DetectionState.PORT_OPEN.value,
        "DETECTED": DetectionState.PROTOCOL_CANDIDATE.value,
        "VERIFIED": DetectionState.PROTOCOL_VERIFIED.value,
    }.get(state, state)


def http_vendor_hint(title: Optional[str], server: Optional[str]) -> dict:
    """Best-effort vendor hint from HTTP evidence.

    Returns empty dict unless a pattern is *known*. Currently no pattern has
    been verified against real attendance hardware, so this stays empty.
    """
    return {}

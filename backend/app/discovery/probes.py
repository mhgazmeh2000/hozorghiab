"""Stage 3: per-service probing of open ports."""
from __future__ import annotations

import asyncio
import re

import httpx

from app.adapters.base import AdapterProbeResult

USER_AGENT = "FreebuffAttendance/0.1"
HTTP_PORTS = {80, 443, 8080, 8000, 8081, 8443, 8888, 7001}


async def probe_banner(ip: str, port: int, timeout_s: float) -> dict:
    """Generic banner read (few hundred ms, best effort)."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=timeout_s
        )
        try:
            data = await asyncio.wait_for(reader.read(256), timeout=0.8)
        except (asyncio.TimeoutError, ConnectionError, OSError):
            data = b""
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        return {
            "port": port,
            "banner": data[:512].decode("latin-1", "replace"),
            "banner_hex": data[:512].hex(),
        }
    except (OSError, asyncio.TimeoutError, ConnectionError):
        return {"port": port, "banner": "", "banner_hex": ""}


async def probe_http(ip: str, port: int, timeout_s: float) -> dict:
    """HTTP/HTTPS GET with header + title extraction."""
    schemes = ("https", "http") if port in (443, 8443) else ("http", "https")
    for scheme in schemes:
        try:
            async with httpx.AsyncClient(
                timeout=timeout_s,
                verify=False,
                follow_redirects=False,
                headers={"User-Agent": USER_AGENT},
                trust_env=False,
            ) as client:
                resp = await client.get(f"{scheme}://{ip}:{port}/")
                headers = {k.lower(): v for k, v in resp.headers.items()}
                title = None
                m = re.search(
                    r"<title[^>]*>(.*?)</title>", resp.text, re.I | re.S
                )
                if m:
                    title = re.sub(r"\s+", " ", m.group(1)).strip()[:200]
                return {
                    "port": port,
                    "scheme": scheme,
                    "http": True,
                    "status_code": resp.status_code,
                    "headers": headers,
                    "server": headers.get("server"),
                    "title": title,
                    "body_snippet": resp.text[:4000],
                    "probe": f"HTTP GET {resp.status_code}",
                }
        except (httpx.HTTPError, OSError, asyncio.TimeoutError, Exception):  # noqa: BLE001
            continue
    return {"port": port, "http": False}


async def probe_zk(ip: str, port: int, timeout_s: float) -> dict:
    """Full ZK handshake probe through the real adapter."""
    from app.adapters.zkteco import ZKTecoAdapter

    result: AdapterProbeResult = await ZKTecoAdapter.probe(ip, port, timeout_s)
    out = {
        "port": port,
        "zk_tcp": result.detected,
        "protocol": "zk_tcp" if result.detected else None,
        "confidence": result.confidence,
        "source": result.source,
        "detail": result.detail,
        "evidence": result.evidence,
    }
    return out


async def probe_snmp(ip: str, port: int, timeout_s: float) -> dict:
    from app.adapters.generic_snmp import GenericSnmpAdapter

    result: AdapterProbeResult = await GenericSnmpAdapter.probe(ip, port, timeout_s)
    return {
        "port": port,
        "snmp": result.detected,
        "protocol": "snmp" if result.detected else None,
        "confidence": result.confidence,
        "source": result.source,
        "detail": result.detail,
        "evidence": result.evidence,
    }


async def probe_service(
    ip: str, port: int, timeout_s: float, zk_probe: bool = False
) -> dict:
    """Pick the right probe strategy for an open port.

    HTTP is attempted on every configured port first (operators may add
    custom ports hosting HTTP), then falls back to a banner read.
    """
    if port == 4370 or zk_probe:
        return await probe_zk(ip, port, timeout_s)
    if port == 161:
        return await probe_snmp(ip, port, timeout_s)
    if port in HTTP_PORTS:
        return await probe_http(ip, port, timeout_s)
    # custom ports: try HTTP, else generic banner
    result = await probe_http(ip, port, timeout_s)
    if result.get("http"):
        return result
    return await probe_banner(ip, port, timeout_s)

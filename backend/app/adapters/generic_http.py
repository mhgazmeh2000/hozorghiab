"""Generic HTTP(S) adapter.

Used when an unknown device exposes an HTTP service.  It collects *evidence*
(headers, title, server banner, HTML markers) and stores it as raw data.  It
never fabricates users, logs or brand claims: unless a higher-confidence
fingerprint rule matches, read operations raise NotSupported with a clear
reason.
"""
from __future__ import annotations

from typing import Optional

import httpx

from app.adapters.base import (
    AdapterProbeResult,
    AttendanceAdapter,
    AttendanceRecord,
    DeviceInfo,
    DeviceUserRecord,
    NotSupported,
)

USER_AGENT = "FreebuffAttendance/0.1"


class GenericHttpAdapter(AttendanceAdapter):
    id_ = "generic_http"
    display_name = "Generic HTTP"
    description = "Evidence-collection adapter for devices with an HTTP/HTTPS service."
    priority = 200

    def __init__(self, device_cfg: Optional[dict] = None):
        super().__init__(device_cfg)
        cfg = device_cfg or {}
        self.host = cfg.get("ip_address", "")
        self.port = int(cfg.get("port") or 80)
        self.scheme = cfg.get("http_scheme") or (
            "https" if self.port in (443, 8443) else "http"
        )
        self.base_url = f"{self.scheme}://{self.host}:{self.port}"

    @classmethod
    async def probe(cls, ip: str, port: int, timeout_s: float) -> AdapterProbeResult:
        for scheme in ("http", "https") if port not in (443, 8443) else ("https", "http"):
            url = f"{scheme}://{ip}:{port}/"
            try:
                async with httpx.AsyncClient(
                    timeout=timeout_s,
                    verify=False,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    resp = await client.get(
                        url, headers={"User-Agent": USER_AGENT}
                    )
                    headers = {
                        k.lower(): v for k, v in resp.headers.items()
                    }
                    title = _extract_title(resp.text)
                    return AdapterProbeResult(
                        protocol="http",
                        detected=True,
                        confidence=0.6,
                        source=f"HTTP GET {scheme.upper()} {resp.status_code}",
                        evidence={
                            "scheme": scheme,
                            "status_code": resp.status_code,
                            "server": headers.get("server"),
                            "title": title,
                            "content_type": headers.get("content-type"),
                            "headers": {k: headers[k] for k in list(headers)[:25]},
                        },
                        detail=f"{scheme.upper()} {resp.status_code} server={headers.get('server')}",
                    )
            except Exception:  # noqa: BLE001 - try next scheme
                continue
        return AdapterProbeResult(
            protocol="http", detected=False, confidence=0.0,
            source="HTTP GET", detail="no HTTP response",
        )

    async def _get(self, path: str = "/") -> httpx.Response:
        async with httpx.AsyncClient(
            timeout=float(self.device_cfg.get("read_timeout_s", 5.0)),
            verify=False,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            return await client.get(
                f"{self.base_url}{path}", headers={"User-Agent": USER_AGENT}
            )

    async def test_connection(self) -> dict:
        try:
            resp = await self._get("/")
            return {
                "ok": True,
                "detail": f"HTTP {resp.status_code}",
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
            }
        except Exception as exc:  # noqa: BLE001
            detail = str(exc).strip() or exc.__class__.__name__
            return {"ok": False, "detail": detail[:500]}

    async def connect(self) -> None:
        # stateless adapter: connectivity is verified by test_connection()
        await self.test_connection()

    async def get_device_info(self) -> DeviceInfo:
        resp = await self._get("/")
        headers = {k.lower(): v for k, v in resp.headers.items()}
        title = _extract_title(resp.text)
        info = DeviceInfo(
            firmware_version=headers.get("server"),
            raw={
                "status_code": resp.status_code,
                "headers": headers,
                "title": title,
                "body_snippet": resp.text[:2000],
            },
            source="http_evidence",
        )
        # Only attribute values the HTTP layer actually proves:
        if "server" in headers:
            info.raw["server"] = headers["server"]
        return info

    async def get_users(self, **kwargs) -> list[DeviceUserRecord]:
        raise NotSupported(
            "No verified HTTP API for reading users on this device"
        )

    async def get_attendance_logs(self, **kwargs) -> list[AttendanceRecord]:
        raise NotSupported(
            "No verified HTTP API for reading attendance logs on this device"
        )

    def declare_capabilities(self) -> dict[str, dict]:
        return {
            "device_info": {
                "supported": True,
                "source": "http evidence (headers/title)",
            },
            "read_users": {
                "supported": False,
                "reason": (
                    "No verified HTTP API for this device; refusing to guess "
                    "an endpoint format"
                ),
            },
            "read_logs": {
                "supported": False,
                "reason": "No verified HTTP attendance API",
            },
            "create_users": {"supported": False, "reason": "No verified HTTP user API"},
            "update_users": {"supported": False, "reason": "No verified HTTP user API"},
            "delete_users": {"supported": False, "reason": "No verified HTTP user API"},
            "delete_logs": {"supported": False, "reason": "No verified HTTP API"},
            "get_log_count": {"supported": False, "reason": "No verified HTTP API"},
            "sync_users_to_device": {"supported": False, "reason": "No verified HTTP user API"},
            "sync_users_from_device": {"supported": False, "reason": "No verified HTTP user API"},
            "realtime_events": {"supported": False, "reason": "Polling only"},
            "fingerprint": {"supported": False, "source": "unknown"},
            "face": {"supported": False, "source": "unknown"},
            "card": {"supported": False, "source": "unknown"},
            "password": {"supported": False, "source": "unknown"},
            "set_time": {"supported": False, "reason": "No verified HTTP API"},
            "get_time": {"supported": False, "reason": "No verified HTTP API"},
            "clear_data": {"supported": False, "reason": "No verified HTTP API"},
            "read_templates": {"supported": False, "reason": "N/A over HTTP"},
            "write_templates": {"supported": False, "reason": "N/A over HTTP"},
            "read_operational_logs": {"supported": False, "reason": "No verified HTTP API"},
        }


def _extract_title(html: str) -> Optional[str]:
    import re

    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip()[:200] or None

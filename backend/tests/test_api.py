"""REST API integration tests (auth, RBAC, CRUD, import/export)."""
from __future__ import annotations

import io
import json

import pytest

from app.core.security import hash_password, verify_password
from app.database import get_session_factory
from app.models import DeviceNetwork, SystemUser
from app.services import seeder
from sqlalchemy import select


async def test_seeder_refreshes_stale_bootstrap_password():
    async with get_session_factory()() as db:
        row = await db.scalar(select(SystemUser).where(SystemUser.username == "admin"))
        assert row is not None
        row.password_hash = hash_password("stale-password")
        await db.commit()

        await seeder.run_seeder(db)
        row = await db.scalar(select(SystemUser).where(SystemUser.username == "admin"))
        assert row is not None
        assert verify_password("Admin-Test-1234!", row.password_hash)


async def test_seeder_adds_missing_default_networks_without_duplicates():
    async with get_session_factory()() as db:
        await seeder.run_seeder(db)
        rows = (await db.scalars(select(DeviceNetwork))).all()
        cidrs = {row.cidr for row in rows}

        assert cidrs == set(seeder.DEFAULT_NETWORK_SEED)
        assert len(rows) == len(cidrs)


async def test_login_bad_password(app_client):
    resp = await app_client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert resp.status_code == 401


async def test_health(app_client):
    resp = await app_client.get("/health")
    assert resp.status_code == 200


async def test_me(auth_headers, app_client):
    resp = await app_client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"
    assert resp.json()["role"] == "admin"


async def test_dashboard_stats(auth_headers, app_client):
    resp = await app_client.get("/api/dashboard/stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_devices" in data
    assert data["networks_count"] >= 10  # default seeds present


async def test_rbac_viewer_cannot_modify(auth_headers, viewer_token, app_client):
    headers = {"Authorization": f"Bearer {viewer_token}"}
    resp = await app_client.post(
        "/api/networks", json={"cidr": "10.90.0.0/24"}, headers=headers
    )
    assert resp.status_code == 403


async def test_network_crud(auth_headers, app_client):
    headers = auth_headers
    r = await app_client.post(
        "/api/networks",
        json={"cidr": "10.90.0.0/24", "label": "test-net", "exclude_ips": ["10.90.0.5"]},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    net_id = r.json()["id"]
    # duplicate -> 400
    r = await app_client.post("/api/networks", json={"cidr": "10.90.0.0/24"}, headers=headers)
    assert r.status_code == 400
    # invalid cidr -> 400
    r = await app_client.post("/api/networks", json={"cidr": "0.0.0.0/0"}, headers=headers)
    assert r.status_code == 400
    # update exclude list
    r = await app_client.put(
        f"/api/networks/{net_id}",
        json={"exclude_ips": ["10.90.0.6"], "enabled": False},
        headers=headers,
    )
    assert r.status_code == 200
    assert "10.90.0.6" in r.json()["exclude_ips"]
    r = await app_client.delete(f"/api/networks/{net_id}", headers=headers)
    assert r.status_code == 200


async def test_device_crud_and_credentials(auth_headers, app_client):
    headers = auth_headers
    r = await app_client.post(
        "/api/devices",
        json={"ip_address": "10.90.0.55", "adapter_name": "zkteco"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    dev_id = r.json()["id"]
    r = await app_client.get(f"/api/devices/{dev_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["capabilities"] == []  # nothing invented pre-connection
    # duplicate IP -> 409
    r = await app_client.post(
        "/api/devices", json={"ip_address": "10.90.0.55"}, headers=headers
    )
    assert r.status_code == 409
    # credentials
    r = await app_client.post(
        f"/api/devices/{dev_id}/credentials",
        json={"kind": "communication_key", "secret": "super-secret-zk-key"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    secret = r.json()["secret_masked"]
    assert "super-secret-zk-key" not in (secret or "")
    r = await app_client.get(f"/api/devices/{dev_id}/credentials", headers=headers)
    assert r.status_code == 200
    assert r.json()[0]["secret_masked"] != "super-secret-zk-key"
    # delete requires confirm
    r = await app_client.delete(f"/api/devices/{dev_id}", headers=headers)
    assert r.status_code == 400
    r = await app_client.delete(
        f"/api/devices/{dev_id}?confirm=true", headers=headers
    )
    assert r.status_code == 200


async def test_import_export_users(auth_headers, app_client):
    headers = auth_headers
    r = await app_client.post(
        "/api/devices",
        json={"ip_address": "10.90.0.60", "adapter_name": "zkteco"},
        headers=headers,
    )
    dev_id = r.json()["id"]
    csv_content = (
        "user_id,employee_code,name,card_number,department,enabled\n"
        "1001,EMP1001,علی رضایی,123456,IT,true\n"
        "1002,EMP1002,Sara Mohammadi,654321,HR,true\n"
        "1003,EMP1003,Duplicate User,1111,IT,false\n"
    ).encode("utf-8")
    files = {"file": ("users.csv", io.BytesIO(csv_content), "text/csv")}
    r = await app_client.post(
        "/api/importexport/users/preview", files=files, headers=headers
    )
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["valid_rows"] == 3
    assert preview["total_rows"] == 3
    # apply
    r = await app_client.post(
        f"/api/importexport/users/apply?device_id={dev_id}",
        files=files,
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == 3
    # export
    r = await app_client.get(
        "/api/importexport/users/export?fmt=csv", headers=headers
    )
    assert r.status_code == 200
    assert b"1001" in r.content
    # list device users
    r = await app_client.get(f"/api/devices/{dev_id}/users", headers=headers)
    assert r.json()["total"] == 3


async def test_import_export_attendance(auth_headers, app_client):
    headers = auth_headers
    r = await app_client.post(
        "/api/devices",
        json={"ip_address": "10.90.0.61", "adapter_name": "zkteco"},
        headers=headers,
    )
    dev_id = r.json()["id"]
    rows = [
        "user_id,employee_code,event_time,event_type,verification_type",
        "1001,EMP1001,2024-03-01T08:01:22,CHECK_IN,FINGERPRINT",
        "1001,EMP1001,2024-03-01T17:02:00,CHECK_OUT,FINGERPRINT",
    ]
    content = "\n".join(rows).encode("utf-8")
    files = {"file": ("logs.csv", io.BytesIO(content), "text/csv")}
    r = await app_client.post(
        "/api/importexport/attendance/preview", files=files, headers=headers
    )
    assert r.status_code == 200, r.text
    r = await app_client.post(
        f"/api/importexport/attendance/apply?device_id={dev_id}",
        files=files,
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == 2
    r = await app_client.get(
        f"/api/devices/{dev_id}/attendance?date_from=2024-03-01T00:00:00",
        headers=headers,
    )
    assert r.json()["total"] == 2
    r = await app_client.get(
        "/api/attendance/export?fmt=json&device_id=" + dev_id, headers=headers
    )
    assert r.status_code == 200
    data = json.loads(r.content)
    assert len(data) == 2


async def test_audit_and_settings(auth_headers, app_client):
    headers = auth_headers
    r = await app_client.get("/api/audit?limit=5", headers=headers)
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    r = await app_client.get("/api/settings", headers=headers)
    assert r.status_code == 200
    keys = {s["key"] for s in r.json()}
    assert "discovery.scan_ports" in keys
    r = await app_client.put(
        "/api/settings/discovery.max_workers",
        json={"value": 128},
        headers=headers,
    )
    assert r.status_code == 200
    # operator cannot change settings
    r = await app_client.put(
        "/api/settings/discovery.max_workers",
        json={"value": 64},
        headers={"Authorization": f"Bearer {await _op(app_client)}"},
    )
    assert r.status_code == 403


async def test_scan_job_lifecycle(auth_headers, app_client):
    headers = auth_headers
    r = await app_client.post(
        "/api/networks",
        json={"cidr": "10.99.0.0/24", "label": "scan-me"},
        headers=headers,
    )
    net_id = r.json()["id"]
    r = await app_client.post(f"/api/networks/{net_id}/scan", headers=headers)
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    r = await app_client.get(f"/api/networks/discovery/jobs/{job_id}", headers=headers)
    assert r.status_code == 200
    # eventually completes (no hosts in that range reachable)
    import time

    for _ in range(120):
        r = await app_client.get(
            f"/api/networks/discovery/jobs/{job_id}", headers=headers
        )
        if r.json()["status"] in ("COMPLETED", "FAILED"):
            break
        time.sleep(0.5)
    assert r.json()["status"] == "COMPLETED"


async def _op(client):
    r = await client.post(
        "/api/auth/login",
        json={"username": "operator", "password": "Operator-Test-1234!"},
    )
    return r.json()["access_token"]

"""Pytest fixtures.

Environment is configured *before* any app import so cached Settings pick it
up.  A file-based sqlite database is used so several async sessions share one
store.
"""
from __future__ import annotations

import asyncio
import os
import sys

# Unique DB file per process: avoids Windows file-lock leftovers between runs.
_db_name = f"test_attendance_{os.getpid()}_{os.getpid()}.db"
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///./{_db_name}")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-000")
os.environ.setdefault("ENABLE_SCHEDULER", "false")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "Admin-Test-1234!")
os.environ.setdefault("BOOTSTRAP_OPERATOR_PASSWORD", "Operator-Test-1234!")
os.environ.setdefault("BOOTSTRAP_VIEWER_PASSWORD", "Viewer-Test-1234!")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", "placeholder")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core import crypto  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def _reset_db():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), _db_name)
    for suffix in ("", "-journal", "-wal", "-shm"):
        try:
            os.remove(db_path + suffix)
        except OSError:
            pass
    yield
    for suffix in ("", "-journal", "-wal", "-shm"):
        try:
            os.remove(db_path + suffix)
        except OSError:
            pass


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
async def schema_ready(event_loop):
    """Create the schema + seed once for the whole session."""
    from app.database import get_session_factory, init_db
    from app.services import seeder
    from app.services.settings_store import ensure_defaults

    await init_db()
    async with get_session_factory()() as db:
        await ensure_defaults(db)
        await seeder.run_seeder(db)
    yield


@pytest.fixture(scope="session")
async def app_client():
    """Async client with lifespan (seeds roles/networks/settings)."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            # fix crypto key to a deterministic Fernet key
            from cryptography.fernet import Fernet

            key = Fernet.generate_key().decode()
            crypto.set_key_for_tests(key)
            yield client


async def login_as(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def admin_token(app_client):
    return await login_as(app_client, "admin", "Admin-Test-1234!")


@pytest.fixture
async def operator_token(app_client):
    return await login_as(app_client, "operator", "Operator-Test-1234!")


@pytest.fixture
async def viewer_token(app_client):
    return await login_as(app_client, "viewer", "Viewer-Test-1234!")


@pytest.fixture
async def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}

"""Service-layer tests: DB persistence + sync against the mock ZK device."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.database import get_session_factory
from app.models import AttendanceLog, Device
from app.models.enums import DeviceStatus
from app.services import attendance_service, device_service, sync_service
from tests.mockserver import MockZKDevice


@pytest.fixture
def mock_zk():
    dev = MockZKDevice()
    dev.start()
    yield dev, dev.port
    dev.stop()


async def _make_device(mock_port: int) -> str:
    sf = get_session_factory()
    async with sf() as db:
        dev = Device(
            ip_address="127.0.0.1",
            port=mock_port,
            adapter_name="zkteco",
            protocol_name="zk_tcp",
            hostname="mock-zk",
            status=DeviceStatus.VERIFIED.value,
        )
        db.add(dev)
        await db.commit()
        return dev.id


async def test_full_sync_flow(mock_zk):
    dev, port = mock_zk
    device_id = await _make_device(port)
    sf = get_session_factory()

    async with sf() as db:
        dev = await db.get(Device, device_id)
        info = await device_service.fetch_and_store_device_info(db, dev)
        assert info["serial_number"] == "ZK-MOCK-0001"

        users = await device_service.read_and_store_users(db, dev)
        assert len(users) == 2
        assert {u.name for u in users} == {"Ned", "محمد احمدی"}

        stats = await attendance_service.pull_attendance_logs(db, dev)
        assert stats["inserted"] == 3
        assert stats["duplicates"] == 0

        stats2 = await attendance_service.pull_attendance_logs(db, dev)
        assert stats2["inserted"] == 0
        assert stats2["duplicates"] == 0
        assert dev.extra_config["attendance_sync"]["mode"] == "high_water_mark"

        count = await db.scalar(
            select(func.count(AttendanceLog.id)).where(
                AttendanceLog.device_id == device_id
            )
        )
        assert count == 3

    async with sf() as db:
        dev = await db.get(Device, device_id)
        job = await sync_service.create_sync_job(
            db, dev.id, "server_to_device", scope="users"
        )
        job_id = job.id
    await sync_service.execute_sync_job(job_id)
    async with sf() as db2:
        job = await db2.get(sync_service.SyncJob, job_id)
        assert job.status == "COMPLETED"

    async with sf() as db:
        dev = await db.get(Device, device_id)
        job2 = await sync_service.create_sync_job(
            db, dev.id, "device_to_server", scope="full"
        )
        job2_id = job2.id
    await sync_service.execute_sync_job(job2_id)
    async with sf() as db3:
        job2 = await db3.get(sync_service.SyncJob, job2_id)
        assert job2.status == "COMPLETED"
        assert job2.stats["users_pulled"] == 2


async def test_sync_job_offline_device():
    """A down device must fail its own sync - not crash anything else."""
    sf = get_session_factory()
    async with sf() as db:
        dev = Device(
            ip_address="127.0.0.1",
            port=1,  # closed port
            adapter_name="zkteco",
            protocol_name="zk_tcp",
        )
        db.add(dev)
        await db.commit()
        job = await sync_service.create_sync_job(db, dev.id, "device_to_server")
        job_id = job.id
    await sync_service.execute_sync_job(job_id)
    async with sf() as db2:
        job = await db2.get(sync_service.SyncJob, job_id)
        assert job.status == "FAILED"
        assert job.error

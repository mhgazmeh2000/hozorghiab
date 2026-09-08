"""End-to-end adapter <-> mock-device tests over TCP sockets."""
from __future__ import annotations

import pytest

from app.adapters.base import NotSupported
from app.adapters.zkteco import ZKTecoAdapter
from app.adapters.zk_protocol import ZKConnection
from tests.mockserver import MockZKDevice


@pytest.fixture
def mock_device():
    dev = MockZKDevice()
    dev.start()
    yield dev
    dev.stop()


async def test_connection_handshake(mock_device):
    conn = ZKConnection("127.0.0.1", mock_device.port)
    await conn.connect()
    assert conn.session_id != 0
    t = await conn.get_time()
    assert t.year >= 2020
    await conn.close()


async def test_get_device_info(mock_device):
    adapter = ZKTecoAdapter({"ip_address": "127.0.0.1", "port": mock_device.port})
    info = await adapter.get_device_info()
    assert info.serial_number == "ZK-MOCK-0001"
    assert info.model == "K14"
    assert info.brand == "ZKTeco"
    assert info.platform == "ZEM760"
    assert "6.60" in (info.firmware_version or "")
    assert info.user_count == 2
    assert info.attendance_count == 3
    assert info.device_time is not None
    await adapter.disconnect()


async def test_read_users(mock_device):
    adapter = ZKTecoAdapter({"ip_address": "127.0.0.1", "port": mock_device.port})
    users = await adapter.get_users()
    by_id = {u.user_id_on_device: u for u in users}
    assert set(by_id) == {"555", "1002"}
    assert by_id["555"].name == "Ned"
    assert by_id["555"].card_number == "222"
    assert by_id["555"].password_status == "SET"
    assert by_id["1002"].name == "محمد احمدی"
    await adapter.disconnect()


async def test_read_attendance(mock_device):
    adapter = ZKTecoAdapter({"ip_address": "127.0.0.1", "port": mock_device.port})
    logs = await adapter.get_attendance_logs()
    assert len(logs) == 3
    by_user = {l.user_id_on_device for l in logs}
    assert "555" in by_user and "1002" in by_user
    first = logs[0]
    assert first.verification_type in ("FINGERPRINT", "CARD")
    assert first.event_time.year >= 2018
    await adapter.disconnect()


async def test_log_count(mock_device):
    adapter = ZKTecoAdapter({"ip_address": "127.0.0.1", "port": mock_device.port})
    assert await adapter.get_attendance_log_count() == 3
    await adapter.disconnect()


async def test_create_user_via_mock(mock_device):
    from app.adapters.base import DeviceUserRecord

    adapter = ZKTecoAdapter({"ip_address": "127.0.0.1", "port": mock_device.port})
    res = await adapter.create_user(
        DeviceUserRecord(user_id_on_device="777", name="Test", card_number="1234")
    )
    assert res["user_id"] == "777"
    await adapter.disconnect()


async def test_probe_detects_zk(mock_device):
    result = await ZKTecoAdapter.probe("127.0.0.1", mock_device.port, 2.0)
    assert result.detected is True
    assert result.protocol == "zk_tcp"
    assert result.confidence > 0.9


async def test_probe_negative():
    result = await ZKTecoAdapter.probe("127.0.0.1", 1, 1.0)  # port 1 closed
    assert result.detected is False


async def test_unsupported_op_raises_not_supported():
    from app.adapters.base import NotSupported
    from app.adapters.vendor_base import UnverifiedVendorAdapter

    v = UnverifiedVendorAdapter()
    assert v.get_capabilities()["read_users"] is False
    with pytest.raises(NotSupported):
        await v.get_users()

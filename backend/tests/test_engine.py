"""Discovery-engine tests: full pipeline against mock devices."""
from __future__ import annotations

import pytest

from app.discovery.engine import discover_host, discover_many, build_host_list
from app.discovery.validate import validate_cidr, validate_ip, network_hosts, ip_in_any
from tests.mockserver import MockHttpDevice, MockZKDevice


@pytest.fixture
def mock_zk():
    dev = MockZKDevice()
    port = dev.start()
    yield dev, port
    dev.stop()


@pytest.fixture
def mock_http():
    dev = MockHttpDevice(server_header="ZKTeco-webserver", title="ZKTime")
    port = dev.start()
    yield dev, port
    dev.stop()


async def test_discover_zk_host(mock_zk):
    dev, port = mock_zk
    report = await discover_host("127.0.0.1", [port], deep_verify=True, zk_probe=True)
    assert report["reachable"] is True
    assert port in report["open_ports"]
    zk = report["zk"]
    assert zk and zk["verified"] is True
    assert report["verdict"]["state"] == "PROTOCOL_VERIFIED"
    assert "zkteco" in report["adapter_candidates"]
    info = report["device_info"]
    assert info["serial_number"] == "ZK-MOCK-0001"
    assert info["model"] == "K14"


async def test_discover_http_host(mock_http):
    dev, port = mock_http
    report = await discover_host("127.0.0.1", [port], deep_verify=False)
    assert report["reachable"] is True
    http = report["http"]
    assert http and http[0]["status_code"] == 200
    assert http[0]["title"] == "ZKTime"
    assert report["verdict"]["state"] in ("PORT_OPEN", "UNKNOWN")
    # HTTP alone must never produce a PROTOCOL_VERIFIED verdict
    assert report["verdict"]["state"] != "PROTOCOL_VERIFIED"


async def test_discover_unreachable_host():
    report = await discover_host("127.0.0.1", [1], deep_verify=False)
    assert report["reachable"] is False


async def test_discover_many_progress(mock_zk):
    dev, port = mock_zk
    progress = []
    reports = await discover_many(
        ["127.0.0.1", "127.0.0.2"],
        [port],
        max_workers=4,
        progress=lambda done, total: progress.append((done, total)),
        deep_verify=False,
    )
    assert len(reports) == 2
    assert progress
    found = [r for r in reports if r["reachable"]]
    assert len(found) == 1


def test_build_host_list_excludes():
    hosts = build_host_list(["127.0.0.0/30"], ["127.0.0.2"])
    assert hosts == ["127.0.0.1"]


def test_validation():
    assert validate_cidr("10.0.0.0/24").prefixlen == 24
    assert validate_ip("10.1.2.3").version == 4
    with pytest.raises(ValueError):
        validate_cidr("0.0.0.0/0")  # wider than /16 refused
    with pytest.raises(ValueError):
        validate_ip("not-an-ip")
    assert ip_in_any("10.0.0.5", ["10.0.0.0/24"]) is True
    assert len(network_hosts("192.168.0.0/30")) == 2


def test_build_host_list_dedup():
    assert build_host_list(["127.0.0.0/30", "127.0.0.0/30"]) == [
        "127.0.0.1",
        "127.0.0.2",
    ]

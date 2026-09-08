"""Protocol-level tests for the ZK wire codec.

The checksum vectors are taken directly from the published protocol spec
(github.com/adrobinoga/zk-protocol) so the framing implementation is pinned
to an authoritative reference.
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.adapters.zk_protocol import (
    checksum,
    decode_frame,
    decode_zk_time,
    encode_packet,
    encode_zk_time,
    parse_att_entries,
    parse_user_entries,
)
from tests.mockserver import build_att_entry, build_user_entry


def test_checksum_spec_vector_1():
    # spec: payload `0b005a17f38d03005a4b4661636556657273696f6e00`
    # checksum field (5a17 LE == 0x175a); computed over payload sans checksum
    payload = bytes.fromhex("0b00") + bytes.fromhex("0000") + bytes.fromhex("f38d0300") + b"ZKFaceVersion\x00"
    assert checksum(payload) == 0x175A


def test_checksum_spec_vector_2():
    raw = bytes.fromhex("d007296af38d0a0009")  # stored checksum bytes 6a 29
    clean = raw[:2] + b"\x00\x00" + raw[4:]
    assert checksum(clean) == 0x6A29


def test_time_roundtrip():
    for t in [
        dt.datetime(2024, 1, 15, 8, 30, 0),
        dt.datetime(2018, 6, 25, 17, 41, 5),
        dt.datetime(2030, 12, 31, 23, 59, 59),
        dt.datetime(2000, 1, 1, 0, 0, 0),
    ]:
        assert decode_zk_time(encode_zk_time(t)) == t


def test_frame_roundtrip():
    frame = encode_packet(2000, 0x8DF3, 5, b"\x7eOS\x00")
    dec = decode_frame(frame)
    assert dec["command"] == 2000
    assert dec["session_id"] == 0x8DF3
    assert dec["reply_id"] == 5
    assert dec["checksum_ok"] is True


def test_frame_bad_marker():
    with pytest.raises(Exception):
        decode_frame(b"\x00" * 20)


def test_parse_user_entries_matches_mock_builder():
    e1 = build_user_entry(13, "555", name="Ned", password="444", card=0xDE, group=2)
    e2 = build_user_entry(14, "1002", name="محمد احمدی", password="", card=0, group=1)
    dataset = __import__("struct").pack("<I", 2 * 72) + e1 + e2
    users = parse_user_entries(dataset)
    assert len(users) == 2
    assert users[0]["user_sn"] == 13
    assert users[0]["user_id"] == "555"
    assert users[0]["name"] == "Ned"
    assert users[0]["card_number"] == "222"
    assert users[0]["password_present"] is True
    assert users[1]["user_id"] == "1002"
    assert users[1]["name"] == "محمد احمدی"
    assert users[1]["password_present"] is False


def test_parse_att_entries():
    a1 = build_att_entry(13, "999111333", 1, dt.datetime(2018, 6, 25, 17, 41, 5), 0)
    a2 = build_att_entry(14, "1002", 2, dt.datetime(2024, 2, 10, 8, 2, 33), 1)
    dataset = __import__("struct").pack("<I", 2 * 40) + a1 + a2
    logs = parse_att_entries(dataset)
    assert len(logs) == 2
    assert logs[0]["user_id"] == "999111333"
    assert logs[0]["verification_type"] == "FINGERPRINT"
    assert logs[0]["event_time"] == dt.datetime(2018, 6, 25, 17, 41, 5)
    assert logs[0]["event_state"] == "CHECK_IN"
    assert logs[1]["verification_type"] == "CARD"
    assert logs[1]["event_state"] == "CHECK_OUT"


def test_user_dataset_size_mismatch_raises():
    import struct

    with pytest.raises(Exception):
        parse_user_entries(struct.pack("<I", 10) + b"\x00" * 10)

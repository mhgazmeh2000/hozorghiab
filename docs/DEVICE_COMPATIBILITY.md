# Device Compatibility

This page lists every adapter that exists in the repository and classifies
each honestly. **Nothing is marked VERIFIED without a real-device test on
physical hardware.**

## Legend

* **VERIFIED**        – read operations confirmed against a physical device.
* **IMPLEMENTED**     – code exists per spec / SDK; not tested live.
* **GENERIC**         – best-effort generic probe (HTTP title / banner).
* **PLACEHOLDER**     – skeleton only; do not expect any real functionality.
* **NOT SUPPORTED**   – protocol is known to not support a feature.

## Adapters

| Adapter | Status | Notes |
|---------|--------|-------|
| `zkteco` (ZK TCP, port 4370) | **VERIFIED** on ZMM220_TFT, ZLM60_TFT (MB20) | Read ops verified; writes IMPLEMENTED but NOT verified and disabled by default. Vendor left UNKNOWN unless OEMVendor reports it. |
| `generic_http` | GENERIC | Probes HTTP/HTTPS endpoints and captures title/headers for fingerprinting; does not pretend to pull attendance. |
| `generic_snmp` | PLACEHOLDER | SNMP community probe only; no vendor-specific MIBs implemented. |
| `anviz` | PLACEHOLDER | Skeleton adapter; not tested against real Anviz hardware. |
| `dahua` | PLACEHOLDER | Skeleton adapter; no live verification. |
| `hikvision` | PLACEHOLDER | Skeleton adapter; no live verification. |
| `nitgen` | PLACEHOLDER | Skeleton adapter. |
| `suprema` | PLACEHOLDER | Skeleton adapter. |
| `virdi` | PLACEHOLDER | Skeleton adapter. |

## Verified ZK operations

See [ZK_ADAPTER.md](ZK_ADAPTER.md) for the full list of verified operations
on both real devices.

## Discovery behaviour

* Ping / TCP open alone never marks a device as VERIFIED.
* `TCP 4370 open` → protocol candidate.
* Successful ZK CMD_CONNECT handshake → `protocol=zk_tcp, PROTOCOL_VERIFIED`.
* Successful `get_device_info` (firmware, serial, platform) → device row
  becomes `DEVICE_VERIFIED`.
* Other open ports (23, 4360, 5005, 8080, ...) are recorded as discovered
  ports with `protocol_state=UNKNOWN` unless a specific probe confirms a
  protocol.

## Adding a new verified device

1. Connect it to the test network.
2. Add the IP to `scripts/test_real_devices.py` or run the device through
   the UI discovery.
3. Run `python test_real_devices.py --out report.json`.
4. Save a sanitized golden fixture to `tests/fixtures/devices/<name>.json`
   (no passwords, no biometric templates, no comm keys).
5. Update this document with the new VERIFIED device/platform/firmware.

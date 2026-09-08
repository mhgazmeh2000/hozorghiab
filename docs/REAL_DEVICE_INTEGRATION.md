# Real Device Integration

This repository ships with a read-only real-device verification flow.
Write operations exist in the adapter but are **disabled by default** and
require explicit operator approval + RBAC + audit logging before they are
exposed.

## Verified devices

Two devices on the operator's LAN have been confirmed reachable with
pyzk 0.9:

| Tag | IP | Port | Platform | FW |
|-----|----|------|----------|----|
| A | 172.16.0.20 | 4370 | ZMM220_TFT | Ver 6.60 Apr 27 2017 |
| B | 172.16.32.21 | 4370 | ZLM60_TFT (MB20) | Ver 6.60 May 3 2016 |

Sanitized golden fixtures for deterministic parser tests are at:
- `tests/fixtures/devices/zk_172_16_0_20.json`
- `tests/fixtures/devices/zk_172_16_32_21.json`

Fixtures intentionally omit credentials and biometric data.

## Running the verification

```bash
cd backend
python test_real_devices.py                 # human-readable
python test_real_devices.py --json          # JSON to stdout
python test_real_devices.py --out report.json
```

Windows (PowerShell):
```powershell
cd backend
.\venv\Scripts\activate
python test_real_devices.py
```

Each step reports one of:

- **PASS** – succeeded and data was received.
- **FAIL** – device responded with an error / invalid payload.
- **NOT_SUPPORTED** – adapter confirms this operation is unavailable.
- **NOT_VERIFIED** – not enough evidence to confirm (shouldn't normally appear
  in this script).
- **EXECUTION_ENVIRONMENT** – the machine running the test cannot reach the
  device (routing, firewall, VPN, sandbox). This does NOT mean the device is
  offline. Run from the operator's network.

## Read-only operations verified by the script

1. TCP connect to port 4370
2. ZK protocol handshake (CMD_CONNECT → ACK_OK + session id)
3. Firmware version (CMD_GET_VERSION / 1100)
4. Serial number (~SerialNumber)
5. Platform (~Platform)
6. Device name (~DeviceName)
7. MAC address (MAC option)
8. Network parameters (IP/Netmask/Gateway)
9. Device time (CMD_GET_TIME)
10. User list (DATA_WRRQ 01090005)
11. Attendance log list (CMD_ATTLOG_RRQ / DATA_WRRQ 010d0000)

## Per-device configuration

Each device may override:

- Port (default 4370)
- Communication Key (ZK commkey) — stored encrypted as a
  `DeviceCredential` of kind `communication_key`, verification state tracked.
- Connect / read timeout, retry count, backoff.

Communication Key verification state (`VERIFIED` / `NOT_VERIFIED` / `FAILED`)
is stored per credential row so the UI can show the operator whether a key
actually worked. The code never hard-codes `password=0`.

## Write operations

The following operations exist in the ZK adapter but are treated as follows:

| Operation | implemented | verified | enabled by default |
|-----------|:-----------:|:--------:|:------------------:|
| create_user | yes | NO | no (destructive) |
| update_user | yes | NO | no (destructive) |
| delete_user | yes | NO | no (destructive) |
| clear_attendance_logs | yes | NO | no (destructive) |
| set_time | yes | NO | no (destructive) |
| restart / poweroff | NOT SUPPORTED | — | no |
| read_templates | NO (intentionally) | NO | no |

Write endpoints additionally require:

- admin role (RBAC)
- `?confirm=true` query parameter
- per-capability `enabled=true` flag
- audit log entry

## Discovery semantics

- TCP 23 / 4360 open → stored as discovered ports; protocol NOT assumed.
- TCP 4370 open + successful ZK handshake → `protocol=zk_tcp`,
  `protocol_state=PROTOCOL_VERIFIED`.
- Vendor is read from `~OEMVendor` when available; otherwise `vendor=UNKNOWN`.
  ZK-protocol compatibility is recorded separately from brand.

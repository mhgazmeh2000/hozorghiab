# ZK TCP Adapter

The `zkteco` adapter implements the documented ZKTeco "Standalone series"
TCP protocol on port 4370. Many OEM devices use the same protocol; the
adapter labels them with `protocol=zk_tcp` and leaves `vendor=UNKNOWN`
unless the device itself reports `~OEMVendor`.

## Verified devices

| IP | Platform | FW | Status |
|----|----------|----|--------|
| 172.16.0.20 | ZMM220_TFT | Ver 6.60 Apr 27 2017 | protocol handshake, firmware, serial, platform, MAC, network, time, users, attendance VERIFIED |
| 172.16.32.21 | ZLM60_TFT (MB20) | Ver 6.60 May 3 2016 | same operations VERIFIED |

Run `python test_real_devices.py` from the operator LAN to regenerate
the report.

## Read operations (verified on both devices)

* connect (CMD_CONNECT / 1000)
* get_firmware_version (CMD_GET_VERSION / 1100)
* get_serialnumber (~SerialNumber OPTIONS_RRQ)
* get_platform (~Platform)
* get_device_name (~DeviceName)
* get_mac (MAC)
* get_network_params (IPAddress / NetMask / Gateway)
* get_time (CMD_GET_TIME / 201)
* get_fp_version (~ZKFPVersion)
* get_face_version (~FaceFunOn)
* get_pin_width (~PIN2Width)
* get_users (DATA_WRRQ / dataset 01090005)
* get_attendance_logs (CMD_ATTLOG_RRQ / dataset 010d0000)
* get_free_sizes (CMD_GET_FREE_SIZES / 50) for capacities/counts

## Write operations (implemented / NOT verified / disabled by default)

* create_user / update_user (CMD_USER_WRQ / 8)
* delete_user (CMD_DELETE_USER / 18)
* clear_attendance_logs (CMD_CLEAR_ATTLOG / 15)
* set_time (CMD_SET_TIME / 202)

These operations exist in the adapter per protocol spec but have NOT been
tested against a real device as part of this release. They will not be
exposed by the API unless:

1. The capability is explicitly `verified=true` on the device row (set
   only after a successful manual verify by an admin).
2. The operator sets `enabled=true` on that capability.
3. The calling user has the `admin` role and passes `confirm=true`.

## Biometrics

Counts and capacities are reported (`fingerprint_count`, `face_count`,
`card_count` and their capacities). Actual biometric template transfer
(`read_templates` / `write_templates`) is intentionally not enabled —
do NOT claim it is supported until it is implemented and tested.

## Port 4360

Discovery stores port 4360 as a discovered TCP port but does NOT assign
any protocol to it without further evidence. Port 4370 is the only port
on which ZK protocol is verified.

## Incremental sync

* The ZK adapter always pulls the full attendance dataset; the high-water
  mark filter and deduplication happen at the service layer using
  `(event_time, raw encoded time, user_id)` as the cursor.
* Cursor is advanced only after a successful DB commit.
* Idempotency: on re-sync, duplicate events are silently skipped via the
  SHA-256 fingerprint unique constraint.

## Compatibility note

Some OEM firmwares reject `CMD_DATA_WRRQ` (1503); the adapter falls back
to the legacy `CMD_DB_RRQ` (7) and surfaces a clear error if both fail
(rather than fabricating data).

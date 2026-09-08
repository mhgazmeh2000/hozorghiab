# Real Device Test Report

Test timestamp: 2026-09-07T11:44:24.500224+00:00
Execution environment: opt-in pytest suite on the current host
Read-only suite: no write operation was called.

## 172.16.0.20:4370

| Test | Status | Scope | Value/Error |
|---|---|---|---|
| TCP 4370 connectivity | FAIL | EXECUTION_ENVIRONMENT | TimeoutError |
| ZK protocol handshake | FAIL | EXECUTION_ENVIRONMENT | cannot open TCP connection to 172.16.0.20:4370:  |
| connect() | FAIL | EXECUTION_ENVIRONMENT | cannot open TCP connection to 172.16.0.20:4370:  |
| get_firmware_version() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_serialnumber() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_platform() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_device_name() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_mac() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_network_params() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_time() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_fp_version() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_face_version() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_pin_width() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_users() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_attendance() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |

### Expected reference

```json
{'platform': 'ZMM220_TFT', 'firmware': 'Ver 6.60 Apr 27 2017', 'serial': 'ADWC175060007', 'mac': '00:17:61:12:c9:b4', 'users': 167, 'attendance': 12799, 'user_capacity': 2000, 'attendance_capacity': 80000, 'fingerprints': 168, 'faces': 160}
```

### Limitations

- Values are VERIFIED only when the corresponding read returns PASS on this run.
- A blocked route is an execution-environment failure, not proof that the device is offline.

## 172.16.32.21:4370

| Test | Status | Scope | Value/Error |
|---|---|---|---|
| TCP 4370 connectivity | FAIL | EXECUTION_ENVIRONMENT | TimeoutError |
| ZK protocol handshake | FAIL | EXECUTION_ENVIRONMENT | cannot open TCP connection to 172.16.32.21:4370:  |
| connect() | FAIL | EXECUTION_ENVIRONMENT | cannot open TCP connection to 172.16.32.21:4370:  |
| get_firmware_version() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_serialnumber() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_platform() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_device_name() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_mac() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_network_params() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_time() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_fp_version() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_face_version() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_pin_width() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_users() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |
| get_attendance() | NOT_VERIFIED | EXECUTION_ENVIRONMENT | connect() did not succeed |

### Expected reference

```json
{'platform': 'ZLM60_TFT', 'device_name': 'MB20', 'firmware': 'Ver 6.60 May 3 2016', 'serial': '2623320414184', 'mac': '00:17:61:10:51:1f', 'users': 90, 'attendance': 38025, 'user_capacity': 200, 'attendance_capacity': 50000, 'fingerprints': 108, 'faces': 83}
```

### Limitations

- Values are VERIFIED only when the corresponding read returns PASS on this run.
- A blocked route is an execution-environment failure, not proof that the device is offline.

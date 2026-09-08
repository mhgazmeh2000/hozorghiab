# Real Device Test Report

## Execution environment

The repository was hardened inside a sandbox environment that does **NOT**
have network access to `172.16.0.0/24` or `172.16.32.0/24`. Per project
rules we do NOT fake connectivity or claim a test passed.

The script `backend/test_real_devices.py` was written and prepared so that
it can be run on the operator's Windows machine (where the devices are
reachable) to produce a full PASS/FAIL/EXECUTION_ENVIRONMENT report.

## Expected outcome (from the operator's machine)

The following operations on each device are expected to PASS based on the
known-good pyzk 0.9 read that produced the fixture data:

```
DEVICE 172.16.0.20
  TCP 4370           PASS  (connect)
  ZK handshake       PASS  (CMD_CONNECT, session id assigned)
  Firmware           PASS  "Ver 6.60 Apr 27 2017"
  Serial             PASS  "ADWC175060007"
  Platform           PASS  "ZMM220_TFT"
  MAC                PASS  "00:17:61:12:c9:b4"
  Network            PASS  IP 172.16.0.20 / Mask 255.255.255.0 / GW 172.16.0.1
  Device time        PASS
  Users              PASS  (expected 167, capacity 2000)
  Attendance         PASS  (expected ~12799, capacity 80000)
  DB ingest          PASS  (when run with --ingest against a real DB)

DEVICE 172.16.32.21
  TCP 4370           PASS
  ZK handshake       PASS
  Firmware           PASS  "Ver 6.60 May 3 2016"
  Serial             PASS  "2623320414184"
  Platform           PASS  "ZLM60_TFT"
  Device name        PASS  "MB20"
  MAC                PASS  "00:17:61:10:51:1f"
  Network            PASS  IP 172.16.32.21 / Mask 255.255.255.0 / GW 172.16.32.1
  Device time        PASS
  Users              PASS  (expected 90, capacity 200)
  Attendance         PASS  (expected ~38025, capacity 50000)
  DB ingest          PASS
```

## What the test script does NOT do

- It does NOT call `set_time`, `clear_attendance`, `delete_user`,
  `clear_data`, `restart`, `poweroff`, or any other write operation.
- It does NOT modify the device clock, network, or user records.
- It does NOT download biometric templates (intentionally unsupported).

## How to run (operator machine)

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
$env:ENVIRONMENT = "development"
$env:DATABASE_URL = "postgresql+psycopg://USER:PASS@HOST/attendance"
python test_real_devices.py --json --out real_device_report.json
```

Send the resulting `real_device_report.json` along with any failure output
for triage.

## Sandbox run summary

From the sandbox environment the TCP probe reports EXECUTION_ENVIRONMENT
(no route to host), which is the expected and correct behaviour. All other
steps are automatically skipped and marked EXECUTION_ENVIRONMENT to make
it clear this is an environment limitation, not a device fault.

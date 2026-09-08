# Production Readiness

This document summarises what is IMPLEMENTED vs VERIFIED vs NOT_VERIFIED vs
NOT_SUPPORTED for a production deployment, and how to operate it safely.

## Architecture (production)

```
┌──────────┐   ┌──────────┐   ┌──────────┐
│ Frontend │──▶│  API (×N)│──▶│ Postgres │
│ (nginx)  │   │ FastAPI  │   └──────────┘
└──────────┘   └────┬─────┘
                    │ enqueue
                    ▼
               ┌─────────┐   ┌───────┐
               │  Redis   │──▶│Worker │
               │ (broker) │   │Celery │
               └─────────┘   └───────┘
                    ▲
                    │ beat
               ┌─────────┐
               │  Beat   │
               │ Celery  │
               └─────────┘
```

* API processes do NOT run the built-in scheduler in production
  (`ENABLE_SCHEDULER=false` on API, beat container owns scheduling).
* Rate limiting uses Redis so N API replicas share the same counters.
* The Celery worker consumes `freebuff.execute_sync_job` and
  `freebuff.execute_discovery_job` tasks.
* Celery Beat owns periodic scan/sync dispatch.

## Environment variables (REQUIRED in production)

| Variable | Purpose |
|----------|---------|
| `ENVIRONMENT=production` | Activates strict validation. |
| `SECRET_KEY` | JWT signing key (≥32 random bytes). |
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet key for device credentials at rest. |
| `DATABASE_URL` | `postgresql+psycopg://user:pass@postgres:5432/attendance`. |
| `REDIS_URL=redis://redis:6379/0` | Celery broker + rate limit backend. |
| `TASK_RUNNER=celery` | Required in production. |
| `RATE_LIMIT_BACKEND=redis` | Required in production. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | Used by docker-compose. |
| `BOOTSTRAP_ADMIN_PASSWORD` (etc.) | Strong first-run passwords. |
| `CORS_ORIGINS` | Restrict to the frontend origin (do NOT use `*`). |

Startup validation refuses to boot if production secrets are missing or set to
well-known defaults.

## Credential handling

* Device credentials (communication keys, SNMP community strings, HTTP
  passwords) are stored encrypted with Fernet (AES-128-CBC + HMAC-SHA256)
  using `CREDENTIAL_ENCRYPTION_KEY`.
* `CREDENTIAL_ENCRYPTION_KEY` is NEVER auto-generated in production. You
  must supply it via the environment so all replicas share the same key
  and redeploys do not invalidate stored credentials.
* Development mode auto-generates a key persisted in `system_settings` for
  single-node convenience (clearly labelled in logs).

## Rate limiting

* `memory` backend (dev): in-process sliding window.
* `redis` backend (prod): atomic Lua sliding window sorted-set per
  `(scope, client_ip)`. Redis failure falls back to in-memory with a
  warning, so a Redis outage does not lock the API out.

## Capability safety model

Per device capability row stores:

| field | meaning |
|-------|---------|
| `implemented` | code exists per protocol spec |
| `verified` | successfully executed against the real device |
| `enabled` | operator allows it in UI / scheduling |
| `is_destructive` | mutates device state |

Destructive capabilities (`delete_users`, `clear_data`, `set_time`,
`delete_logs`, `sync_users_to_device`, `write_templates`, ...) default to
`enabled=false` even after verification and require explicit operator
enabling + RBAC approval + confirmation before execution.

## Device status model

| status | meaning |
|--------|---------|
| `UNKNOWN` | never probed |
| `PROBE_UNREACHABLE` | current environment cannot connect (does NOT prove device offline) |
| `OFFLINE_VERIFIED` | device was previously ONLINE/VERIFIED, recent probes fail from production network |
| `ONLINE_PROTOCOL_OPEN` | port open, protocol not yet confirmed |
| `ONLINE_PROTOCOL_VERIFIED` | successful protocol handshake + at least one read op |
| `VERIFIED` | operator explicitly accepted / full info read |
| `DISABLED` | management disabled by operator |

Dashboard surfaces `last_probe_at`, `last_probe_error`, `last_online_at`,
`device_time_offset_s`, `storage_usage_pct` alongside the status so a
reachability failure in the wrong environment is not mistaken for a real
outage.

## Incremental attendance sync

* High-water cursor (event_time, raw_time, user_id) is stored on the
  device row inside `extra_config.attendance_sync.cursor`.
* Cursor advances ONLY after `db.commit()` of inserted rows.
* Inserts are chunked (500 records) for memory safety on large logs
  (Device B ~38k records).
* `event_hash` (SHA-256 over device_id, user, event_time, verify type,
  raw_state, raw_punch) with a uniqueness constraint guarantees
  idempotent re-runs.

## Biometrics

The system records fingerprint/face/card *counts* and *capacities*. It does
NOT claim to synchronize biometric templates until that capability is both
implemented and verified (it is currently `NOT_VERIFIED`).

## Deployment checklist

- [ ] Generate `SECRET_KEY` via `python -c "import secrets; print(secrets.token_hex(32))"`.
- [ ] Generate `CREDENTIAL_ENCRYPTION_KEY` via `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- [ ] Set strong bootstrap passwords (DO NOT reuse the dev defaults).
- [ ] Run `alembic upgrade head` against PostgreSQL before first boot.
- [ ] Restrict `CORS_ORIGINS` to the real frontend origin.
- [ ] Run `python test_real_devices.py` from a machine that can reach the
      devices and verify all read steps PASS.
- [ ] Destructive capabilities remain disabled by default — enable only
      after RBAC review.

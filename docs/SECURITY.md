# Security

## Secrets management

* No default production passwords are shipped in source or README.
* `ENVIRONMENT=production` refuses to boot with placeholder/insecure values
  for `SECRET_KEY`, `CREDENTIAL_ENCRYPTION_KEY`, and bootstrap passwords.
* `.env` is gitignored; `.env.example` contains placeholders only.
* `docker-compose.yml` pulls all credentials from `.env` (no hard-coded
  `POSTGRES_PASSWORD=attendance` anymore).

## Authentication & JWT

* Passwords hashed with bcrypt (work factor 12).
* JWTs are HS256 signed with `SECRET_KEY`, validated with `iss`, `iat`, `exp`,
  and `sub` claims.
* In development when `SECRET_KEY` is unset, an ephemeral key is generated
  per process startup (sessions reset on restart); this path is disabled in
  production.

## Credential encryption at rest

* Device credentials (ZK commkey, SNMP community, HTTP passwords, API
  keys) are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) before
  storage.
* Production: `CREDENTIAL_ENCRYPTION_KEY` must be supplied externally and
  is never auto-generated or persisted to the database.
* Dev: auto-generate + persist in `system_settings._credential_encryption_key`
  (single-node convenience; a warning is logged).

## Rate limiting

* Auth endpoints: 30 req/min per IP (configurable).
* General API: 600 req/min per IP (configurable).
* Production backend: Redis-backed sliding window (atomic Lua, shared
  across workers).
* Redis outages fall back to in-memory with a logged warning so the API
  stays up.

## RBAC

Roles: `admin`, `operator`, `viewer`.

* `viewer` – read-only.
* `operator` – read + initiate sync/discovery (non-destructive).
* `admin` – everything, including user/credential management and
  destructive device ops (which also require per-capability enabled flag
  and explicit confirmation).

Destructive endpoints (`delete_user`, `clear_attendance`, `set_time`,
user deletion, network deletion...) require admin role AND `confirm=true`
AND the matching device capability must be `verified=true, enabled=true`.

## Audit logging

All login/logout/sync/discovery/config mutations are recorded in
`audit_logs` with actor, source IP, duration, and parameterised details.

## CORS

`CORS_ORIGINS` defaults to `*` in development; production deployments MUST
restrict it to the frontend origin. A startup warning is emitted when `*`
is used in production.

## Communication Key / per-device settings

ZK communication key is configurable per device (never hard-coded to `0`).
Each credential tracks verification state so the UI can show whether it
successfully authenticated.

## Safe defaults for real devices

* Destructive capabilities default to `enabled=false` even after
  verification.
* Attendance ingestion never silently maps raw punch state to IN/OUT
  without a verified mapping; `event_type` stays UNKNOWN while
  `raw_state` and `raw_punch` are preserved verbatim.
* Vendor is never inferred from port or protocol alone.

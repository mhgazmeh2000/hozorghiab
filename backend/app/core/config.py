"""Application configuration.

Everything is configurable through environment variables / .env.  Nothing
security- or network-relevant is hard-coded; the default scan networks are a
seed list stored in the database (SystemSetting/DeviceNetwork), so operators
may change them from the dashboard without touching code.

SECURITY MODEL
--------------
* In development (ENVIRONMENT=development) convenience defaults are tolerated
  (SQLite, auto-generated SECRET_KEY, auto-generated CREDENTIAL_ENCRYPTION_KEY
  persisted in the local DB, documented bootstrap passwords).
* In production (ENVIRONMENT=production) the server refuses to start unless
  SECRET_KEY, CREDENTIAL_ENCRYPTION_KEY, and non-default bootstrap passwords
  are explicitly provided via the environment or .env.
"""
from __future__ import annotations

import logging
import os
import secrets
from functools import lru_cache

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Seed list imported on first boot (then fully user-editable in the DB).
DEFAULT_NETWORK_SEED = [
    "172.16.0.0/24",
    "172.16.8.0/24",
    "172.16.10.0/24",
    "172.16.15.0/24",
    "172.16.25.0/24",
    "172.16.27.0/24",
    "172.16.31.0/24",
    "172.16.32.0/24",
    "172.16.50.0/24",
    "172.16.61.0/24",
]

DEFAULT_SCAN_PORTS = [80, 443, 8080, 8000, 8081, 4360, 4370, 5005]

# Known-insecure placeholder values we refuse to accept in production.
_INSECURE_SECRET_KEYS = {
    "",
    "CHANGE_ME",
    "CHANGE_ME__generate_with_openssl_rand_hex_32",
    "changeme",
    "secret",
}
_INSECURE_BOOTSTRAP_PASSWORDS = {
    "",
    "admin",
    "password",
    "changeme",
}
_DEV_DEFAULT_ADMIN_PASSWORD = "dev-admin-only-please-change"
_DEV_DEFAULT_OPERATOR_PASSWORD = "dev-operator-only"
_DEV_DEFAULT_VIEWER_PASSWORD = "dev-viewer-only"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Freebuff Attendance Manager"
    app_version: str = "0.1.0"
    environment: str = os.environ.get("ENVIRONMENT", "development").lower()
    debug: bool = False
    api_prefix: str = "/api"

    # Database ------------------------------------------------------------
    # Default to SQLite for zero-friction local dev; set Postgres in prod.
    database_url: str = "sqlite+aiosqlite:///./attendance.db"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Security ------------------------------------------------------------
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    jwt_issuer: str = "freebuff-attendance"
    # Fernet key used to encrypt device credentials. In production this MUST
    # be supplied (44-char urlsafe base64 from Fernet.generate_key()). In dev
    # we allow auto-generation + DB persistence (single-node convenience).
    credential_encryption_key: str = ""
    # Master bootstrap passwords (only applied when seeding/creating users).
    bootstrap_admin_password: str = ""
    bootstrap_operator_password: str = ""
    bootstrap_viewer_password: str = ""
    bootstrap_force: bool = False

    # Networking / discovery ----------------------------------------------
    default_scan_ports: list[int] = DEFAULT_SCAN_PORTS
    scan_tcp_connect_timeout_s: float = 1.0
    scan_read_timeout_s: float = 2.0
    device_connect_timeout_s: float = 3.0
    device_read_timeout_s: float = 10.0
    device_retry_count: int = 2
    device_backoff_base_s: float = 0.5
    scan_max_workers: int = 96
    scan_retry_count: int = 0
    enable_icmp: bool = False
    enable_reverse_dns: bool = False
    scan_http_user_agent: str = "FreebuffAttendance/0.1"

    # Real-time / events ---------------------------------------------------
    realtime_poll_interval_s: int = 5

    # Job execution --------------------------------------------------------
    # "builtin" = in-process asyncio runner (single-node dev).
    # "celery"  = Redis-backed Celery worker pool (production).
    enable_scheduler: bool = True
    task_runner: str = "builtin"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # Rate limiting --------------------------------------------------------
    # "memory" = single-process (dev only).
    # "redis"  = shared via Redis (production, works across workers).
    rate_limit_enabled: bool = True
    rate_limit_backend: str = "memory"
    rate_limit_auth_per_minute: int = 30
    rate_limit_api_per_minute: int = 600

    # CORS -----------------------------------------------------------------
    cors_origins: str = "*"  # comma separated list; restrict in production

    # Storage usage thresholds (percent) -----------------------------------
    storage_warn_thresholds: list[int] = [70, 80, 90, 95]

    @field_validator("default_scan_ports", "storage_warn_thresholds", mode="before")
    @classmethod
    def _split_int_list(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.split(",") if x.strip()]
        return v

    @field_validator("secret_key", mode="before")
    @classmethod
    def _default_secret_key(cls, v: str, info: ValidationInfo) -> str:
        env = (info.data.get("environment") or "development").lower()
        if v and v not in _INSECURE_SECRET_KEYS:
            return v
        if env == "production":
            raise ValueError(
                "SECRET_KEY must be set to a long random value in production "
                "(e.g. `openssl rand -hex 32`). Refusing to start with a "
                "default/insecure secret."
            )
        # Dev only: generate an ephemeral key per process startup.
        logger.warning(
            "SECRET_KEY not set; generating ephemeral dev key. "
            "Set SECRET_KEY in .env for stable sessions."
        )
        return secrets.token_hex(32)

    @field_validator("credential_encryption_key", mode="before")
    @classmethod
    def _validate_cek(cls, v: str, info: ValidationInfo) -> str:
        env = (info.data.get("environment") or "development").lower()
        if v and v.strip():
            # Basic Fernet key sanity: accept anything that cryptography will
            # not reject (>=16 chars, base64-ish). Exact validation happens at
            # first use; here we only catch obviously-empty values.
            if len(v.strip()) < 8:
                raise ValueError(
                    "CREDENTIAL_ENCRYPTION_KEY looks too short; generate with "
                    "`from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())`."
                )
            return v.strip()
        if env == "production":
            raise ValueError(
                "CREDENTIAL_ENCRYPTION_KEY must be explicitly set in production. "
                "A persistent key is required to decrypt stored device credentials. "
                "Auto-generating a key and persisting it in the DB is NOT allowed "
                "in production because it makes credentials irrecoverable across "
                "redeploys / replicas."
            )
        return ""  # signals auto-generate + DB persistence (dev only)

    @field_validator("bootstrap_admin_password", mode="before")
    @classmethod
    def _default_admin_pwd(cls, v: str, info: ValidationInfo) -> str:
        return cls._default_bootstrap_pwd(v, info, _DEV_DEFAULT_ADMIN_PASSWORD, "admin")

    @field_validator("bootstrap_operator_password", mode="before")
    @classmethod
    def _default_operator_pwd(cls, v: str, info: ValidationInfo) -> str:
        return cls._default_bootstrap_pwd(
            v, info, _DEV_DEFAULT_OPERATOR_PASSWORD, "operator"
        )

    @field_validator("bootstrap_viewer_password", mode="before")
    @classmethod
    def _default_viewer_pwd(cls, v: str, info: ValidationInfo) -> str:
        return cls._default_bootstrap_pwd(v, info, _DEV_DEFAULT_VIEWER_PASSWORD, "viewer")

    @classmethod
    def _default_bootstrap_pwd(
        cls, v, info: ValidationInfo, dev_default: str, role: str
    ) -> str:
        env = (info.data.get("environment") or "development").lower()
        if v and v.strip() and v.strip().lower() not in _INSECURE_BOOTSTRAP_PASSWORDS:
            return v.strip()
        if env == "production":
            raise ValueError(
                f"BOOTSTRAP_{role.upper()}_PASSWORD must be set to a strong value "
                f"in production (default/well-known passwords are refused)."
            )
        logger.warning(
            "Using DEV-ONLY bootstrap password for %r: %r. "
            "Set BOOTSTRAP_%s_PASSWORD in .env.",
            role,
            dev_default,
            role.upper(),
        )
        return dev_default

    @field_validator("task_runner", mode="before")
    @classmethod
    def _coerce_task_runner(cls, v: str, info: ValidationInfo) -> str:
        env = (info.data.get("environment") or "development").lower()
        if not v:
            return "celery" if env == "production" else "builtin"
        if v not in ("builtin", "celery"):
            raise ValueError(f"task_runner must be 'builtin' or 'celery', got {v!r}")
        return v

    @field_validator("rate_limit_backend", mode="before")
    @classmethod
    def _coerce_rl_backend(cls, v: str, info: ValidationInfo) -> str:
        env = (info.data.get("environment") or "development").lower()
        if not v:
            return "redis" if env == "production" else "memory"
        if v not in ("memory", "redis"):
            raise ValueError(
                f"rate_limit_backend must be 'memory' or 'redis', got {v!r}"
            )
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _warn_cors(cls, v: str, info: ValidationInfo) -> str:
        env = (info.data.get("environment") or "development").lower()
        if v and v.strip() == "*" and env == "production":
            logger.warning(
                "CORS_ORIGINS is '*' in production - restrict this to your "
                "frontend origin for safety."
            )
        return v or "*"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        # Treat test/development/staging as non-production (dev conveniences
        # like ephemeral secret keys are allowed).
        return self.environment != "production"

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgres")

    def validate_startup(self) -> list[str]:
        """Run post-init startup validation. Returns a list of warnings."""
        warnings: list[str] = []
        if self.is_production:
            if self.database_url.startswith("sqlite"):
                raise ValueError(
                    "Production requires PostgreSQL (DATABASE_URL=postgresql+psycopg://...)"
                )
            if not self.redis_url or "localhost" in self.redis_url:
                warnings.append(
                    "REDIS_URL points at localhost; in multi-container production "
                    "this must point at the Redis service."
                )
            if self.task_runner != "celery":
                raise ValueError(
                    "Production requires task_runner=celery (builtin runner is "
                    "single-process only and unsafe for multiple replicas)."
                )
            if self.rate_limit_backend != "redis":
                raise ValueError(
                    "Production requires rate_limit_backend=redis (memory backend "
                    "is not shared across workers)."
                )
            if self.cors_origins.strip() == "*":
                warnings.append("CORS_ORIGINS='*' is not recommended in production.")
        if not self.secret_key or self.secret_key in _INSECURE_SECRET_KEYS:
            raise ValueError("SECRET_KEY must be set.")
        return warnings


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    warnings = s.validate_startup()
    for w in warnings:
        logger.warning("CONFIG: %s", w)
    return s


settings = get_settings()

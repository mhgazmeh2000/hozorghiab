"""Application configuration.

Everything is configurable through environment variables / .env.  Nothing
security- or network-relevant is hard-coded; the default scan networks are a
seed list stored in the database (SystemSetting/DeviceNetwork), so operators
may change them from the dashboard without touching code.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Freebuff Attendance Manager"
    app_version: str = "0.1.0"
    environment: str = "production"
    debug: bool = False
    api_prefix: str = "/api"

    # Database ------------------------------------------------------------
    # Default to SQLite for zero-friction local runs; set POSTGRES in prod.
    database_url: str = "sqlite+aiosqlite:///./attendance.db"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Security ------------------------------------------------------------
    secret_key: str = "CHANGE_ME__generate_with_openssl_rand_hex_32"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    jwt_issuer: str = "freebuff-attendance"
    # Fernet key used to encrypt device credentials (auto-generated if unset,
    # persisted in the DB settings on first boot).
    credential_encryption_key: str = ""
    # Master bootstrap passwords (only applied when the seed admin runs).
    bootstrap_admin_password: str = "ChangeMe-Admin-2026!"
    bootstrap_operator_password: str = "ChangeMe-Operator-2026!"
    bootstrap_viewer_password: str = "ChangeMe-Viewer-2026!"
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
    enable_icmp: bool = False  # raw ICMP usually requires privileges
    enable_reverse_dns: bool = False  # keep False where DNS is intercepted
    scan_http_user_agent: str = "FreebuffAttendance/0.1"

    # Real-time / events ---------------------------------------------------
    realtime_poll_interval_s: int = 5  # UI/fallback polling cadence

    # Job execution --------------------------------------------------------
    enable_scheduler: bool = True
    task_runner: str = "builtin"  # "builtin" | "celery" (documented choice)
    redis_url: str = "redis://redis:6379/0"

    # Rate limiting ---------------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_auth_per_minute: int = 30
    rate_limit_api_per_minute: int = 600

    # CORS ------------------------------------------------------------------
    cors_origins: str = "*"  # comma separated list

    @field_validator("default_scan_ports", mode="before")
    @classmethod
    def _split_ports(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.split(",") if x.strip()]
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgres")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

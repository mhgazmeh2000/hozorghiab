"""First-boot seeding: system users, default networks, settings."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DEFAULT_NETWORK_SEED, settings
from app.core.crypto import configure_key_provider, generate_key
from app.core.security import hash_password, verify_password
from app.models import DeviceNetwork, SystemSetting, SystemUser

logger = logging.getLogger("freebuff.seeder")


async def run_seeder(db: AsyncSession, force: bool = False) -> None:
    refresh_bootstrap = force or settings.bootstrap_force

    # 1) system roles
    bootstrap = [
        ("admin", settings.bootstrap_admin_password, "Administrator"),
        ("operator", settings.bootstrap_operator_password, "Operator"),
        ("viewer", settings.bootstrap_viewer_password, "Viewer"),
    ]
    for username, password, display in bootstrap:
        existing = await db.scalar(
            select(SystemUser).where(SystemUser.username == username)
        )
        if existing is None:
            db.add(
                SystemUser(
                    username=username,
                    display_name=display,
                    password_hash=hash_password(password),
                    role=username,
                    must_change_password=True,
                )
            )
            logger.info("seeded system user '%s'", username)
            continue

        needs_refresh = (
            refresh_bootstrap
            or existing.role != username
            or existing.display_name != display
            or not verify_password(password, existing.password_hash)
        )
        if needs_refresh:
            existing.password_hash = hash_password(password)
            existing.must_change_password = True
            existing.display_name = display
            existing.role = username
            existing.is_active = True
            logger.info("refreshed bootstrap user '%s'", username)

    # 2) default scan networks; preserve existing operator configuration
    configured_cidrs = set(
        (await db.scalars(select(DeviceNetwork.cidr))).all()
    )
    missing_networks = [
        cidr for cidr in DEFAULT_NETWORK_SEED if cidr not in configured_cidrs
    ]
    for cidr in missing_networks:
        db.add(
            DeviceNetwork(
                cidr=cidr,
                label=f"Default {cidr}",
                is_default=True,
                exclude_ips=[],
            )
        )
    if missing_networks:
        logger.info("seeded %d missing default scan networks", len(missing_networks))

    # 3) credential encryption key (single-node persistence)
    key_row = await db.scalar(
        select(SystemSetting).where(
            SystemSetting.key == "_credential_encryption_key"
        )
    )
    if key_row is None and not settings.credential_encryption_key:
        key = generate_key()
        key_row = SystemSetting(
            key="_credential_encryption_key", value=key,
            description="Auto-generated Fernet key for credential encryption",
        )
        db.add(key_row)
    await db.commit()
    if key_row is not None and key_row.value:
        configure_key_provider(lambda v: None)  # already persisted
        from app.core import crypto as _c

        _c._key = key_row.value.encode("utf-8")  # noqa: SLF001


async def bootstrap_credentials_check(db: AsyncSession) -> None:
    """Remind operators to rotate bootstrap passwords."""
    for username in ("admin", "operator", "viewer"):
        row = await db.scalar(select(SystemUser).where(SystemUser.username == username))
        if row is not None and row.must_change_password:
            return

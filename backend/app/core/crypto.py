"""Credential encryption using Fernet (AES-128-CBC + HMAC-SHA256).

Security model
--------------
* Production (ENVIRONMENT=production): CREDENTIAL_ENCRYPTION_KEY MUST be
  supplied via the environment. The server refuses to start otherwise. We
  never silently generate a key and persist it in the DB in production
  (that would break redeploys / replicas and is a security smell).
* Development (ENVIRONMENT=development): if CREDENTIAL_ENCRYPTION_KEY is
  not set, we auto-generate one on first boot and persist it in
  system_settings (key: _credential_encryption_key) so restarts keep working
  on a single node. A warning is logged.
"""
from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)

_key: bytes | None = None
_persisted_provider = None  # callable to persist a newly generated dev key


def configure_key_provider(persist: callable) -> None:
    global _persisted_provider
    _persisted_provider = persist


def _load_or_create_key() -> bytes:
    global _key
    if _key is not None:
        return _key
    if settings.credential_encryption_key:
        _key = settings.credential_encryption_key.encode("utf-8")
        return _key
    if settings.is_production:
        raise RuntimeError(
            "CREDENTIAL_ENCRYPTION_KEY is required in production. "
            "Generate one with: "
            "`from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())`"
        )
    # DEV-ONLY auto-generation + DB persistence.
    logger.warning(
        "CREDENTIAL_ENCRYPTION_KEY not set; generating an ephemeral "
        "development key and persisting it in system_settings. Set "
        "CREDENTIAL_ENCRYPTION_KEY explicitly for stable behavior."
    )
    _key = Fernet.generate_key()
    if _persisted_provider:
        try:
            _persisted_provider(_key.decode("utf-8"))
        except Exception:  # noqa: BLE001
            logger.exception("failed to persist auto-generated dev encryption key")
    return _key


def set_key_for_tests(key: str) -> None:
    global _key
    _key = key.encode("utf-8")


def encrypt_secret(plaintext: str) -> str:
    return Fernet(_load_or_create_key()).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return (
            Fernet(_load_or_create_key()).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        )
    except (InvalidToken, ValueError):
        raise ValueError("Unable to decrypt credential (key mismatch or corrupted data)")


def generate_key() -> str:
    return Fernet.generate_key().decode("utf-8")


def mask(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "*" * (len(value) - 2) + value[-1]

"""Credential encryption using Fernet (AES-128-CBC + HMAC-SHA256).

When no CREDENTIAL_ENCRYPTION_KEY is configured the server generates one on
first boot and persists it in system_settings (key: _credential_encryption_key)
so restarts keep working on a single node. Multi-instance/production setups
should set CREDENTIAL_ENCRYPTION_KEY explicitly in the environment.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_key: bytes | None = None
_persisted_provider = None  # callable -> persist a newly generated key (set at boot)


def configure_key_provider(persist: callable) -> None:
    global _persisted_provider
    _persisted_provider = persist


def _load_or_create_key() -> bytes:
    global _key
    if _key is not None:
        return _key
    if settings.credential_encryption_key:
        key = settings.credential_encryption_key.encode("utf-8")
    else:
        key = Fernet.generate_key()
        if _persisted_provider:
            try:
                _persisted_provider(key.decode("utf-8"))
            except Exception:
                pass  # survive if persistence fails; key lives for this process
    _key = key
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

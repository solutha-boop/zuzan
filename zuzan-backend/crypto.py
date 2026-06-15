"""
ZuZan Field Encryption
Encrypts sensitive database fields (bank account numbers, branch codes)
using AES-128 via Fernet.

Set FIELD_ENCRYPTION_KEY in Render environment variables.
Generate a key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("zuzan.crypto")

_key_raw = os.environ.get("FIELD_ENCRYPTION_KEY", "").strip()
_fernet = None

if _key_raw:
    try:
        _fernet = Fernet(_key_raw.encode())
        logger.info("Field encryption ENABLED — bank fields will be encrypted at rest")
    except Exception as e:
        logger.error(f"FIELD_ENCRYPTION_KEY is invalid: {e}. Bank fields stored in plaintext.")
else:
    logger.warning("FIELD_ENCRYPTION_KEY not set — bank fields stored in plaintext (set this in Render env vars)")


def encrypt_field(value: str | None) -> str | None:
    """Encrypt a sensitive string field before saving to DB."""
    if value is None or not _fernet:
        return value
    if _is_fernet_token(value):
        return value  # Already encrypted — don't double-encrypt
    try:
        return _fernet.encrypt(value.encode()).decode()
    except Exception as e:
        logger.error(f"encrypt_field failed: {e}")
        return value


def decrypt_field(value: str | None) -> str | None:
    """Decrypt a sensitive string field when reading from DB."""
    if value is None or not _fernet:
        return value
    try:
        return _fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        return value  # Not encrypted (legacy plaintext) — return as-is
    except Exception as e:
        logger.error(f"decrypt_field failed: {e}")
        return value


def _is_fernet_token(value: str) -> bool:
    """Quick check: Fernet tokens are base64url and start with 'gAAA'."""
    return isinstance(value, str) and value.startswith("gAAA")


def encryption_enabled() -> bool:
    return _fernet is not None

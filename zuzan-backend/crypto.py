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

# Production must never silently store sensitive fields in plaintext (security audit 2026-11-23, crypto fail-open).
# On Render (RENDER env var set) a missing or invalid key now stops the app from starting, unless the operator
# explicitly opts out with ZUZAN_ALLOW_PLAINTEXT_FIELDS=1 (an emergency switch, logged at CRITICAL level).
if os.environ.get("RENDER") and _fernet is None:
    if os.environ.get("ZUZAN_ALLOW_PLAINTEXT_FIELDS") == "1":
        logger.critical("SECURITY: FIELD_ENCRYPTION_KEY missing/invalid - sensitive fields are being stored in PLAINTEXT "
                        "because ZUZAN_ALLOW_PLAINTEXT_FIELDS=1. Set a valid key and remove that override.")
    else:
        raise RuntimeError("FIELD_ENCRYPTION_KEY is missing or invalid. Set a valid Fernet key in Render env vars "
                           "(or, in an emergency only, set ZUZAN_ALLOW_PLAINTEXT_FIELDS=1).")


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


# ── Blind index + masking helpers (security audit 2026-11-23) ────────────────────────────────────────
import hmac as _hmac, hashlib as _hashlib


def _blind_key() -> bytes:
    k = os.environ.get("FIELD_ENCRYPTION_KEY", "").strip() or "zuzan-blind-index-v1"
    return _hashlib.sha256(("blind-index|" + k).encode()).digest()


def blind_index(value) -> str | None:
    """Deterministic keyed hash (HMAC-SHA256) of a sensitive value, so an encrypted field can still be matched
    exactly (e.g. find an employee by SA ID number) without storing it in plaintext. Spaces/dashes are ignored."""
    if value is None:
        return None
    norm = "".join(ch for ch in str(value) if ch.isalnum()).upper()
    if not norm:
        return None
    return _hmac.new(_blind_key(), norm.encode(), _hashlib.sha256).hexdigest()


MASK_PREFIX = "••••"


def mask_tail(value, keep: int = 4) -> str:
    """'1234567890' -> '••••7890'. Empty in, empty out."""
    if not value:
        return ""
    v = str(value).strip()
    return MASK_PREFIX + v[-keep:] if len(v) > keep else MASK_PREFIX + v[-1:] if v else ""


def is_masked(value) -> bool:
    """True for a value produced by mask_tail - an edit form sent the mask back, so the stored value must be kept."""
    return isinstance(value, str) and value.startswith(MASK_PREFIX)


try:
    from sqlalchemy.types import TypeDecorator, String as _SAString

    class EncryptedString(TypeDecorator):
        """A String column that is transparently encrypted at rest with encrypt_field/decrypt_field.
        Legacy plaintext values still read correctly (decrypt_field returns them unchanged)."""
        impl = _SAString
        cache_ok = True

        def process_bind_param(self, value, dialect):
            if value is None or value == "":
                return value
            return encrypt_field(str(value))

        def process_result_value(self, value, dialect):
            return decrypt_field(value) if value else value
except ImportError:          # pragma: no cover
    EncryptedString = None

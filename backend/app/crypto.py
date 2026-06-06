"""Application-level encryption for secrets at rest.

Used for the TOTP MFA secret (`users.mfa_secret`), which would
otherwise sit in the DB as plaintext base32 — anyone with a DB dump
could clone a user's authenticator. We wrap it in Fernet (AES-128-CBC
+ HMAC-SHA256, authenticated) so a leaked dump is useless without the
application key.

Key resolution (first match wins):
  1. MFA_ENCRYPTION_KEY — a urlsafe-base64 32-byte Fernet key. Set this
     in production and rotate it independently of everything else.
  2. Derived from JWT_SECRET via SHA-256 — so encryption is always on
     with zero extra ops. The tradeoff: rotating JWT_SECRET also
     invalidates stored MFA secrets (users must re-enrol). Acceptable
     for a fallback; set a dedicated key to decouple them.

The `EncryptedSecret` SQLAlchemy type makes this transparent at the
column level: plaintext in Python, ciphertext in the DB. Reads of
legacy plaintext rows (pre-encryption) fall through unchanged, so the
rollout needs no data migration — rows re-encrypt on their next write.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


def _fernet() -> Fernet:
    """Build the Fernet cipher from config. Not cached so tests that
    swap the key (via get_settings.cache_clear) take effect; MFA writes
    are rare enough that per-call construction is irrelevant."""
    settings = get_settings()
    key = settings.mfa_encryption_key.strip()
    if key:
        return Fernet(key.encode())
    # Fallback: derive a stable 32-byte key from the JWT secret. SHA-256
    # yields exactly 32 bytes; Fernet wants it urlsafe-base64 encoded.
    digest = hashlib.sha256(settings.jwt_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


class EncryptedSecret(TypeDecorator):
    """String column transparently encrypted at rest with Fernet.

    Backward compatible: a value that fails to decrypt is assumed to be
    a legacy plaintext row and returned as-is, so existing MFA secrets
    keep working until the next write re-encrypts them. The DB-side
    width must hold the Fernet token (~140 chars for a 32-byte secret),
    not the plaintext — see the migration that widened the column."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        return encrypt_secret(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return None
        try:
            return decrypt_secret(value)
        except InvalidToken:
            return value

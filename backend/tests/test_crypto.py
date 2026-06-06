"""MFA-secret encryption at rest (§192).

The TOTP secret is wrapped in Fernet via the `EncryptedSecret` column
type so a leaked DB dump can't be used to clone authenticators. These
tests cover the round-trip, the ciphertext-not-plaintext guarantee, and
the legacy-plaintext passthrough that makes the rollout need no data
migration.
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from app.config import get_settings
from app.crypto import EncryptedSecret, decrypt_secret, encrypt_secret


def test_round_trip():
    secret = "JBSWY3DPEHPK3PXP"
    assert decrypt_secret(encrypt_secret(secret)) == secret


def test_ciphertext_is_not_plaintext():
    secret = "JBSWY3DPEHPK3PXP"
    token = encrypt_secret(secret)
    assert secret not in token
    # Fernet tokens are non-deterministic (random IV) — two encryptions
    # of the same plaintext differ, but both decrypt back.
    assert encrypt_secret(secret) != token


def test_dedicated_key_takes_precedence(monkeypatch):
    key = Fernet.generate_key().decode()
    settings = get_settings()
    monkeypatch.setattr(settings, "mfa_encryption_key", key)
    token = encrypt_secret("topsecret")
    # The same explicit key decrypts it; the derived-from-JWT fallback
    # would not.
    assert Fernet(key.encode()).decrypt(token.encode()).decode() == "topsecret"


def test_column_bind_and_result_round_trip():
    col = EncryptedSecret()
    stored = col.process_bind_param("JBSWY3DPEHPK3PXP", dialect=None)
    assert stored is not None and "JBSWY3DPEHPK3PXP" not in stored
    assert col.process_result_value(stored, dialect=None) == "JBSWY3DPEHPK3PXP"


def test_column_none_passthrough():
    col = EncryptedSecret()
    assert col.process_bind_param(None, dialect=None) is None
    assert col.process_result_value(None, dialect=None) is None


def test_legacy_plaintext_is_read_as_is():
    """A row written before encryption holds raw base32, which is not a
    valid Fernet token — the type returns it unchanged so existing MFA
    keeps working until the next write re-encrypts it."""
    col = EncryptedSecret()
    assert col.process_result_value("JBSWY3DPEHPK3PXP", dialect=None) == "JBSWY3DPEHPK3PXP"

"""TOTP MFA service.

Two pieces:
  1. TOTP: 6-digit time-based codes from a base32 secret bound to the
     user's authenticator app (Google Authenticator, 1Password, Authy,
     Bitwarden, etc).
  2. Backup codes: ten plaintext-once recovery codes the user prints
     and stashes — bcrypt-hashed at rest, single-use, for "phone died"
     scenarios.

The TOTP secret is generated on /mfa/setup and stored on the user row,
encrypted at rest by the `EncryptedSecret` column type (Fernet — see
app/crypto.py), so a leaked DB dump can't be used to clone an
authenticator. It is NOT considered active until /mfa/enable validates
the first code from the user.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

import pyotp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MfaBackupCode
from app.security import hash_password, verify_password

# pyotp's default is ±1 30-second window (so 90s tolerance). Standard
# tradeoff for clock skew vs. attack window. Don't widen unless you
# really need the slack.
TOTP_VALID_WINDOW = 1

# Ten codes is the industry default (Google, GitHub, Gitlab all do 10).
# Enough for a phone-lost emergency without being so many they leak.
BACKUP_CODE_COUNT = 10

# 8-char alphanumeric → ~41 bits of entropy per code, plenty for a
# one-shot recovery code. Hyphenated for readability.
BACKUP_CODE_BYTES = 5  # secrets.token_hex returns 2*BYTES chars

# Issuer string shown in the user's authenticator app next to the
# 6-digit code. Branding for legitimacy + so the user can tell our
# token apart from Gmail, GitHub, etc in their app.
TOTP_ISSUER = "CRM Gallo"


def generate_secret() -> str:
    """160-bit base32 — matches RFC 6238 recommendation and what every
    auth-app QR scanner expects."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, account_label: str) -> str:
    """The `otpauth://totp/...` URI that the user's authenticator app
    decodes from the QR code. `account_label` is what the user sees
    in their app — we use their email so multi-account users can tell
    sessions apart."""
    return pyotp.TOTP(secret).provisioning_uri(name=account_label, issuer_name=TOTP_ISSUER)


def verify_totp(secret: str, code: str) -> bool:
    """Validate a 6-digit code against the secret with the standard
    ±1-step skew tolerance. Empty / malformed codes return False
    rather than raising — call sites just need a boolean."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=TOTP_VALID_WINDOW)
    except Exception:
        return False


# -------- Backup codes --------


def _new_backup_code() -> str:
    """4-4 hex pattern, e.g. `a1b2-c3d4`. Readable and easy to type."""
    raw = secrets.token_hex(BACKUP_CODE_BYTES)
    return f"{raw[:4]}-{raw[4:]}"


async def generate_backup_codes(
    db: AsyncSession, user_id, count: int = BACKUP_CODE_COUNT
) -> list[str]:
    """Create N fresh backup codes for the user, persist their hashes,
    and return the PLAINTEXT codes (the caller MUST surface them to the
    user immediately and warn they won't be shown again).

    Any pre-existing unused codes are dropped first — re-generating
    invalidates the old set. This prevents a stockpile from outliving
    the user's intent to rotate."""
    # Wipe any previous unused codes for this user.
    existing = (
        (
            await db.execute(
                select(MfaBackupCode).where(
                    MfaBackupCode.user_id == user_id,
                    MfaBackupCode.used_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for c in existing:
        await db.delete(c)

    plaintexts: list[str] = []
    for _ in range(count):
        code = _new_backup_code()
        plaintexts.append(code)
        db.add(MfaBackupCode(user_id=user_id, code_hash=hash_password(code)))
    return plaintexts


async def consume_backup_code(db: AsyncSession, user_id, code: str) -> bool:
    """Try to spend a backup code. On match: mark used_at + return
    True. On miss: return False. Bcrypt comparison runs against EVERY
    unused code for this user (constant-time across the candidate
    set) — `secrets.compare_digest` doesn't apply since we need to
    compare against a hash."""
    code = (code or "").strip().lower()
    candidates = (
        (
            await db.execute(
                select(MfaBackupCode).where(
                    MfaBackupCode.user_id == user_id,
                    MfaBackupCode.used_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for candidate in candidates:
        if verify_password(code, candidate.code_hash):
            candidate.used_at = datetime.now(UTC)
            return True
    return False


async def count_unused_backup_codes(db: AsyncSession, user_id) -> int:
    """For the /mfa/status surface — tells the user how many codes
    they have left so they know when to regenerate."""
    rows = (
        (
            await db.execute(
                select(MfaBackupCode).where(
                    MfaBackupCode.user_id == user_id,
                    MfaBackupCode.used_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return len(rows)

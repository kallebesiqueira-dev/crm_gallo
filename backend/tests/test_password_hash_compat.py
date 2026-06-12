"""Password-hash compatibility: argon2 is the writer, but users who
enrolled before the 2026-06-11 argon2 migration still carry bcrypt
hashes ($2a$/$2b$) — `verify_password` must keep accepting those until
every hash has rotated. This is the regression net for bcrypt major
bumps (e.g. Dependabot #90): the fallback path had no coverage, so a
green suite said nothing about legacy logins surviving the upgrade.
"""

from __future__ import annotations

import bcrypt
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Organization
from app.security import hash_password, verify_password
from tests.conftest import PYTEST_PREFIX, CsrfAwareClient

LEGACY_PASSWORD = "LegacyBcryptPass2026!"


def _bcrypt_hash(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def test_argon2_roundtrip():
    hashed = hash_password("SomePass2026!")
    assert hashed.startswith("$argon2")
    assert verify_password("SomePass2026!", hashed)
    assert not verify_password("WrongPass2026!", hashed)


def test_legacy_bcrypt_verifies_and_rejects():
    hashed = _bcrypt_hash(LEGACY_PASSWORD)
    assert hashed.startswith(("$2b$", "$2a$"))
    assert verify_password(LEGACY_PASSWORD, hashed)
    assert not verify_password("WrongPass2026!", hashed)


@pytest.fixture
def legacy_user(db: Session, test_org: Organization) -> str:
    """A user seeded exactly as the pre-argon2 era left them: bcrypt
    hash in `hashed_password`."""
    email = f"{PYTEST_PREFIX}legacy-bcrypt@example.com"
    db.execute(
        text(
            "INSERT INTO users (id, email, full_name, hashed_password, role, locale,"
            " is_active, email_verified, last_active_org_id, mfa_enabled)"
            " VALUES (gen_random_uuid(), :email, 'Legacy User', :pwd, 'sales_agent', 'en',"
            " true, true, :org, false)"
        ),
        {"email": email, "pwd": _bcrypt_hash(LEGACY_PASSWORD), "org": str(test_org.id)},
    )
    db.execute(
        text(
            "INSERT INTO org_memberships (user_id, organization_id, role)"
            " SELECT id, :org, 'sales_agent' FROM users WHERE email = :email"
        ),
        {"org": str(test_org.id), "email": email},
    )
    db.commit()
    return email


def test_legacy_bcrypt_user_can_log_in(client: CsrfAwareClient, legacy_user: str):
    """End-to-end: the login endpoint accepts a legacy bcrypt account."""
    r = client.post(
        "/api/auth/login",
        data={"username": legacy_user, "password": LEGACY_PASSWORD},
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/api/auth/login",
        data={"username": legacy_user, "password": "WrongPass2026!"},
    )
    assert r.status_code == 401

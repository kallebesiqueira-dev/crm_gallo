"""MFA-mandatory-for-privileged policy (§P1 191).

When `mfa_required_for_privileged` is on, any user holding an admin/manager
role in any org must enroll in TOTP before touching tenant data:

  * /login starts a full session but returns `mfa_setup_required` so the
    client routes into forced enrollment.
  * every tenant-data endpoint (choke point: get_current_org_id) returns
    403 `mfa_enrollment_required` until they enable MFA.
  * the policy is a no-op when off, and never touches non-privileged users.

The flag lives on the cached Settings singleton; deps.py and auth.py both
hold a reference to that same object, so monkeypatching the attribute flips
enforcement everywhere at once.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User

from .conftest import CsrfAwareClient

_settings = get_settings()


@pytest.fixture
def mfa_policy_on(monkeypatch):
    """Turn the privileged-MFA policy on for one test and restore after."""
    monkeypatch.setattr(_settings, "mfa_required_for_privileged", True)
    yield


def _login(client: CsrfAwareClient, email: str):
    return client.post("/api/auth/login", data={"username": email, "password": "PytestPass2026!"})


def test_policy_off_is_noop(client: CsrfAwareClient, admin_user: User):
    """With the flag off, a privileged un-enrolled user logs in normally
    and reaches tenant data."""
    r = _login(client, admin_user.email)
    assert r.status_code == 200
    body = r.json()
    assert "mfa_setup_required" not in body
    assert body["user"]["email"] == admin_user.email
    assert client.get("/api/leads").status_code == 200


def test_privileged_login_signals_setup_required(
    client: CsrfAwareClient, admin_user: User, mfa_policy_on
):
    """Flag on + admin without MFA: login succeeds (cookies set) but the
    body tells the client to go enroll."""
    r = _login(client, admin_user.email)
    assert r.status_code == 200
    body = r.json()
    assert body["mfa_setup_required"] is True
    assert body["user"]["email"] == admin_user.email
    # A session WAS started — the access cookie is present.
    assert "access_token" in r.cookies or "access_token" in client.cookies


def test_privileged_blocked_on_data_until_enrolled(
    client: CsrfAwareClient, admin_user: User, mfa_policy_on
):
    """Flag on: the privileged un-enrolled user is bounced off every
    tenant-data endpoint with the machine-readable 403."""
    _login(client, admin_user.email)
    r = client.get("/api/leads")
    assert r.status_code == 403
    assert r.json()["detail"] == "mfa_enrollment_required"


def test_gate_clears_once_enrolled(
    client: CsrfAwareClient, admin_user: User, db: Session, mfa_policy_on
):
    """Same session: blocked before enrollment, clear after. We flip
    mfa_enabled on the existing session (instead of re-logging-in) because
    a re-login with MFA on would demand a TOTP challenge we can't satisfy
    in-test — this models "user finishes /mfa/enable, data unblocks"."""
    _login(client, admin_user.email)
    assert client.get("/api/leads").status_code == 403

    admin_user.mfa_enabled = True
    db.commit()

    assert client.get("/api/leads").status_code == 200


def test_non_privileged_user_unaffected(client: CsrfAwareClient, other_user: User, mfa_policy_on):
    """A sales_agent (non-privileged) is never forced to enroll, even with
    the policy on."""
    r = _login(client, other_user.email)
    assert r.status_code == 200
    assert "mfa_setup_required" not in r.json()
    assert client.get("/api/leads").status_code == 200


def test_mfa_endpoints_reachable_while_blocked(
    client: CsrfAwareClient, admin_user: User, mfa_policy_on
):
    """The whole point of starting a session: the enrollment + status
    endpoints (get_current_user only) stay open so the user can actually
    complete setup while every data route is 403."""
    _login(client, admin_user.email)
    assert client.get("/api/auth/mfa/status").status_code == 200
    assert client.post("/api/auth/mfa/setup").status_code == 200


def test_setup_enable_round_trips_through_encrypted_secret(
    client: CsrfAwareClient, admin_user: User, db: Session
):
    """End-to-end proof of §192: the secret returned by /setup is stored
    ENCRYPTED at rest, yet /enable validates a real TOTP code computed
    from it — so the decrypt-on-read path produces the exact secret the
    user's authenticator holds. Also asserts the DB column does NOT hold
    the plaintext base32."""
    import pyotp
    from sqlalchemy import text

    _login(client, admin_user.email)
    secret = client.post("/api/auth/mfa/setup").json()["secret"]

    # The raw secret must NOT be what's sitting in the column.
    stored = db.execute(
        text("SELECT mfa_secret FROM users WHERE id = :id"), {"id": str(admin_user.id)}
    ).scalar_one()
    assert stored != secret
    assert secret not in stored

    code = pyotp.TOTP(secret).now()
    r = client.post("/api/auth/mfa/enable", json={"code": code})
    assert r.status_code == 200, r.text
    assert len(r.json()["backup_codes"]) == 10

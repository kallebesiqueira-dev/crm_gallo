"""Refresh token rotation + reuse detection.

Coverage:
  * /refresh rotates the refresh_token cookie on every successful call
  * The old refresh token stops working after rotation
  * Reuse of an already-rotated token triggers `refresh.reuse_detected`
    and revokes ALL of the user's sessions (steal signal)
  * /refresh with no cookie still returns 401 plain (no false alarm)

The rotation is implemented in `app/redis_client.rotate_refresh_token`
and detected via `check_rotated_token`. These tests exercise the
HTTP surface that ties them together.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import User


def _login(client, email: str, password: str) -> dict:
    r = client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.cookies.jar


def test_refresh_rotates_cookie(client, admin_user: User):
    # Login → cookies set
    r = client.post(
        "/api/auth/login",
        data={"username": admin_user.email, "password": "PytestPass2026!"},
    )
    assert r.status_code == 200
    original = client.cookies.get("refresh_token")
    assert original is not None

    # Call /refresh → expect a NEW refresh cookie
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200, r.text
    rotated = client.cookies.get("refresh_token")
    assert rotated is not None
    assert rotated != original


def test_old_refresh_token_invalidated_after_rotation(client, admin_user: User):
    # Login + capture the original refresh token
    client.post(
        "/api/auth/login",
        data={"username": admin_user.email, "password": "PytestPass2026!"},
    ).raise_for_status()
    original = client.cookies.get("refresh_token")

    # First refresh — rotates.
    client.post("/api/auth/refresh").raise_for_status()
    rotated = client.cookies.get("refresh_token")
    assert rotated != original

    # Manually plant the OLD token back in and call refresh — must be
    # detected as REUSE → 401 + all sessions revoked.
    # Force-replace the cookie. The server emits Set-Cookie WITHOUT a
    # Domain attribute, so http.cookiejar stores it host-only under the
    # key `testserver.local` (it appends `.local` to dotless hosts) —
    # NOT `testserver`. Delete by name across all domains to be robust,
    # then re-plant under the same `.local` key the jar actually uses so
    # the OLD value is what gets sent.
    client.cookies.delete("refresh_token")
    client.cookies.set("refresh_token", original, domain="testserver.local", path="/api/auth")
    r = client.post("/api/auth/refresh")
    assert r.status_code == 401, r.text
    assert "reuse" in r.json()["detail"].lower()


def test_reuse_detection_revokes_all_user_sessions(client, admin_user: User):
    """The reuse path must wipe EVERY session for the user — even
    sessions that have nothing to do with the leaked token. After
    /refresh trips the alarm, even the NEW (rotated) refresh token
    must not work for further /refresh calls."""
    client.post(
        "/api/auth/login",
        data={"username": admin_user.email, "password": "PytestPass2026!"},
    ).raise_for_status()
    original = client.cookies.get("refresh_token")

    client.post("/api/auth/refresh").raise_for_status()
    rotated = client.cookies.get("refresh_token")

    # Plant the OLD token → tripwire. (Jar stores host-only cookies for
    # the dotless `testserver` host under the `testserver.local` key.)
    client.cookies.delete("refresh_token")
    client.cookies.set("refresh_token", original, domain="testserver.local", path="/api/auth")
    client.post("/api/auth/refresh")  # 401 alarm

    # Now restore the legitimate rotated token. It MUST no longer
    # work, because reuse detection revoked every session.
    client.cookies.delete("refresh_token")
    client.cookies.set("refresh_token", rotated, domain="testserver.local", path="/api/auth")
    r = client.post("/api/auth/refresh")
    assert r.status_code == 401, r.text


def test_refresh_rejects_deactivated_user(client, admin_user: User, db: Session):
    """A user disabled out-of-band (is_active=False) must be rejected at
    /refresh — not handed a fresh 15-min access token that only the next
    protected call would catch. The live refresh token is also burned, so
    a follow-up /refresh can't keep minting credentials either."""
    client.post(
        "/api/auth/login",
        data={"username": admin_user.email, "password": "PytestPass2026!"},
    ).raise_for_status()
    assert client.cookies.get("refresh_token") is not None

    # Admin flips the account off out-of-band.
    db.execute(
        text("UPDATE users SET is_active = false WHERE id = :id"), {"id": str(admin_user.id)}
    )
    db.commit()

    r = client.post("/api/auth/refresh")
    assert r.status_code == 401, r.text
    assert "inactive" in r.json()["detail"].lower()

    # Sessions were revoked: a second attempt is still 401 (no new token).
    r2 = client.post("/api/auth/refresh")
    assert r2.status_code == 401, r2.text


def test_refresh_without_cookie_returns_plain_401(client):
    """Missing cookie is the boring 'expired or never logged in' path —
    must NOT be confused with the reuse alarm."""
    r = client.post("/api/auth/refresh")
    assert r.status_code == 401
    detail = r.json()["detail"].lower()
    assert "no refresh" in detail
    assert "reuse" not in detail

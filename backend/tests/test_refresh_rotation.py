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
    # Force-replace the cookie. TestClient's cookie jar can keep
    # multiple entries with the same name when set() is called naively;
    # delete first to be sure the OLD value is the one sent.
    client.cookies.delete("refresh_token", domain="testserver", path="/api/auth")
    client.cookies.set(
        "refresh_token", original, domain="testserver", path="/api/auth"
    )
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

    # Plant the OLD token → tripwire.
    client.cookies.delete("refresh_token", domain="testserver", path="/api/auth")
    client.cookies.set("refresh_token", original, domain="testserver", path="/api/auth")
    client.post("/api/auth/refresh")  # 401 alarm

    # Now restore the legitimate rotated token. It MUST no longer
    # work, because reuse detection revoked every session.
    client.cookies.delete("refresh_token", domain="testserver", path="/api/auth")
    client.cookies.set("refresh_token", rotated, domain="testserver", path="/api/auth")
    r = client.post("/api/auth/refresh")
    assert r.status_code == 401, r.text


def test_refresh_without_cookie_returns_plain_401(client):
    """Missing cookie is the boring 'expired or never logged in' path —
    must NOT be confused with the reuse alarm."""
    r = client.post("/api/auth/refresh")
    assert r.status_code == 401
    detail = r.json()["detail"].lower()
    assert "no refresh" in detail
    assert "reuse" not in detail

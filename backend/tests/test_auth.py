"""Auth happy + sad paths.

What we're proving:
  * `/login` returns 200 + sets all three cookies (access, refresh, csrf).
  * Same response shape for unknown email and bad password — no
    enumeration.
  * `/me` rejects unauthenticated calls (401) and accepts the cookie
    (200) without any Authorization header.
  * Logout clears the cookies and the next protected call 401s.
  * CSRF middleware rejects mutating calls without the header.
"""

from __future__ import annotations

from app.models import User
from tests.conftest import TEST_PASSWORD, CsrfAwareClient


def test_login_sets_three_cookies(client: CsrfAwareClient, admin_user: User):
    r = client.post(
        "/api/auth/login",
        data={"username": admin_user.email, "password": TEST_PASSWORD},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == admin_user.email
    assert body["token"]["access_token"]
    # All three cookies set: csrf is JS-readable, access + refresh httpOnly.
    cookies = {c.name for c in client.cookies.jar}
    assert "access_token" in cookies
    assert "refresh_token" in cookies
    assert "csrf_token" in cookies


def test_login_unknown_email_401(client: CsrfAwareClient):
    r = client.post(
        "/api/auth/login",
        data={"username": "nobody@example.com", "password": TEST_PASSWORD},
    )
    assert r.status_code == 401
    # No cookies issued on failure.
    assert "access_token" not in {c.name for c in client.cookies.jar}


def test_login_wrong_password_401(client: CsrfAwareClient, admin_user: User):
    r = client.post(
        "/api/auth/login",
        data={"username": admin_user.email, "password": "totally-wrong-pwd"},
    )
    assert r.status_code == 401


def test_me_requires_auth(client: CsrfAwareClient):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_with_cookie(admin_client: CsrfAwareClient, admin_user: User):
    r = admin_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == admin_user.email


def test_display_currency_defaults_to_eur(admin_client: CsrfAwareClient):
    assert admin_client.get("/api/auth/me").json()["display_currency"] == "EUR"


def test_update_display_currency(admin_client: CsrfAwareClient):
    r = admin_client.patch("/api/auth/me", json={"display_currency": "CHF"})
    assert r.status_code == 200, r.text
    assert r.json()["display_currency"] == "CHF"
    # Persisted across reads.
    assert admin_client.get("/api/auth/me").json()["display_currency"] == "CHF"


def test_update_display_currency_rejects_unknown(admin_client: CsrfAwareClient):
    r = admin_client.patch("/api/auth/me", json={"display_currency": "XXX"})
    assert r.status_code == 422


def test_logout_clears_cookies(admin_client: CsrfAwareClient):
    r = admin_client.post("/api/auth/logout")
    assert r.status_code == 204
    # Subsequent /me must fail — refresh was revoked AND access cookie cleared.
    r2 = admin_client.get("/api/auth/me")
    assert r2.status_code == 401


def test_csrf_required_on_mutating(client: CsrfAwareClient, admin_user: User):
    """A POST that carries the auth cookie but NO `X-CSRF-Token`
    header must 403. Make the request via the underlying
    TestClient.request method while explicitly stripping the
    CSRF header that the wrapper would otherwise inject."""
    client.post(
        "/api/auth/login",
        data={"username": admin_user.email, "password": TEST_PASSWORD},
    )
    # Bypass the wrapper by calling TestClient's parent request method
    # directly with an empty header dict — no CSRF gets added.
    from starlette.testclient import TestClient as _BaseTC

    r = _BaseTC.request(
        client,
        "POST",
        "/api/leads",
        json={"first_name": "X", "last_name": "Y", "stage": "new"},
        headers={},
    )
    assert r.status_code == 403
    assert "csrf" in r.json()["detail"].lower()

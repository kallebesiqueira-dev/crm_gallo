"""Cookie + CSRF helpers for httpOnly-cookie auth.

The shape of the deal:
  - `access_token` cookie carries the JWT. httpOnly so XSS can't read
    it. Sent automatically by the browser on same-origin requests
    (and on cross-origin requests that opt in with `credentials:
    'include'` + CORS `allow_credentials=true`).
  - `csrf_token` cookie carries a random nonce. NOT httpOnly so the
    SPA can read it from `document.cookie` and echo it into the
    `X-CSRF-Token` request header. Backend verifies the header matches
    the cookie on every mutating request — the "double-submit cookie"
    pattern. A foreign site can trigger the browser to send the
    cookie automatically but cannot read its value to forge the
    matching header, so the verification fails for CSRF attempts.

In production: `Secure=True` + `SameSite=Lax`. In dev (no HTTPS):
`Secure=False` + `SameSite=Lax`. We never use `SameSite=None` (which
would require Secure anyway and is only needed for true cross-site
embedding, which we don't do).
"""

from __future__ import annotations

import secrets

from fastapi import Response

from app.config import get_settings

ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"
REFRESH_TOKEN_PATH = "/api/auth"
CSRF_TOKEN_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"

# Refresh cookie is path-scoped to `/api/auth` so the browser sends
# it to /refresh AND /logout (so logout can read the value and revoke
# the Redis entry). It is NOT sent to /api/leads, /api/customers,
# etc — minimal exposure surface while keeping logout-revocation
# possible. Strictly /api/auth/refresh would block logout-revoke
# entirely; sending on every request (path=/) over-exposes a
# 30-day credential.

# Methods that mutate state — CSRF is enforced on these when an auth
# cookie is present. GET/HEAD/OPTIONS are safe per the HTTP spec
# (clients shouldn't trigger side effects on these).
CSRF_PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def issue_csrf_token() -> str:
    """Generate a fresh CSRF nonce. URL-safe so it round-trips through
    cookies and headers without any encoding gymnastics."""
    return secrets.token_urlsafe(32)


def set_auth_cookies(
    response: Response,
    access_token: str,
    csrf_token: str,
    refresh_token: str | None = None,
) -> None:
    """Attach the auth cookies to the outgoing response.

    Called from /login, /register, /register-with-invite — anywhere we
    mint a new session — and from /refresh, which rotates just the
    access cookie (refresh_token is None on rotate so the long-lived
    cookie keeps its original Set-Cookie from login).

    Cookies:
      * `access_token`  — JWT, short TTL (15 min default), path=/,
                          httpOnly so JS can't read it.
      * `csrf_token`    — random nonce, TTL = refresh TTL so the SPA
                          can always echo it back when calling /refresh
                          to mint a new access cookie. JS-readable.
      * `refresh_token` — opaque random, TTL 30 days, path scoped to
                          /api/auth/refresh so it's never sent to data
                          endpoints. httpOnly.
    """
    settings = get_settings()
    access_max_age = settings.jwt_access_token_expire_minutes * 60
    refresh_max_age = settings.refresh_token_expire_days * 86400
    secure = settings.is_production
    # Cross-subdomain: when the SPA (app.gallo-crm.com) and API
    # (api.gallo-crm.com) differ, scope the cookies to the shared parent so
    # the SPA can read the csrf cookie and both subdomains receive the auth
    # cookie. Empty COOKIE_DOMAIN => host-only (same-origin / dev default).
    domain = settings.cookie_domain or None

    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        max_age=access_max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        domain=domain,
    )
    # CSRF cookie outlives the access cookie — the SPA still needs to
    # send X-CSRF-Token when calling /refresh after the access JWT has
    # already expired. If both expired together the SPA would have to
    # rely on cookies-disappeared signals; longer csrf cookie keeps the
    # refresh path callable.
    response.set_cookie(
        key=CSRF_TOKEN_COOKIE,
        value=csrf_token,
        max_age=refresh_max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
        domain=domain,
    )
    if refresh_token is not None:
        response.set_cookie(
            key=REFRESH_TOKEN_COOKIE,
            value=refresh_token,
            max_age=refresh_max_age,
            httponly=True,
            secure=secure,
            samesite="lax",
            path=REFRESH_TOKEN_PATH,
            domain=domain,
        )


def clear_auth_cookies(response: Response) -> None:
    """Wipe all three cookies on logout. We pass the same path /
    secure / samesite that we set them with so the browser actually
    matches and deletes (mismatched attributes leave the cookie alive
    silently). The refresh cookie needs its narrower path to delete."""
    settings = get_settings()
    secure = settings.is_production
    domain = settings.cookie_domain or None
    for key in (ACCESS_TOKEN_COOKIE, CSRF_TOKEN_COOKIE):
        response.delete_cookie(
            key=key,
            path="/",
            secure=secure,
            samesite="lax",
            httponly=(key == ACCESS_TOKEN_COOKIE),
            domain=domain,
        )
    response.delete_cookie(
        key=REFRESH_TOKEN_COOKIE,
        path=REFRESH_TOKEN_PATH,
        secure=secure,
        samesite="lax",
        httponly=True,
        domain=domain,
    )

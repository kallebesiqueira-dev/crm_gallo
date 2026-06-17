"""Social login (Microsoft Entra ID + Google) — OpenID Connect authorization-code flow.

Matches an EXISTING user by their verified provider email (no oauth-account
table ⇒ no DB migration). Each provider is disabled (404) until its CLIENT_ID +
CLIENT_SECRET are set, so a fresh clone runs with social login off and the
buttons hidden. CSRF is a short-lived, per-provider `state` cookie checked in
constant time. The email is read from the id_token (returned back-channel over
TLS from the token endpoint, so trusted without re-verifying its signature).
Sign-up via a social provider (provisioning a new org) is a follow-up — today
it logs in known accounts and bounces unknown emails back to the login page
with a hint.
"""

import secrets
import urllib.parse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from jose import jwt
from jose.exceptions import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import analytics
from app.api.auth import _start_session
from app.audit import record_audit
from app.config import get_settings
from app.database import get_db
from app.logging_setup import get_logger
from app.models import User

router = APIRouter(prefix="/api/auth/oauth", tags=["oauth"])

settings = get_settings()
log = get_logger(__name__)

_SCOPE = "openid email profile"
_MS_STATE_COOKIE = "ms_oauth_state"
_GOOGLE_STATE_COOKIE = "google_oauth_state"
# Google's OIDC endpoints (well-known, static values).
_GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def _ms_enabled() -> bool:
    return bool(settings.microsoft_client_id and settings.microsoft_client_secret)


def _google_enabled() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def _ms_authority() -> str:
    return f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}/oauth2/v2.0"


def _redirect_uri(request: Request, provider: str) -> str:
    # Must EXACTLY match the redirect URI registered on the provider's app.
    base = (settings.oauth_redirect_base or str(request.base_url)).rstrip("/")
    return f"{base}/api/auth/oauth/{provider}/callback"


@router.get("/providers")
async def providers() -> dict[str, bool]:
    """Public — which social-login providers are wired (drives the login UI)."""
    return {"microsoft": _ms_enabled(), "google": _google_enabled()}


async def _complete_login(
    request: Request,
    db: AsyncSession,
    email: str,
    *,
    provider: str,
    state_cookie: str,
) -> RedirectResponse:
    """Shared callback tail: match the verified `email` to an existing active
    user and start a session, else bounce to /login with a hint. `provider`
    labels the audit + analytics records; `state_cookie` is cleared on success.
    """
    frontend = settings.frontend_base_url.rstrip("/")
    if not email:
        return RedirectResponse(f"{frontend}/login?oauth=no_email")

    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None or not user.is_active:
        # No matching (active) account — bounce to login with a hint to sign up.
        return RedirectResponse(f"{frontend}/login?oauth=no_account")

    await record_audit(
        db, actor=user, action=f"user.login_oauth_{provider}", entity_type="user", entity_id=user.id
    )
    await db.commit()
    redirect = RedirectResponse(f"{frontend}/{user.locale}/dashboard")
    # _start_session sets the auth + csrf + refresh cookies on the redirect, so
    # the SPA reads the csrf cookie and treats the user as logged in.
    await _start_session(request, redirect, user)
    redirect.delete_cookie(state_cookie, path="/")
    analytics.capture(str(user.id), "user_logged_in", {"method": f"{provider}_oauth"})
    return redirect


# ---------------------------------------------------------------------------
# Microsoft (Entra ID)
# ---------------------------------------------------------------------------
@router.get("/microsoft/start")
async def microsoft_start(request: Request) -> RedirectResponse:
    if not _ms_enabled():
        raise HTTPException(status_code=404, detail="Microsoft login is not configured")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.microsoft_client_id,
        "response_type": "code",
        "redirect_uri": _redirect_uri(request, "microsoft"),
        "response_mode": "query",
        "scope": _SCOPE,
        "state": state,
    }
    resp = RedirectResponse(f"{_ms_authority()}/authorize?{urllib.parse.urlencode(params)}")
    resp.set_cookie(
        _MS_STATE_COOKIE, state, max_age=600, httponly=True, secure=True, samesite="lax", path="/"
    )
    return resp


@router.get("/microsoft/callback")
async def microsoft_callback(
    request: Request,
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not _ms_enabled():
        raise HTTPException(status_code=404, detail="Microsoft login is not configured")
    cookie_state = request.cookies.get(_MS_STATE_COOKIE)
    if not code or not state or not cookie_state or not secrets.compare_digest(state, cookie_state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    redirect_uri = _redirect_uri(request, "microsoft")
    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(
            f"{_ms_authority()}/token",
            data={
                "client_id": settings.microsoft_client_id,
                "client_secret": settings.microsoft_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": _SCOPE,
            },
        )
    if token_resp.status_code != 200:
        log.warning(
            "oauth.token_exchange_failed", provider="microsoft", status=token_resp.status_code
        )
        raise HTTPException(status_code=400, detail="Token exchange failed")

    # Read the email from the id_token, NOT from /userinfo: Microsoft's
    # graph.microsoft.com/oidc/userinfo returns a minimal claim set that often
    # omits the email and never carries preferred_username, whereas the id_token
    # has both. It arrived back-channel over TLS from the token endpoint, so it's
    # trusted without re-verifying its signature.
    id_token = token_resp.json().get("id_token")
    try:
        claims = jwt.get_unverified_claims(id_token) if id_token else {}
    except JWTError:
        log.warning("oauth.id_token_decode_failed", provider="microsoft")
        claims = {}
    raw_email = claims.get("email") or claims.get("preferred_username") or claims.get("upn")
    email = (raw_email or "").lower().strip()
    return await _complete_login(
        request, db, email, provider="microsoft", state_cookie=_MS_STATE_COOKIE
    )


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------
@router.get("/google/start")
async def google_start(request: Request) -> RedirectResponse:
    if not _google_enabled():
        raise HTTPException(status_code=404, detail="Google login is not configured")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.google_client_id,
        "response_type": "code",
        "redirect_uri": _redirect_uri(request, "google"),
        "scope": _SCOPE,
        "state": state,
        # online: we don't need a refresh token (we run our own session).
        # select_account: always show the chooser instead of silently reusing
        # whichever Google session the browser already has.
        "access_type": "online",
        "prompt": "select_account",
    }
    resp = RedirectResponse(f"{_GOOGLE_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}")
    resp.set_cookie(
        _GOOGLE_STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return resp


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not _google_enabled():
        raise HTTPException(status_code=404, detail="Google login is not configured")
    cookie_state = request.cookies.get(_GOOGLE_STATE_COOKIE)
    if not code or not state or not cookie_state or not secrets.compare_digest(state, cookie_state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    redirect_uri = _redirect_uri(request, "google")
    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(
            _GOOGLE_TOKEN_ENDPOINT,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if token_resp.status_code != 200:
        log.warning("oauth.token_exchange_failed", provider="google", status=token_resp.status_code)
        raise HTTPException(status_code=400, detail="Token exchange failed")

    # The id_token carries the email + an email_verified flag. Only trust a
    # verified address, so a Google account with an unconfirmed email can never
    # match (and take over) a CRM login.
    id_token = token_resp.json().get("id_token")
    try:
        claims = jwt.get_unverified_claims(id_token) if id_token else {}
    except JWTError:
        log.warning("oauth.id_token_decode_failed", provider="google")
        claims = {}
    email = ""
    if claims.get("email_verified") in (True, "true"):
        email = (claims.get("email") or "").lower().strip()
    return await _complete_login(
        request, db, email, provider="google", state_cookie=_GOOGLE_STATE_COOKIE
    )

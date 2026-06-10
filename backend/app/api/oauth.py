"""Microsoft (Entra ID) social login — OpenID Connect authorization-code flow.

Matches an EXISTING user by their verified Microsoft email (no oauth-account
table ⇒ no DB migration). Disabled (404) until MICROSOFT_OAUTH_CLIENT_ID +
MICROSOFT_OAUTH_CLIENT_SECRET are set. CSRF is a short-lived state cookie checked
in constant time. The id/access token is exchanged back-channel over TLS, so the
profile from `/userinfo` is trusted without local JWT verification. Sign-up via
Microsoft (provisioning a new org) is a follow-up — today it logs in known
accounts and bounces unknown emails back to the login page with a hint.
"""

import secrets
import urllib.parse
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
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

_STATE_COOKIE = "ms_oauth_state"
_SCOPE = "openid email profile"


def _enabled() -> bool:
    return bool(settings.microsoft_client_id and settings.microsoft_client_secret)


def _authority() -> str:
    return f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}/oauth2/v2.0"


def _redirect_uri(request: Request) -> str:
    # Must EXACTLY match the redirect URI registered on the Azure app.
    base = (settings.oauth_redirect_base or str(request.base_url)).rstrip("/")
    return f"{base}/api/auth/oauth/microsoft/callback"


@router.get("/providers")
async def providers() -> dict[str, bool]:
    """Public — which social-login providers are wired (drives the login UI)."""
    return {"microsoft": _enabled()}


@router.get("/microsoft/start")
async def start(request: Request) -> RedirectResponse:
    if not _enabled():
        raise HTTPException(status_code=404, detail="Microsoft login is not configured")
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.microsoft_client_id,
        "response_type": "code",
        "redirect_uri": _redirect_uri(request),
        "response_mode": "query",
        "scope": _SCOPE,
        "state": state,
    }
    resp = RedirectResponse(f"{_authority()}/authorize?{urllib.parse.urlencode(params)}")
    resp.set_cookie(
        _STATE_COOKIE, state, max_age=600, httponly=True, secure=True, samesite="lax", path="/"
    )
    return resp


@router.get("/microsoft/callback")
async def callback(
    request: Request,
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    if not _enabled():
        raise HTTPException(status_code=404, detail="Microsoft login is not configured")
    cookie_state = request.cookies.get(_STATE_COOKIE)
    if not code or not state or not cookie_state or not secrets.compare_digest(state, cookie_state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    redirect_uri = _redirect_uri(request)
    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(
            f"{_authority()}/token",
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
            log.warning("oauth.token_exchange_failed", status=token_resp.status_code)
            raise HTTPException(status_code=400, detail="Token exchange failed")
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="No access token from Microsoft")
        userinfo_resp = await client.get(
            "https://graph.microsoft.com/oidc/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Could not read Microsoft profile")
        info: dict[str, Any] = userinfo_resp.json()

    email = (info.get("email") or info.get("preferred_username") or "").lower().strip()
    frontend = settings.frontend_base_url.rstrip("/")
    if not email:
        return RedirectResponse(f"{frontend}/login?oauth=no_email")

    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None or not user.is_active:
        # No matching (active) account — bounce to login with a hint to sign up.
        return RedirectResponse(f"{frontend}/login?oauth=no_account")

    await record_audit(
        db, actor=user, action="user.login_oauth_microsoft", entity_type="user", entity_id=user.id
    )
    await db.commit()
    redirect = RedirectResponse(f"{frontend}/{user.locale}/dashboard")
    # _start_session sets the auth + csrf + refresh cookies on the redirect, so
    # the SPA reads the csrf cookie and treats the user as logged in.
    await _start_session(request, redirect, user)
    redirect.delete_cookie(_STATE_COOKIE, path="/")
    analytics.capture(str(user.id), "user_logged_in", {"method": "microsoft_oauth"})
    return redirect

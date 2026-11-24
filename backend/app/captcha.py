"""Cloudflare Turnstile verification — anti-bot for public surfaces.

Gated by ``TURNSTILE_SECRET_KEY``: when it is empty, verification is a no-op
(returns ``True``) so the app runs without CAPTCHA configured — the honeypot
and per-IP rate limits still apply. Set the secret to enforce Turnstile on
registration and public Web-to-Lead submissions; the matching *site* key is
served to the browser via ``NEXT_PUBLIC_TURNSTILE_SITE_KEY``.
"""

from __future__ import annotations

import httpx

from app.config import get_settings

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(
    token: str | None,
    remote_ip: str | None = None,
    *,
    missing_ok: bool = False,
) -> bool:
    """Return True if the Turnstile token is valid (or if CAPTCHA is disabled).

    Disabled (no secret) → always True. Configured → an INVALID token fails
    CLOSED. A missing token fails CLOSED unless ``missing_ok`` (login): the
    widget can time out or fail to load, and that path must not trap the user.
    A network error or a siteverify call that exceeds 4s fails OPEN so an
    outage never blocks the form. The per-IP rate limit stays as a second layer.
    """
    secret = get_settings().turnstile_secret_key
    if not secret:
        return True
    if not token:
        return missing_ok
    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(_VERIFY_URL, data=payload)
        return bool(resp.json().get("success"))
    except httpx.RequestError:
        # Connectivity fault or timeout reaching Cloudflare → fail OPEN.
        return True
    except Exception:
        # Any other error — non-2xx, unparseable/unexpected body — is a FAILED
        # verification (fail CLOSED), not a free pass.
        return False

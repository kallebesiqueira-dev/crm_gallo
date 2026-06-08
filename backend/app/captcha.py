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


async def verify_turnstile(token: str | None, remote_ip: str | None = None) -> bool:
    """Return True if the Turnstile token is valid (or if CAPTCHA is disabled).

    Disabled (no secret) → always True. Configured → a missing token is
    rejected; a verified token passes. On a network error reaching Cloudflare
    we fail OPEN (allow) so a Cloudflare outage never blocks legitimate
    sign-ups — only the explicit invalid-token path fails closed.
    """
    secret = get_settings().turnstile_secret_key
    if not secret:
        return True
    if not token:
        return False
    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(_VERIFY_URL, data=payload)
        return bool(resp.json().get("success"))
    except Exception:
        return True

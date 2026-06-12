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

    Disabled (no secret) → always True. Configured → a MISSING token fails
    OPEN (the widget likely couldn't run for a legitimate visitor; the per-IP
    rate limit still guards), a verified token passes, and a present-but-
    INVALID token fails closed (the bot-tampering signal). A network error
    reaching Cloudflare also fails OPEN so an outage never blocks sign-ups.
    """
    secret = get_settings().turnstile_secret_key
    if not secret:
        return True
    if not token:
        # No token usually means the widget couldn't run for a legitimate
        # visitor (e.g. the site key's hostname list doesn't cover this
        # deployment, or the challenge script was blocked) — which would
        # otherwise block ALL sign-ups. Fail OPEN and lean on the per-IP rate
        # limit; a present-but-INVALID token below still fails closed.
        return True
    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(_VERIFY_URL, data=payload)
        return bool(resp.json().get("success"))
    except Exception:
        return True

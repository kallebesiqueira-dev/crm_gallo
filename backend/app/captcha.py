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

    Disabled (no secret) → always True. Configured → a MISSING or INVALID
    token fails CLOSED (Turnstile is live, so a real visitor's widget yields a
    token; an absent/invalid one signals a bot), while a verified token passes.
    A network error reaching Cloudflare fails OPEN so an outage never blocks
    sign-ups; the per-IP rate limit is a second layer throughout.
    """
    secret = get_settings().turnstile_secret_key
    if not secret:
        return True
    if not token:
        # Fail CLOSED on a missing token: Turnstile is configured and live (the
        # site key is served to the browser), so a legitimate visitor's widget
        # produces a token. An absent token signals a bot or a tampered/blocked
        # client — reject it. The per-IP rate limit remains a second layer.
        return False
    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(_VERIFY_URL, data=payload)
        return bool(resp.json().get("success"))
    except httpx.RequestError:
        # Connectivity fault reaching Cloudflare → fail OPEN so an outage never
        # blocks sign-ups (the per-IP rate limit stays as a second layer).
        return True
    except Exception:
        # Any other error — non-2xx, unparseable/unexpected body — is a FAILED
        # verification (fail CLOSED), not a free pass.
        return False

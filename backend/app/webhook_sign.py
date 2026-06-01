"""Webhook HMAC signing — outgoing deliveries.

Header format (Stripe-style):
    X-CRM-Signature: t=<unix_ts>,v1=<sha256_hex>

The receiver re-computes `HMAC_SHA256(secret, f"{t}.{body}")` and
compares with `secrets.compare_digest`. Timestamp is included in the
signed payload so a replay >5 min old can be rejected by the
receiver (we don't enforce this ourselves — sender-side, we just
sign with the current timestamp).

`generate_secret()` produces a 64-hex (32 random bytes) token. Shown
ONCE on endpoint create; never round-tripped on subsequent reads.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time


SIGNATURE_HEADER = "X-CRM-Signature"


def generate_secret() -> str:
    """64-hex (32 random bytes). Cryptographically strong via
    `secrets.token_hex`, suitable for HMAC keys."""
    return secrets.token_hex(32)


def sign_payload(secret: str, body: bytes, *, timestamp: int | None = None) -> str:
    """Build the value for `X-CRM-Signature`.

    `body` is the EXACT bytes that go on the wire — sign-then-send,
    not the other way. `timestamp` defaults to the current unix
    second; pass it explicitly only in tests for determinism.
    """
    ts = timestamp if timestamp is not None else int(time.time())
    signed = f"{ts}.".encode() + body
    mac = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify_signature(
    secret: str,
    body: bytes,
    header_value: str,
    *,
    max_age_seconds: int = 300,
    now: int | None = None,
) -> bool:
    """Constant-time signature check. Returns True only if:
      * the header parses
      * `t` is within `max_age_seconds` of `now`
      * `v1` matches the recomputed HMAC

    Provided for symmetry / unit testing; production receivers
    typically live OUTSIDE this codebase, but they can copy this
    function. Also used by the test sink during smoke.
    """
    try:
        parts = dict(p.split("=", 1) for p in header_value.split(","))
        ts = int(parts["t"])
        provided = parts["v1"]
    except (ValueError, KeyError):
        return False

    current = now if now is not None else int(time.time())
    if abs(current - ts) > max_age_seconds:
        return False

    signed = f"{ts}.".encode() + body
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)

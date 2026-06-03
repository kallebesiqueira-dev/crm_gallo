"""Public-API key token helpers (ADR-016 public-API slice).

Pure functions — no DB, no Redis, no network. The token mint/parse/hash
logic lives here so the management endpoint (which creates keys) and the
bearer dependency (which validates them) share ONE definition of the
token shape and can never drift.

Token shape: ``crmk_{org_hex}_{secret}``
  * ``crmk_``    — a fixed, greppable prefix so a leaked key is
                   recognisable in logs/secret-scanners (mirrors
                   GitHub's ``ghp_`` / Stripe's ``sk_``).
  * ``{org_hex}`` — the owning org's UUID as 32 hex chars. NOT a secret;
                    it lets the bearer path recover the tenant, set the
                    ``app.current_org_id`` GUC, and look the key up under
                    RLS before any session exists (same trick the e-sign
                    ``sign_token`` uses).
  * ``{secret}``  — 32 random bytes, urlsafe-base64. The only secret part.

At rest we store ONLY ``sha256(full_token)`` (hex) — never the plaintext.
The plaintext is shown once on create and is otherwise unrecoverable.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid

from app.models import ApiKeyScope

TOKEN_PREFIX = "crmk_"
_SECRET_BYTES = 32


def mint_token(org_id: uuid.UUID) -> tuple[str, str, str]:
    """Mint a fresh token for ``org_id``.

    Returns ``(full_token, hashed_key, display_prefix)``:
      * ``full_token``   — the plaintext, shown to the admin exactly once.
      * ``hashed_key``   — sha256 hex, the only thing persisted.
      * ``display_prefix`` — the non-secret label for the UI list.
    """
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    full = f"{TOKEN_PREFIX}{org_id.hex}_{secret}"
    return full, hash_token(full), build_display_prefix(full)


def hash_token(token: str) -> str:
    """sha256 hex of the full token. Deterministic, so a presented token
    can be matched against the stored hash with a single indexed lookup."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_display_prefix(token: str) -> str:
    """A non-secret label like ``crmk_a1b2c3…wxyz`` for listing keys.

    Shows the fixed prefix + a slice of the (non-secret) org hex and the
    last 4 chars of the secret. 4 chars of a 43-char secret is far too
    little to brute-force, and matches how Stripe/GitHub render a key's
    tail so a human can tell two keys apart."""
    return f"{token[:12]}…{token[-4:]}"


def parse_org_id(token: str) -> uuid.UUID | None:
    """Recover the embedded org UUID from a token, or None if the token
    is malformed. Used by the bearer path to set the RLS GUC before the
    key lookup. Never trusts the result as authn — it only narrows which
    tenant's keys we search; the sha256 match is the actual credential
    check, and RLS makes a cross-org hash match return zero rows."""
    if not token.startswith(TOKEN_PREFIX):
        return None
    rest = token[len(TOKEN_PREFIX) :]
    org_hex, sep, secret = rest.partition("_")
    if not sep or not secret:
        return None
    try:
        return uuid.UUID(hex=org_hex)
    except ValueError:
        return None


def encode_scopes(scopes: list[ApiKeyScope]) -> str:
    """JSON-encode a scope list for the ``api_keys.scopes`` text column.
    De-dupes and stores stable values."""
    seen: list[str] = []
    for s in scopes:
        if s.value not in seen:
            seen.append(s.value)
    return json.dumps(seen)


def decode_scopes(raw: str) -> set[ApiKeyScope]:
    """Parse the stored ``scopes`` column into a set of ApiKeyScope.
    Unknown/garbage values are dropped (forward-compat: a future scope
    written by a newer node is simply ignored by an older one)."""
    try:
        values = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return set()
    out: set[ApiKeyScope] = set()
    for v in values if isinstance(values, list) else []:
        try:
            out.add(ApiKeyScope(v))
        except ValueError:
            continue
    return out


# Idempotent, safe verbs need only `read`; anything that can mutate
# state needs `write`.
_READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def required_scope_for_method(method: str) -> ApiKeyScope:
    return ApiKeyScope.read if method.upper() in _READ_METHODS else ApiKeyScope.write

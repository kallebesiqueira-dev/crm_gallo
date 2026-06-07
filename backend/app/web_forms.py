"""Web-to-Lead public form token helpers.

Pure functions — no DB, no network. Shared by the management endpoint
(which mints tokens) and the public submit endpoint (which resolves them),
so the token shape can never drift between the two.

Token shape: ``crmf_{org_hex}_{secret}``
  * ``crmf_``     — fixed, greppable prefix ("crm form"). Distinct from the
                    API-key ``crmk_`` so a leaked value is identifiable.
  * ``{org_hex}`` — owning org UUID as 32 hex chars. NOT a secret; it lets
                    the public path recover the tenant, set the
                    ``app.current_org_id`` GUC, and look the form up UNDER
                    RLS before any session exists (same trick as ``crmk_``
                    API keys and the e-sign ``sign_token``).
  * ``{secret}``  — 32 random urlsafe bytes — enough entropy that the token
                    is unguessable.

Unlike an API key, this token is a PUBLIC identifier: it ships inside the
embed snippet on the customer's website, so it is stored in plaintext
(unique-indexed) and shown in the UI as often as needed. The org embedding
is what makes the RLS lookup possible; the secret keeps it unguessable.
"""

from __future__ import annotations

import secrets
import uuid

TOKEN_PREFIX = "crmf_"
_SECRET_BYTES = 32


def mint_token(org_id: uuid.UUID) -> str:
    """Mint a fresh public form token embedding ``org_id``."""
    return f"{TOKEN_PREFIX}{org_id.hex}_{secrets.token_urlsafe(_SECRET_BYTES)}"


def parse_org_id(token: str) -> uuid.UUID | None:
    """Recover the embedded org UUID, or None if the token is malformed.

    Used by the public submit path to set the RLS GUC before the form
    lookup. Never trusted as authorisation on its own — it only narrows
    which tenant's forms we search; the plaintext-token match is the real
    check, and RLS makes a cross-org match return zero rows.
    """
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

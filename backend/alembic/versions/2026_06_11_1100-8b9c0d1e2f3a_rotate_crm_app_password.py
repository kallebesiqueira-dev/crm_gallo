"""Rotate crm_app role password to match APP_DATABASE_URL

Revision ID: 8b9c0d1e2f3a
Revises: 7a8b9c0d1e2f
Create Date: 2026-06-11 11:00:00.000000

Ensures the crm_app Postgres role's password always matches the
APP_DATABASE_URL environment variable so that the runtime credentials
are reproducible from config rather than from deploy history.

Run this migration (as the `crm` superuser) after rotating
APP_DATABASE_URL. downgrade() is a no-op — there is no safe way
to restore a previous password.
"""

import os
from urllib.parse import unquote, urlparse

from alembic import op

revision = "8b9c0d1e2f3a"
down_revision = "7a8b9c0d1e2f"
branch_labels = None
depends_on = None


def _extract_password(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        return unquote(parsed.password) if parsed.password else None
    except Exception:
        return None


def upgrade() -> None:
    url = os.environ.get("APP_DATABASE_URL", "")
    pwd = _extract_password(url)
    if not pwd:
        # APP_DATABASE_URL not set or has no password component —
        # skip silently rather than locking the role with an empty password.
        return
    # ALTER ROLE does not support bind parameters in standard SQL, so we
    # inline the value. Single-quote escaping (doubling) is the correct
    # Postgres defence against injection in string literals.
    safe_pwd = pwd.replace("'", "''")
    op.execute(f"ALTER ROLE crm_app PASSWORD '{safe_pwd}'")


def downgrade() -> None:
    pass  # Previous password unknown — cannot restore safely.

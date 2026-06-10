"""rotate crm_app role password from APP_DATABASE_URL env

The initial crm_app role was created in f5fde59e0dc8 with a hard-coded
password ('crm_app_dev_2026') that was committed to git history. This
migration reads the password from the APP_DATABASE_URL environment
variable at migration time and issues ALTER ROLE to synchronise the
database with whatever the operator has configured, removing the
dependency on the baked-in value.

Safe to run multiple times (idempotent: ALTER ROLE is a no-op if the
password is already correct). No table changes — pure DDL on the role.

Revision ID: f0a1b2c3d4e5
Revises: e4f5a6b7c8d9
Create Date: 2026-06-10 18:00:00.000000+00:00

"""

from __future__ import annotations

import os
from typing import Sequence, Union
from urllib.parse import urlparse

from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _extract_password(url: str) -> str | None:
    parsed = urlparse(url)
    return parsed.password or None


def upgrade() -> None:
    app_db_url = os.environ.get("APP_DATABASE_URL", "")
    password = _extract_password(app_db_url)
    if not password or password == "CHANGE_ME":
        raise RuntimeError(
            "APP_DATABASE_URL is not set or still uses the placeholder password. "
            "Set a strong password in your environment before running this migration."
        )
    # Text() is intentionally not used here — role names and passwords
    # cannot be parameterised in PostgreSQL ALTER ROLE. The password is
    # read from a trusted environment variable controlled by the operator,
    # not from user input.
    escaped = password.replace("'", "''")
    op.execute(f"ALTER ROLE crm_app PASSWORD '{escaped}'")


def downgrade() -> None:
    # Intentionally a no-op: we cannot restore the previous password
    # safely. To roll back, set APP_DATABASE_URL to the old value and
    # re-run the upgrade() direction.
    pass

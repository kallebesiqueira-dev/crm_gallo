"""rotate crm_app password — source from env, retire the leaked literal

The original ``create_crm_app_runtime_role`` migration (f5fde59e0dc8)
hard-coded the runtime role's password, which leaked into the public repo.
That migration now sources the password from the environment instead; this
follow-up rotates the password on databases that were created BEFORE the
de-hard-coding, so every environment converges on the env-supplied secret.

The password comes from ``APP_DATABASE_URL`` (the same URL the app connects
with), or ``CRM_APP_DB_PASSWORD`` as an explicit override — never a baked-in
default. Operators MUST also rotate the secret out of band (the old value is
in git history): set a fresh ``APP_DATABASE_URL`` password per environment,
then deploy so this migration ALTERs the role to it.

Revision ID: 0862af48f9ca
Revises: b4c5d6e7f8a9
Create Date: 2026-06-08 10:07:43.905709+00:00

"""

import os
from typing import Sequence, Union
from urllib.parse import unquote, urlparse

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0862af48f9ca"
down_revision: Union[str, None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _crm_app_password() -> str:
    """Runtime ``crm_app`` password, read from the environment — never hard-coded.

    Parsed from ``APP_DATABASE_URL`` (``postgresql+asyncpg://crm_app:<pw>@host/db``)
    or ``CRM_APP_DB_PASSWORD``. Raising on absence is deliberate: we never fall
    back to a baked-in default secret.
    """
    url = os.environ.get("APP_DATABASE_URL") or ""
    pw = None
    if "://" in url:
        scheme, rest = url.split("://", 1)
        scheme = scheme.split("+", 1)[0]  # drop the +asyncpg driver suffix
        parsed = urlparse(f"{scheme}://{rest}")
        pw = unquote(parsed.password) if parsed.password else None
    pw = pw or os.environ.get("CRM_APP_DB_PASSWORD")
    if not pw:
        raise RuntimeError(
            "crm_app role password unavailable: set APP_DATABASE_URL "
            "(postgresql+asyncpg://crm_app:<password>@host/db) or CRM_APP_DB_PASSWORD."
        )
    return pw


def upgrade() -> None:
    # Single-quote-escape for the SQL string literal. The value is
    # operator-supplied via env, not user input.
    pw = _crm_app_password().replace("'", "''")
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_app') THEN
            ALTER ROLE crm_app WITH PASSWORD '{pw}';
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # Intentionally a no-op: we will not restore a known-leaked password.
    # The role keeps whatever the environment currently supplies.
    pass

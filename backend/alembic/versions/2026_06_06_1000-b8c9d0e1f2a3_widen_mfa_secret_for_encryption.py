"""widen mfa_secret for at-rest encryption

`users.mfa_secret` now stores a Fernet token instead of the raw base32
secret (see app/crypto.py — encryption at rest so a DB dump can't clone
authenticators). The token of a 32-byte secret is ~140 chars, which no
longer fits the original String(64). Widen to String(255).

No data transform: existing plaintext rows stay plaintext and are read
back via the type's legacy-passthrough, then re-encrypted on their next
write. Pure widening is safe and reversible on Postgres.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-06 10:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "mfa_secret",
        existing_type=sa.String(length=64),
        type_=sa.String(length=255),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Narrowing back to 64 would truncate any encrypted tokens; callers
    # must clear/re-enrol MFA before downgrading. We still declare it so
    # the chain is reversible structurally.
    op.alter_column(
        "users",
        "mfa_secret",
        existing_type=sa.String(length=255),
        type_=sa.String(length=64),
        existing_nullable=True,
    )

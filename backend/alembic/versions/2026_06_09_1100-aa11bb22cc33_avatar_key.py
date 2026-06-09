"""avatar_key on users / customers / companies (profile photos)

Adds a nullable `avatar_key` (S3 object key) to users, customers and companies.
Purely additive — no RLS change (the columns ride existing tenant tables / the
users table, which already carry the right policies / grants).

Revision ID: aa11bb22cc33
Revises: d7e8f9a0b1c2
Create Date: 2026-06-09 11:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa11bb22cc33"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("users", "customers", "companies")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("avatar_key", sa.String(length=512), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "avatar_key")

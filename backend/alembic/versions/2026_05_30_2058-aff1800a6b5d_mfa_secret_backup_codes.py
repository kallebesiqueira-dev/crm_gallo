"""mfa_secret_backup_codes

Adds the persistence for the TOTP MFA flow:
  * `users.mfa_secret` (base32, nullable) — bound when /mfa/setup
    runs; meaningful only when `users.mfa_enabled` is True.
  * `users.mfa_enrolled_at` (timestamptz, nullable) — set on /enable.
  * `mfa_backup_codes` table — bcrypt-hashed single-use recovery
    codes, ten per enable.

The composite tenant indices that autogenerate keeps trying to drop
(`sa.text("…DESC")` not representable in the model diff) are KEPT —
see the comment in the `drop_user_billing_columns` migration for the
rationale.

Revision ID: aff1800a6b5d
Revises: f403f55cf0b4
Create Date: 2026-05-30 20:58:18.878037+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aff1800a6b5d"
down_revision: Union[str, None] = "f403f55cf0b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mfa_backup_codes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_mfa_backup_codes_user_id"),
        "mfa_backup_codes",
        ["user_id"],
        unique=False,
    )
    op.add_column(
        "users", sa.Column("mfa_secret", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("mfa_enrolled_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Grant CRUD on the new table to the runtime role so the app can
    # touch it. Default privileges from the crm_app role migration
    # should also cover this (FOR ROLE crm), but explicit GRANT here
    # is idempotent and removes any ordering doubt.
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "ON mfa_backup_codes TO crm_app;"
    )


def downgrade() -> None:
    op.drop_column("users", "mfa_enrolled_at")
    op.drop_column("users", "mfa_secret")
    op.drop_index(op.f("ix_mfa_backup_codes_user_id"), table_name="mfa_backup_codes")
    op.drop_table("mfa_backup_codes")

"""email verification

Adds the `users.email_verified` flag and the `email_verification_tokens`
table for the self-registration email-confirmation flow.

`email_verified` ships with a `server_default=true` so EXISTING rows are
grandfathered as verified (we don't want to lock out anyone who signed up
before this feature). The default is then dropped so NEW rows fall back to
the app/model default (False) — fresh self-signups must confirm their email.
The first user (install founder) and invited users are set verified
explicitly in the application layer.

The `email_verification_tokens` table mirrors `password_reset_tokens`
exactly (same columns, same indexes, same FK + cascade).

Revision ID: a7b8c9d0e1f2
Revises: c1d2e3f4a5b6
Create Date: 2026-06-05 12:45:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default=true grandfathers existing users as verified; then we
    # drop the default so new rows rely on the app/model default (False).
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.alter_column("users", "email_verified", server_default=None)

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
        op.f("ix_email_verification_tokens_token"),
        "email_verification_tokens",
        ["token"],
        unique=True,
    )
    op.create_index(
        op.f("ix_email_verification_tokens_user_id"),
        "email_verification_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_email_verification_tokens_user_id"),
        table_name="email_verification_tokens",
    )
    op.drop_index(
        op.f("ix_email_verification_tokens_token"),
        table_name="email_verification_tokens",
    )
    op.drop_table("email_verification_tokens")
    op.drop_column("users", "email_verified")

"""notes — per-user markdown notes on Lead/Customer/Deal

Soft-deletable (`deleted_at` index auto-created from the
SoftDeleteMixin). Indexed for the "list notes for this entity,
newest first" query that the detail page runs every visit.

Composite tenant indices that autogenerate keeps trying to drop
(sa.text("…DESC") / lower() not representable) are KEPT — see
`drop_user_billing_columns` for the rationale.

Revision ID: 31c9a3466f9c
Revises: dd5318916104
Create Date: 2026-06-01 13:14:31.267153+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "31c9a3466f9c"
down_revision: Union[str, None] = "dd5318916104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("author_user_id", sa.UUID(), nullable=True),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_notes_deleted_at"), "notes", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_notes_organization_id"),
        "notes",
        ["organization_id"],
        unique=False,
    )
    # "Notes for this entity, newest first" — same pattern as the
    # activities timeline index.
    op.execute(
        """
        CREATE INDEX idx_notes_entity_created
          ON notes (organization_id, entity_type, entity_id, created_at DESC)
          WHERE deleted_at IS NULL;
        """
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON notes TO crm_app;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_notes_entity_created;")
    op.drop_index(op.f("ix_notes_organization_id"), table_name="notes")
    op.drop_index(op.f("ix_notes_deleted_at"), table_name="notes")
    op.drop_table("notes")

"""file_attachments — files attached to Lead/Customer/Deal

Metadata table; the blobs live in S3 (MinIO in dev). Indexed for
the "list attachments for this entity" query. Composite tenant
indices that autogenerate keeps trying to drop are KEPT — see
`drop_user_billing_columns` for the rationale.

Revision ID: e05d0dcd743e
Revises: 31c9a3466f9c
Create Date: 2026-06-01 13:49:23.492937+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e05d0dcd743e"
down_revision: Union[str, None] = "31c9a3466f9c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "file_attachments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("uploader_user_id", sa.UUID(), nullable=True),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["uploader_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_file_attachments_deleted_at"),
        "file_attachments",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_file_attachments_organization_id"),
        "file_attachments",
        ["organization_id"],
        unique=False,
    )
    # "Attachments for this entity, newest first" — same pattern as
    # the activities + notes indices.
    op.execute(
        """
        CREATE INDEX idx_file_attachments_entity_created
          ON file_attachments (organization_id, entity_type, entity_id, created_at DESC)
          WHERE deleted_at IS NULL;
        """
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON file_attachments TO crm_app;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_file_attachments_entity_created;")
    op.drop_index(
        op.f("ix_file_attachments_organization_id"),
        table_name="file_attachments",
    )
    op.drop_index(
        op.f("ix_file_attachments_deleted_at"), table_name="file_attachments"
    )
    op.drop_table("file_attachments")

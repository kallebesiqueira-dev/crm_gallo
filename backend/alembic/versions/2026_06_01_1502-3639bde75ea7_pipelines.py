"""pipelines — customer-defined funnels (Phase 1: tables only)

Phase 1 adds `pipelines` + `pipeline_stages` and the per-org auto-seed
service. Lead/Deal are NOT yet bound to pipeline_stage_id — the
existing LeadStage/DealStage enums remain the source of truth for
this round. Phase 2 (next session): nullable pipeline_stage_id on
Lead/Deal + backfill + start migrating filters.

Composite tenant indices that autogenerate keeps trying to drop
(`sa.text("…DESC")` / `lower()`) are KEPT — see
`drop_user_billing_columns` for the rationale.

Revision ID: 3639bde75ea7
Revises: 94990b0118ae
Create Date: 2026-06-01 15:02:08.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3639bde75ea7"
down_revision: Union[str, None] = "94990b0118ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipelines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind", sa.Enum("lead", "deal", name="pipelinekind"), nullable=False
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pipelines_deleted_at"), "pipelines", ["deleted_at"], unique=False
    )
    op.create_index(
        op.f("ix_pipelines_organization_id"),
        "pipelines",
        ["organization_id"],
        unique=False,
    )
    # Per-org slug uniqueness within a kind. Live rows only so a
    # soft-deleted pipeline frees its slug for the same kind.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_pipelines_org_kind_slug_live
          ON pipelines (organization_id, kind, slug)
          WHERE deleted_at IS NULL;
        """
    )

    op.create_table(
        "pipeline_stages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("pipeline_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("probability", sa.Integer(), nullable=False),
        sa.Column("is_won", sa.Boolean(), nullable=False),
        sa.Column("is_lost", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["pipeline_id"], ["pipelines.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pipeline_stages_deleted_at"),
        "pipeline_stages",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pipeline_stages_pipeline_id"),
        "pipeline_stages",
        ["pipeline_id"],
        unique=False,
    )
    # Slug uniqueness per pipeline.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_pipeline_stages_pipeline_slug_live
          ON pipeline_stages (pipeline_id, slug)
          WHERE deleted_at IS NULL;
        """
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON pipelines TO crm_app;")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON pipeline_stages TO crm_app;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_pipeline_stages_pipeline_slug_live;")
    op.drop_index(
        op.f("ix_pipeline_stages_pipeline_id"), table_name="pipeline_stages"
    )
    op.drop_index(
        op.f("ix_pipeline_stages_deleted_at"), table_name="pipeline_stages"
    )
    op.drop_table("pipeline_stages")

    op.execute("DROP INDEX IF EXISTS uq_pipelines_org_kind_slug_live;")
    op.drop_index(op.f("ix_pipelines_organization_id"), table_name="pipelines")
    op.drop_index(op.f("ix_pipelines_deleted_at"), table_name="pipelines")
    op.drop_table("pipelines")
    sa.Enum(name="pipelinekind").drop(op.get_bind(), checkfirst=True)

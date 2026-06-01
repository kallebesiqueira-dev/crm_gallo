"""teams — optional grouping of users + team_id FK on User/Lead/Deal

Adds the `teams` table and the three `team_id` foreign keys
(SET NULL on delete so wiping a team doesn't orphan its members).
Slug uniqueness per-org is enforced via a partial unique index so
soft-deleted teams free their slug.

Composite tenant indices that autogenerate keeps trying to drop
(`sa.text("…DESC")` / `lower()`) are KEPT — see
`drop_user_billing_columns` for the rationale.

Revision ID: 94990b0118ae
Revises: e05d0dcd743e
Create Date: 2026-06-01 14:20:01.480950+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "94990b0118ae"
down_revision: Union[str, None] = "e05d0dcd743e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
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
    op.create_index(op.f("ix_teams_deleted_at"), "teams", ["deleted_at"], unique=False)
    op.create_index(
        op.f("ix_teams_organization_id"), "teams", ["organization_id"], unique=False
    )
    # Per-org slug uniqueness, scoped to live rows so a soft-deleted
    # team's slug can be reused.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_teams_org_slug_live
          ON teams (organization_id, slug)
          WHERE deleted_at IS NULL;
        """
    )

    # team_id FK on User / Lead / Deal — nullable; SET NULL on team
    # delete so a winding-down team doesn't lose its users/records.
    op.add_column("users", sa.Column("team_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_users_team_id"), "users", ["team_id"], unique=False)
    op.create_foreign_key(
        "fk_users_team_id", "users", "teams", ["team_id"], ["id"], ondelete="SET NULL"
    )

    op.add_column("leads", sa.Column("team_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_leads_team_id"), "leads", ["team_id"], unique=False)
    op.create_foreign_key(
        "fk_leads_team_id", "leads", "teams", ["team_id"], ["id"], ondelete="SET NULL"
    )

    op.add_column("deals", sa.Column("team_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_deals_team_id"), "deals", ["team_id"], unique=False)
    op.create_foreign_key(
        "fk_deals_team_id", "deals", "teams", ["team_id"], ["id"], ondelete="SET NULL"
    )

    # Grant CRUD on the new table to the runtime role; default privs
    # for the crm role should cover this but explicit GRANT is
    # idempotent and removes ordering doubt.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON teams TO crm_app;")


def downgrade() -> None:
    op.drop_constraint("fk_deals_team_id", "deals", type_="foreignkey")
    op.drop_index(op.f("ix_deals_team_id"), table_name="deals")
    op.drop_column("deals", "team_id")

    op.drop_constraint("fk_leads_team_id", "leads", type_="foreignkey")
    op.drop_index(op.f("ix_leads_team_id"), table_name="leads")
    op.drop_column("leads", "team_id")

    op.drop_constraint("fk_users_team_id", "users", type_="foreignkey")
    op.drop_index(op.f("ix_users_team_id"), table_name="users")
    op.drop_column("users", "team_id")

    op.execute("DROP INDEX IF EXISTS uq_teams_org_slug_live;")
    op.drop_index(op.f("ix_teams_organization_id"), table_name="teams")
    op.drop_index(op.f("ix_teams_deleted_at"), table_name="teams")
    op.drop_table("teams")

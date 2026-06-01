"""multi_tenant_organizations

Introduces the `Organization` + `OrgMembership` tables and a non-null
`organization_id` FK on every tenant table (leads, customers, deals,
tasks). The audit_logs table gets a nullable FK because platform-level
events (login, logout, webhook idempotency) have no org context.

Backfill strategy for existing installs:
  1. Create a single `default-workspace` organization, inheriting billing
     from the oldest admin user (so the migration is non-destructive for
     active subscriptions).
  2. Every existing user becomes a member of that org, keeping the role
     they already had on `users.role`.
  3. Every existing lead / customer / deal / task / audit_log is
     re-parented to the default-workspace.
  4. Each user's `last_active_org_id` points at the default-workspace
     so the next login lands them in a valid org.

After step 3 the `organization_id` columns are altered to NOT NULL.
Composite `(organization_id, created_at DESC)` indices are added so
the new tenant-scoped list queries scale.

Revision ID: bcac4a2cdbfa
Revises: be40f9fed1a8
Create Date: 2026-05-30 17:56:26.366405+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "bcac4a2cdbfa"
down_revision: Union[str, None] = "be40f9fed1a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tenant tables that get a NOT NULL organization_id FK + composite index.
TENANT_TABLES = ("leads", "customers", "deals", "tasks")


# Reference Postgres enums that ALREADY EXIST in the DB (created when
# users.plan / billing_cycle / role were added). `create_type=False`
# tells SQLAlchemy: don't issue a CREATE TYPE — just point at the
# existing one.
plan_enum = postgresql.ENUM(
    "free", "standard", "premium", name="plan", create_type=False
)
billing_cycle_enum = postgresql.ENUM(
    "monthly", "yearly", name="billingcycle", create_type=False
)
userrole_enum = postgresql.ENUM(
    "admin", "manager", "sales_agent", "support_agent", "client",
    name="userrole", create_type=False,
)


def upgrade() -> None:
    # ── 1. organizations table ─────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("plan", plan_enum, server_default="free", nullable=False),
        sa.Column("billing_cycle", billing_cycle_enum, server_default="monthly", nullable=False),
        sa.Column("plan_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_renewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_organizations_slug"), "organizations", ["slug"], unique=True)
    op.create_index(op.f("ix_organizations_stripe_customer_id"), "organizations", ["stripe_customer_id"])
    op.create_index(op.f("ix_organizations_stripe_subscription_id"), "organizations", ["stripe_subscription_id"])

    # ── 2. org_memberships junction table ──────────────────────────────
    op.create_table(
        "org_memberships",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("role", userrole_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "organization_id"),
    )

    # ── 3. organization_id columns (nullable for backfill) ─────────────
    for table in TENANT_TABLES:
        op.add_column(table, sa.Column("organization_id", sa.UUID(), nullable=True))
        op.create_index(op.f(f"ix_{table}_organization_id"), table, ["organization_id"])
        op.create_foreign_key(
            f"fk_{table}_organization_id",
            table, "organizations",
            ["organization_id"], ["id"],
            ondelete="CASCADE",
        )

    # audit_logs gets a nullable FK (platform events have no org)
    op.add_column("audit_logs", sa.Column("organization_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_audit_logs_organization_id"), "audit_logs", ["organization_id"])
    op.create_foreign_key(
        "fk_audit_logs_organization_id",
        "audit_logs", "organizations",
        ["organization_id"], ["id"],
        ondelete="SET NULL",
    )

    # users.last_active_org_id (SET NULL to avoid circular cascade)
    op.add_column("users", sa.Column("last_active_org_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_users_last_active_org_id",
        "users", "organizations",
        ["last_active_org_id"], ["id"],
        ondelete="SET NULL",
    )

    # ── 4. Backfill — only runs when there are existing users ──────────
    # Creates one default-workspace org per install, inheriting billing
    # from the oldest admin so an active Stripe subscription stays glued
    # to a real entity.
    op.execute(
        """
        INSERT INTO organizations (
            id, name, slug,
            plan, billing_cycle,
            plan_started_at, plan_renewed_at, plan_canceled_at, trial_ends_at,
            stripe_customer_id, stripe_subscription_id,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            'CRM Gallo Workspace',
            'default-workspace',
            COALESCE(seed.plan, 'free'),
            COALESCE(seed.billing_cycle, 'monthly'),
            seed.plan_started_at, seed.plan_renewed_at, seed.plan_canceled_at, seed.trial_ends_at,
            seed.stripe_customer_id, seed.stripe_subscription_id,
            NOW(), NOW()
        FROM (
            SELECT plan, billing_cycle,
                   plan_started_at, plan_renewed_at, plan_canceled_at, trial_ends_at,
                   stripe_customer_id, stripe_subscription_id
            FROM users
            WHERE role = 'admin'
            ORDER BY created_at ASC
            LIMIT 1
        ) AS seed
        WHERE EXISTS (SELECT 1 FROM users)
          AND NOT EXISTS (SELECT 1 FROM organizations WHERE slug = 'default-workspace');
        """
    )

    # Every user becomes a member of default-workspace, keeping their
    # legacy role from users.role. Idempotent via ON CONFLICT.
    op.execute(
        """
        INSERT INTO org_memberships (user_id, organization_id, role, created_at)
        SELECT u.id, o.id, u.role, u.created_at
        FROM users u
        CROSS JOIN organizations o
        WHERE o.slug = 'default-workspace'
        ON CONFLICT (user_id, organization_id) DO NOTHING;
        """
    )

    # Re-parent every tenant row to default-workspace.
    for table in TENANT_TABLES:
        op.execute(
            f"""
            UPDATE {table}
            SET organization_id = (SELECT id FROM organizations WHERE slug = 'default-workspace')
            WHERE organization_id IS NULL;
            """
        )

    # Audit logs: backfill historical events into default-workspace too.
    # Future platform-level events keep this column NULL.
    op.execute(
        """
        UPDATE audit_logs
        SET organization_id = (SELECT id FROM organizations WHERE slug = 'default-workspace')
        WHERE organization_id IS NULL;
        """
    )

    # Pin each user's current-org pointer at default-workspace.
    op.execute(
        """
        UPDATE users
        SET last_active_org_id = (SELECT id FROM organizations WHERE slug = 'default-workspace')
        WHERE last_active_org_id IS NULL;
        """
    )

    # ── 5. Enforce NOT NULL on tenant tables (post-backfill) ───────────
    for table in TENANT_TABLES:
        op.alter_column(table, "organization_id", existing_type=sa.UUID(), nullable=False)

    # ── 6. Composite indices for the new tenant-scoped list queries ────
    # `(organization_id, created_at DESC)` is the access pattern every
    # tenant table will hit on its first paginated list call.
    op.create_index(
        "idx_leads_org_created",
        "leads",
        ["organization_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_customers_org_created",
        "customers",
        ["organization_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_deals_org_stage_updated",
        "deals",
        ["organization_id", "stage", sa.text("updated_at DESC")],
    )
    op.create_index(
        "idx_tasks_org_due",
        "tasks",
        ["organization_id", "due_date"],
    )
    op.create_index(
        "idx_audit_logs_org_created",
        "audit_logs",
        ["organization_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_audit_logs_org_created", table_name="audit_logs")
    op.drop_index("idx_tasks_org_due", table_name="tasks")
    op.drop_index("idx_deals_org_stage_updated", table_name="deals")
    op.drop_index("idx_customers_org_created", table_name="customers")
    op.drop_index("idx_leads_org_created", table_name="leads")

    op.drop_constraint("fk_users_last_active_org_id", "users", type_="foreignkey")
    op.drop_column("users", "last_active_org_id")

    op.drop_constraint("fk_audit_logs_organization_id", "audit_logs", type_="foreignkey")
    op.drop_index(op.f("ix_audit_logs_organization_id"), table_name="audit_logs")
    op.drop_column("audit_logs", "organization_id")

    for table in TENANT_TABLES:
        op.drop_constraint(f"fk_{table}_organization_id", table, type_="foreignkey")
        op.drop_index(op.f(f"ix_{table}_organization_id"), table_name=table)
        op.drop_column(table, "organization_id")

    op.drop_table("org_memberships")
    op.drop_index(op.f("ix_organizations_stripe_subscription_id"), table_name="organizations")
    op.drop_index(op.f("ix_organizations_stripe_customer_id"), table_name="organizations")
    op.drop_index(op.f("ix_organizations_slug"), table_name="organizations")
    op.drop_table("organizations")

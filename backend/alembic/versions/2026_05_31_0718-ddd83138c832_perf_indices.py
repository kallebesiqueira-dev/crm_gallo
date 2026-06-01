"""perf_indices — Phase P1 database hardening

Adds the index set called for in the P1 backlog:
  * Partial unique on `(organization_id, lower(email))` for Lead and
    Customer, scoped to live (`deleted_at IS NULL`) rows with a
    non-null email. Prevents duplicate contacts within one tenant
    while allowing the same email across orgs (every CRM "two
    different companies have the same lead" case) and not blocking
    a re-import of a previously trashed contact. `lower(email)` so
    `John@ACME` and `john@acme` collide.
  * Composite `(organization_id, stage, created_at DESC)` on Lead —
    powers the "leads by stage, newest first" view. Mirrors the
    existing `idx_deals_org_stage_updated` on Deal.
  * Composite `(organization_id, owner_id) WHERE deleted_at IS NULL`
    on Lead/Customer/Deal/Task — "my open records" queries (which
    the dashboard widgets and assigned-to-me views run constantly)
    no longer have to scan all rows in the org.
  * `(organization_id, expected_close_date)` on Deal, scoped to
    open pipeline (`deleted_at IS NULL AND stage NOT IN
    ('won','lost')`) — for forecast queries. The partial predicate
    keeps the index tiny.

DDL only — no data touched — so RLS doesn't apply.

Revision ID: ddd83138c832
Revises: aff1800a6b5d
Create Date: 2026-05-31 07:18:57.116568+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = "ddd83138c832"
down_revision: Union[str, None] = "aff1800a6b5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Partial unique on email — Lead. `lower()` for case-insensitive
    # dedupe. Excludes deleted rows so trashing a contact frees the
    # email; excludes NULL emails because Lead.email is optional.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_leads_org_email_live
          ON leads (organization_id, lower(email))
          WHERE deleted_at IS NULL AND email IS NOT NULL;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_customers_org_email_live
          ON customers (organization_id, lower(email))
          WHERE deleted_at IS NULL AND email IS NOT NULL;
        """
    )

    # Lead "by stage, newest first" — analogue to the existing
    # idx_deals_org_stage_updated on Deal.
    op.execute(
        """
        CREATE INDEX idx_leads_org_stage_created
          ON leads (organization_id, stage, created_at DESC);
        """
    )

    # "My open records" composite — covers leads/customers/deals/tasks
    # filtered by org + owner-ish-id with deleted_at IS NULL. Task
    # uses `assignee_id` (the user the task is assigned to) where the
    # contact-style models use `owner_id`; we index whichever the
    # table actually has.
    for table, owner_col in (
        ("leads", "owner_id"),
        ("customers", "owner_id"),
        ("deals", "owner_id"),
        ("tasks", "assignee_id"),
    ):
        op.execute(
            f"""
            CREATE INDEX idx_{table}_org_owner_live
              ON {table} (organization_id, {owner_col})
              WHERE deleted_at IS NULL;
            """
        )

    # Deal forecast — only OPEN pipeline (won/lost are realised, not
    # forecast). Predicate keeps the index small (open deals are a
    # small slice of historical Deal data).
    op.execute(
        """
        CREATE INDEX idx_deals_org_close_open
          ON deals (organization_id, expected_close_date)
          WHERE deleted_at IS NULL
            AND stage NOT IN ('won', 'lost');
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_deals_org_close_open;")
    for table in ("leads", "customers", "deals", "tasks"):
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_org_owner_live;")
    op.execute("DROP INDEX IF EXISTS idx_leads_org_stage_created;")
    op.execute("DROP INDEX IF EXISTS uq_customers_org_email_live;")
    op.execute("DROP INDEX IF EXISTS uq_leads_org_email_live;")

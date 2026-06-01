"""rls_policies — Phase 6 defense-in-depth

Enables PostgreSQL Row-Level Security on every tenant-scoped table so a
forgotten `WHERE organization_id = ...` clause in app code cannot leak
cross-org data. The application sets the per-transaction GUC
`app.current_org_id` from `get_current_org_id`; policies read that GUC
and filter row visibility.

Design notes:
  - `ENABLE` + `FORCE` row level security: FORCE makes the table OWNER
    respect policies too (we run as the owner role; without FORCE the
    policies would be advisory and the app would silently bypass).
  - GUC read pattern:
      NULLIF(current_setting('app.current_org_id', true), '')::uuid
    The `true` second arg means "missing_ok" — returns '' instead of
    erroring if the GUC was never set. NULLIF maps '' → NULL so the
    cast doesn't blow up. A NULL GUC means "no scope" → policy
    `organization_id = NULL` is NULL (falsy) → zero rows. Safe default.
  - `audit_logs` gets a split policy: SELECT only sees own-org rows
    OR rows with `organization_id IS NULL` (system events from
    background jobs and webhooks). INSERT is unrestricted because the
    app is the only writer and `record_audit()` is the controlled
    entrypoint — restricting INSERT would block webhook actor=None
    audits.
  - Tables NOT covered (intentionally):
      users, organizations, org_memberships, org_invites,
      stripe_events, alembic_version.
      • `users` / `organizations` are the boundary objects themselves.
      • `org_memberships` is filtered by user_id server-side and
        needs cross-org visibility for the "my orgs" listing.
      • `org_invites` is queried by `token` from unauthenticated
        public endpoints (preview, register-with-invite) where
        there is no current_org_id to populate the GUC. The token
        itself is the credential — possession proves authorization
        — so app-layer enforcement is sufficient and RLS would
        break the public path.
      • `stripe_events` is idempotency dedupe only, no PII.
  - DDL is not subject to RLS — future Alembic migrations run fine.
    Data-touching migrations need to either set the GUC or
    DISABLE/ENABLE RLS around the data step (no current example).

Revision ID: ca1013e5bde6
Revises: 62fa86d2429c
Create Date: 2026-05-30 19:48:35.285826+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = "ca1013e5bde6"
down_revision: Union[str, None] = "62fa86d2429c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables that have a non-null `organization_id` column and use the
# standard symmetric policy (USING == WITH CHECK).
TENANT_TABLES = ("leads", "customers", "deals", "tasks")

# The GUC-reading expression — kept in one place so policies stay
# byte-identical across tables. Using NULLIF + the missing_ok flag of
# current_setting guarantees that a missing or empty GUC yields NULL,
# which makes any equality comparison fail (zero rows returned).
GUC_EXPR = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"


def upgrade() -> None:
    for tbl in TENANT_TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {tbl}
              FOR ALL
              USING (organization_id = {GUC_EXPR})
              WITH CHECK (organization_id = {GUC_EXPR});
            """
        )

    # Audit log gets a split policy: read scoped to org (+ system rows),
    # write unrestricted so webhook handlers and background jobs can
    # record events for any org once they've authenticated the event
    # source out-of-band.
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY audit_select_own_or_system ON audit_logs
          FOR SELECT
          USING (organization_id IS NULL OR organization_id = {GUC_EXPR});
        """
    )
    op.execute(
        """
        CREATE POLICY audit_insert_any ON audit_logs
          FOR INSERT
          WITH CHECK (true);
        """
    )
    # No UPDATE/DELETE policy on audit_logs by design — those ops should
    # never happen against an append-only ledger; without a policy
    # FORCE RLS will block them.


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_insert_any ON audit_logs;")
    op.execute("DROP POLICY IF EXISTS audit_select_own_or_system ON audit_logs;")
    op.execute("ALTER TABLE audit_logs NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY;")

    for tbl in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl};")
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")

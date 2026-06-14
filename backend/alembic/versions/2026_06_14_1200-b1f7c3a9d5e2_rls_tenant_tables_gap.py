"""rls_tenant_tables_gap — close the RLS gap on six tenant tables

The Phase-6 RLS round (ca1013e5bde6) enabled Row-Level Security on
leads/customers/deals/tasks + audit_logs, and every table created
afterwards enabled RLS in its own create-migration. But six
tenant-scoped tables shipped WITHOUT it and relied solely on app-layer
`WHERE organization_id = ...` filtering — with no defense-in-depth net:

    notes, activities, notifications, pipelines, teams   (direct organization_id)
    pipeline_stages                                       (org via pipeline_id)

Since the runtime role `crm_app` is NOBYPASSRLS, a single forgotten
WHERE clause on any of these would silently leak cross-org data on a
public-repo, live-prod app. This migration applies the same
ENABLE+FORCE+`tenant_isolation` policy used everywhere else.

Safety: the API (`database.py` begin-event from `get_current_org_id`)
and the worker (`worker/jobs.py` `set_current_org_id` on every job) set
the `app.current_org_id` GUC for every transaction that touches a tenant
table, so FORCE RLS is safe for all read AND write paths. Default
pipelines/stages are lazily seeded on first `GET /api/pipelines` under
the authenticated org context (not at org creation), so WITH CHECK
passes there too.

`pipeline_stages` has no own `organization_id` (it hangs off
`pipeline_id`), so its policy resolves the org transitively through
`pipelines` (itself RLS'd here); the subquery filters by org directly so
a direct query to `pipeline_stages` is scoped even without a join.

Revision ID: b1f7c3a9d5e2
Revises: 5b6c7d8e9f0a
Create Date: 2026-06-14 12:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = "b1f7c3a9d5e2"
down_revision: Union[str, None] = "5b6c7d8e9f0a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Same GUC-reading expression as ca1013e5bde6 — kept byte-identical so every
# tenant_isolation policy behaves identically (missing GUC -> NULL -> 0 rows).
GUC_EXPR = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"

# Tenant tables with a direct organization_id column → standard symmetric policy.
DIRECT_TABLES = ("notes", "activities", "notifications", "pipelines", "teams")


def upgrade() -> None:
    for tbl in DIRECT_TABLES:
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

    # pipeline_stages is scoped via its parent pipeline (no own organization_id).
    # The subquery is itself RLS-filtered (pipelines is FORCE-RLS'd above), and it
    # also constrains by org directly so a stage can never be read/written for a
    # pipeline outside the current org's scope.
    op.execute("ALTER TABLE pipeline_stages ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE pipeline_stages FORCE ROW LEVEL SECURITY;")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON pipeline_stages
          FOR ALL
          USING (pipeline_id IN (SELECT id FROM pipelines WHERE organization_id = {GUC_EXPR}))
          WITH CHECK (pipeline_id IN (SELECT id FROM pipelines WHERE organization_id = {GUC_EXPR}));
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON pipeline_stages;")
    op.execute("ALTER TABLE pipeline_stages NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE pipeline_stages DISABLE ROW LEVEL SECURITY;")

    for tbl in DIRECT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl};")
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")

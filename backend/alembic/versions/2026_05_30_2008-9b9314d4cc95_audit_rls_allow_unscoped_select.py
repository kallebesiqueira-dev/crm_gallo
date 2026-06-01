"""audit_rls_allow_unscoped_select

Phase 6 follow-up. The previous strict SELECT policy on `audit_logs`
broke INSERT ... RETURNING from unscoped (system) code paths: the
INSERT's WITH CHECK(true) passes, but the RETURNING clause exercises
the SELECT policy on the just-inserted row, which fails when the
new row has `organization_id = <some org>` but the request's
`app.current_org_id` GUC is empty (e.g. /api/orgs/me/switch,
Stripe webhooks, register, login). The driver raises
"new row violates row-level security policy" — confusing, because
WITH CHECK actually passes; it's the RETURNING-implies-SELECT path
that fails.

Fix: replace the SELECT policy with a permissive variant — when no
GUC is set the session is treated as "system context" and can read
any audit row; when a GUC is set, scope to own-org + system events.
Trade-off accepted:
  - Defense-in-depth on tenant DATA tables (leads/customers/deals/
    tasks) is preserved — those policies remain strict.
  - Audit_logs becomes "RLS-advisory" — a route that authenticates a
    user but never resolves an org (via get_current_org_id) could
    SELECT cross-org audit rows. No such route exists today; if one
    is added later, it must explicitly filter by org_id at the app
    layer.

Revision ID: 9b9314d4cc95
Revises: f5fde59e0dc8
Create Date: 2026-05-30 20:08:33.102071+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = "9b9314d4cc95"
down_revision: Union[str, None] = "f5fde59e0dc8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_select_own_or_system ON audit_logs;")
    op.execute(
        """
        CREATE POLICY audit_select_scoped_or_unscoped ON audit_logs
          FOR SELECT
          USING (
            current_setting('app.current_org_id', true) = ''
            OR organization_id IS NULL
            OR organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
          );
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_select_scoped_or_unscoped ON audit_logs;")
    op.execute(
        """
        CREATE POLICY audit_select_own_or_system ON audit_logs
          FOR SELECT
          USING (
            organization_id IS NULL
            OR organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
          );
        """
    )

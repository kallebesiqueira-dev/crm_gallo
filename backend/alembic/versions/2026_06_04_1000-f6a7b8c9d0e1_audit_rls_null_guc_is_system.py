"""audit_rls_null_guc_is_system

Fixes a register-on-fresh-DB 500: the audit_logs SELECT policy treated an
*unset* `app.current_org_id` GUC differently from an empty one.

`current_setting('app.current_org_id', true)` (missing_ok=true) returns the
empty string ONLY if the GUC was previously assigned in the session; on a
brand-new connection that has never had it set, it returns SQL NULL. The
public register path never resolves an org (the ContextVar is empty, so the
`begin` event in app/database.py never calls set_config), so the GUC is
genuinely unset. `record_audit(... organization_id=org.id ...)` then inserts
an audit row with a non-null organization_id; the INSERT's WITH CHECK(true)
passes, but the RETURNING clause re-checks the row against the SELECT policy:

    current_setting('app.current_org_id', true) = ''   -> NULL = ''  -> NULL
    OR organization_id IS NULL                          -> FALSE
    OR organization_id = NULLIF(NULL,'')::uuid          -> NULL

USING evaluates to NULL (falsy) → "new row violates row-level security policy".

On a long-lived dev DB the GUC had been touched by an earlier request on the
pooled connection, so it read '' and the first branch matched — which is why
this only reproduced on a fresh CI database (the same from-zero divergence
class as the empty-baseline issue).

Fix: replace the `= ''` test with `NULLIF(..., '') IS NULL`, which is true for
BOTH a never-set (NULL) and an empty ('') GUC. Semantics are unchanged for
scoped sessions; this only widens the "system context" bypass to include the
genuinely-unset case it always intended to cover. Tenant DATA tables
(leads/customers/deals/tasks) are unaffected — their strict policy already
yields zero rows under a NULL GUC, which is the correct safe default.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-04 10:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_select_scoped_or_unscoped ON audit_logs;")
    op.execute(
        """
        CREATE POLICY audit_select_scoped_or_unscoped ON audit_logs
          FOR SELECT
          USING (
            NULLIF(current_setting('app.current_org_id', true), '') IS NULL
            OR organization_id IS NULL
            OR organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
          );
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_select_scoped_or_unscoped ON audit_logs;")
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

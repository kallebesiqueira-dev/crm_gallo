"""audit_select_strict

Closes the §169 backlog item: drop the "unset GUC = system context can
read EVERY audit row" branch from the audit_logs SELECT policy. Since
2026-05-30 the policy had been intentionally permissive (RLS-advisory,
see 9b9314d4cc95) because unscoped code paths — register, login,
user.switch_org, Stripe webhooks — insert org-scoped audit rows while
`app.current_org_id` is unset, and the ORM's INSERT...RETURNING
re-checks the new row against the SELECT policy, failing the insert.

That blocker is gone: app.models.AuditLog now sets
`implicit_returning=False`, so audit inserts are plain INSERTs (the id
is client-generated and record_audit never reads the row back). Only
the INSERT policy's WITH CHECK (true) applies to writes, which lets us
make reads strict:

  - GUC set to org X  -> org-X rows + organization_id IS NULL rows
  - GUC unset         -> ONLY organization_id IS NULL rows

organization_id IS NULL rows stay visible to every session by design:
they are platform-level events (login, password reset, MFA enrollment)
with no org owner; the admin audit API additionally filters them by
actor-membership at the app layer. The cross-tenant surface — rows
that DO carry another org's id — is now closed at the database, not
just in app-layer WHERE clauses.

Deploy ordering: this migration must ship together with (or after) the
implicit_returning model change — old app code emitting RETURNING under
this strict policy would lose unscoped audit writes. Compose/CI run
`alembic upgrade head` from the same image as the app, so the pair is
atomic in practice.

Revision ID: 9f8e7d6c5b4a
Revises: f0a1b2c3d4e5
Create Date: 2026-06-10 21:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = "9f8e7d6c5b4a"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_select_scoped_or_unscoped ON audit_logs;")
    op.execute(
        """
        CREATE POLICY audit_select_strict ON audit_logs
          FOR SELECT
          USING (
            organization_id IS NULL
            OR organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
          );
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_select_strict ON audit_logs;")
    # Restore the permissive policy exactly as f6a7b8c9d0e1 left it.
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

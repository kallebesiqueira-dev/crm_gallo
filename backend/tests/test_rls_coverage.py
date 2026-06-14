"""RLS coverage contract — every tenant-scoped table MUST have forced RLS.

Regression guard for the gap where `notes`, `activities`, `notifications`,
`pipelines`, `pipeline_stages`, and `teams` shipped tenant-scoped but with no
ENABLE/FORCE ROW LEVEL SECURITY + policy — so a forgotten `WHERE
organization_id = ...` could leak cross-org data with no backstop (closed in
migration b1f7c3a9d5e2).

The required set is derived from the schema itself: any table carrying an
`organization_id` column, minus the documented exceptions, plus tables scoped
transitively via a parent FK. Deriving from the schema (not a hand-list) means
a FUTURE tenant table that forgets RLS fails this test automatically — which is
exactly the regression class that bit us.

Reads only catalog tables, so it runs in both single-role and two-role test
modes (the migration sets rowsecurity regardless of the connecting role).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

# Tables that carry organization_id but are intentionally NOT RLS'd — see the
# ca1013e5bde6 migration docstring: membership/invite rows need cross-org or
# token-based visibility from unscoped/public (pre-auth) paths.
RLS_EXEMPT = {"org_memberships", "org_invites"}

# Tenant tables scoped via a parent FK rather than a direct organization_id
# column (so the organization_id schema scan below cannot find them).
RLS_REQUIRED_EXTRA = {"pipeline_stages"}


def _required_tenant_tables(db: Session) -> set[str]:
    rows = (
        db.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'organization_id'"
            )
        )
        .scalars()
        .all()
    )
    return (set(rows) - RLS_EXEMPT) | RLS_REQUIRED_EXTRA


def test_every_tenant_table_has_forced_rls(db: Session):
    tables = _required_tenant_tables(db)
    # Sanity: the schema scan actually found tenant tables (incl. the gap set).
    assert {"notes", "activities", "notifications", "pipelines", "teams"} <= tables
    assert "pipeline_stages" in tables

    missing = []
    for t in sorted(tables):
        row = db.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity "
                "FROM pg_class WHERE oid = to_regclass('public.' || :t)"
            ),
            {"t": t},
        ).one()
        if not (row[0] and row[1]):
            missing.append({"table": t, "rowsecurity": row[0], "forced": row[1]})

    assert not missing, f"tenant tables without ENABLE+FORCE row level security: {missing}"


def test_every_tenant_table_has_a_policy(db: Session):
    tables = _required_tenant_tables(db)
    no_policy = [
        t
        for t in sorted(tables)
        if db.execute(
            text("SELECT count(*) FROM pg_policies WHERE schemaname = 'public' AND tablename = :t"),
            {"t": t},
        ).scalar_one()
        == 0
    ]
    assert not no_policy, f"tenant tables with RLS enabled but no policy attached: {no_policy}"

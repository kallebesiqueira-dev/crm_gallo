"""RLS contract for audit_logs under the strict SELECT policy (§169).

Migration 9f8e7d6c5b4a dropped the "unset GUC = system context reads
everything" branch. What a crm_app session can now read:

  - GUC set to org X  -> org-X rows + organization_id IS NULL rows
  - GUC unset         -> ONLY organization_id IS NULL rows

Writes from unscoped sessions (register, login, user.switch_org,
Stripe webhooks) keep working because AuditLog inserts are plain
INSERTs (implicit_returning=False on the model): INSERT's
WITH CHECK (true) passes and there is no RETURNING row for Postgres
to re-check against the SELECT policy.

These probes connect as the runtime role (crm_app) through a sync
psycopg2 engine — same loop-agnostic trick as conftest's admin engine,
but RLS-subject. Skipped in single-role mode (no APP_DATABASE_URL),
where the owner role bypasses RLS and there is nothing to probe.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditLog, Organization, User

settings = get_settings()

# Namespaced so seed/teardown can't touch real audit rows.
PROBE_ENTITY = "pytest-rls-probe"

pytestmark = pytest.mark.skipif(
    not settings.app_database_url,
    reason="single-role mode: owner role bypasses RLS, nothing to probe",
)


@pytest.fixture(scope="module")
def runtime_engine():
    """Sync engine as crm_app (NOSUPERUSER, NOBYPASSRLS)."""
    url = settings.app_database_url.replace("+asyncpg", "")
    engine = create_engine(url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture
def audit_probe_rows(db: Session, test_org: Organization, other_org: Organization):
    rows = [
        AuditLog(organization_id=test_org.id, action="pytest.rls.own", entity_type=PROBE_ENTITY),
        AuditLog(
            organization_id=other_org.id, action="pytest.rls.foreign", entity_type=PROBE_ENTITY
        ),
        # Platform-level event: no org owner (login, password reset, ...).
        AuditLog(organization_id=None, action="pytest.rls.system", entity_type=PROBE_ENTITY),
    ]
    db.add_all(rows)
    db.commit()
    yield rows
    # The generic org-cascade wipe in conftest does NOT remove audit rows
    # (the org FK is ON DELETE SET NULL), so clean up by namespace here.
    db.execute(delete(AuditLog).where(AuditLog.entity_type == PROBE_ENTITY))
    db.commit()


def _visible_actions(engine, org_id=None) -> set[str]:
    """Actions of probe rows visible to a crm_app transaction, with the
    tenant GUC optionally set (transaction-local, like the app does)."""
    with engine.begin() as conn:
        if org_id is not None:
            conn.execute(
                text("SELECT set_config('app.current_org_id', :v, true)"),
                {"v": str(org_id)},
            )
        result = conn.execute(
            text("SELECT action FROM audit_logs WHERE entity_type = :et"),
            {"et": PROBE_ENTITY},
        )
        return {row[0] for row in result}


def test_scoped_session_sees_own_org_and_system_rows(
    runtime_engine, audit_probe_rows, test_org: Organization
):
    assert _visible_actions(runtime_engine, test_org.id) == {
        "pytest.rls.own",
        "pytest.rls.system",
    }


def test_scoped_session_never_sees_foreign_org_rows(
    runtime_engine, audit_probe_rows, other_org: Organization
):
    assert _visible_actions(runtime_engine, other_org.id) == {
        "pytest.rls.foreign",
        "pytest.rls.system",
    }


def test_unscoped_session_sees_only_system_rows(runtime_engine, audit_probe_rows):
    # THE §169 fix: before the strict policy an unset GUC read everything.
    assert _visible_actions(runtime_engine) == {"pytest.rls.system"}


def test_unscoped_org_scoped_insert_still_works(runtime_engine, db: Session, test_org):
    """WITH CHECK (true) admits org-scoped writes from unscoped sessions
    as long as nothing RETURNINGs the row — the exact shape record_audit
    relies on."""
    with runtime_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit_logs (id, organization_id, action, entity_type)"
                " VALUES (gen_random_uuid(), :org, 'pytest.rls.unscoped-write', :et)"
            ),
            {"org": str(test_org.id), "et": PROBE_ENTITY},
        )
    written = (
        db.execute(
            select(AuditLog).where(AuditLog.action == "pytest.rls.unscoped-write")
        )
        .scalars()
        .all()
    )
    assert len(written) == 1 and written[0].organization_id == test_org.id
    db.execute(delete(AuditLog).where(AuditLog.entity_type == PROBE_ENTITY))
    db.commit()


def test_switch_org_endpoint_audits_under_strict_policy(
    admin_client, admin_user: User, test_org: Organization, db: Session
):
    """End-to-end pin of the historical breakage: /api/orgs/me/switch is
    authenticated but never resolves get_current_org_id (GUC unset) and
    audits user.switch_org WITH an organization_id. Under the old strict
    policy this 500'd via the RETURNING re-check; with plain INSERTs it
    must succeed and the audit row must land."""
    r = admin_client.post(
        "/api/orgs/me/switch", json={"organization_id": str(test_org.id)}
    )
    assert r.status_code == 200, r.text

    row = (
        db.execute(
            select(AuditLog).where(
                AuditLog.action == "user.switch_org",
                AuditLog.actor_id == admin_user.id,
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    assert row.organization_id == test_org.id
    db.execute(delete(AuditLog).where(AuditLog.id == row.id))
    db.commit()

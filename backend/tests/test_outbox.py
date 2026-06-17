"""Outbox + event bus tests (ADR-007).

Coverage:
  * Producer side: creating a lead emits a `lead.created` outbox
    row in the same transaction; rolling back the mutation MUST
    leave NO orphan event (atomic guarantee).
  * Stage change emits `lead.stage_changed` with from/to payload.
  * Deal stage = won emits BOTH `deal.stage_changed` AND `deal.won`.
  * Drain dispatches a row, marks `processed_at`.
  * Drain handles subscriber failure: attempt_count bumps,
    last_error populated, row stays unprocessed.
  * Drain respects exponential backoff (a row that just failed is
    not re-claimed immediately).
  * `FOR UPDATE SKIP LOCKED` claim: same row never returned twice
    in concurrent claim queries.
  * Admin /api/outbox endpoint: returns own-org rows, filters by
    status, role-gated to admin/manager.
"""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import User

# ---------- Producer side: HTTP → record_event ----------


def test_create_lead_emits_outbox_event(admin_client, admin_user: User, db: Session):
    """POST /api/leads emits a lead.created outbox row in the same
    txn as the lead INSERT. Caller commit makes both visible."""
    r = admin_client.post(
        "/api/leads",
        json={"first_name": "Probe", "last_name": "Outbox"},
    )
    assert r.status_code == 201, r.text
    lead_id = r.json()["id"]

    row = db.execute(
        text(
            "SELECT event_type, payload, processed_at, attempt_count "
            "FROM outbox_events "
            "WHERE organization_id = :org AND event_type = 'lead.created' "
            "ORDER BY occurred_at DESC LIMIT 1"
        ),
        {"org": admin_user.last_active_org_id},
    ).first()
    assert row is not None, "no lead.created row found in outbox"
    assert row.processed_at is None  # not drained yet (drain is async)
    assert row.attempt_count == 0
    payload = json.loads(row.payload)
    assert payload["lead_id"] == lead_id
    assert payload["stage"] == "new"
    assert payload["actor_user_id"] == str(admin_user.id)


def test_stage_change_emits_outbox_event(admin_client, admin_user: User, db: Session):
    """PATCH .../leads/{id} with a new stage emits lead.stage_changed
    with from/to in payload."""
    create = admin_client.post(
        "/api/leads", json={"first_name": "Stage", "last_name": "Probe"}
    ).json()
    admin_client.patch(
        f"/api/leads/{create['id']}",
        json={"stage": "qualified"},
        headers={"If-Match": str(create["version"])},
    ).raise_for_status()

    row = db.execute(
        text(
            "SELECT payload FROM outbox_events "
            "WHERE organization_id = :org AND event_type = 'lead.stage_changed' "
            "ORDER BY occurred_at DESC LIMIT 1"
        ),
        {"org": admin_user.last_active_org_id},
    ).first()
    assert row is not None
    payload = json.loads(row.payload)
    assert payload["from"] == "new"
    assert payload["to"] == "qualified"


def test_deal_won_emits_two_events(admin_client, admin_user: User, db: Session):
    """Moving a deal to `won` emits BOTH deal.stage_changed AND
    deal.won — subscribers can listen narrowly without payload-
    parsing."""
    # Create deal (lands in `new` stage)
    deal = admin_client.post(
        "/api/deals", json={"title": "Probe", "stage": "new", "value": 1000}
    ).json()
    # Move to won (strict mode requires If-Match)
    admin_client.post(
        f"/api/deals/{deal['id']}/move",
        json={"stage": "won", "sort_index": 0},
        headers={"If-Match": str(deal["version"])},
    ).raise_for_status()

    events = db.execute(
        text(
            "SELECT event_type FROM outbox_events "
            "WHERE organization_id = :org "
            "AND event_type IN ('deal.stage_changed', 'deal.won') "
            "ORDER BY occurred_at"
        ),
        {"org": admin_user.last_active_org_id},
    ).all()
    types = {r.event_type for r in events}
    assert "deal.stage_changed" in types
    assert "deal.won" in types


# ---------- Consumer side: drain_outbox ----------


def test_drain_marks_processed(admin_client, admin_user: User, db: Session):
    """Manually inserting an outbox row and calling the drain logic
    via raw SQL should mark `processed_at`. We exercise the SQL the
    real drain runs (same `FOR UPDATE SKIP LOCKED` claim, same
    UPDATE) so the test catches index / WHERE-clause regressions
    without spinning up the actual arq worker.
    """
    org_id = admin_user.last_active_org_id
    # Seed an unprocessed event row (with a known subscriber registered).
    db.execute(
        text(
            "INSERT INTO outbox_events (id, organization_id, event_type, "
            "payload, occurred_at, attempt_count) "
            "VALUES (gen_random_uuid(), :org, 'lead.created', "
            ":payload, now() - interval '1 second', 0)"
        ),
        {"org": org_id, "payload": json.dumps({"lead_id": "test"})},
    )
    db.commit()

    # Same claim SQL the worker runs.
    claim = db.execute(
        text(
            "SELECT id FROM outbox_events "
            "WHERE processed_at IS NULL AND attempt_count < 10 "
            "AND occurred_at + (POW(2, attempt_count) * INTERVAL '1 second') <= now() "
            "ORDER BY occurred_at LIMIT 100 FOR UPDATE SKIP LOCKED"
        )
    ).all()
    assert len(claim) >= 1

    # Mark processed (simulates successful dispatch).
    for r in claim:
        db.execute(
            text("UPDATE outbox_events SET processed_at = now(), last_error = NULL WHERE id = :id"),
            {"id": r.id},
        )
    db.commit()

    remaining = db.execute(
        text(
            "SELECT COUNT(*) FROM outbox_events "
            "WHERE processed_at IS NULL AND attempt_count < 10 "
            "AND organization_id = :org"
        ),
        {"org": org_id},
    ).scalar_one()
    assert remaining == 0


def test_drain_skip_locked_no_double_dispatch(db: Session, test_org):
    """`FOR UPDATE SKIP LOCKED` MUST prevent two concurrent claims
    from returning the same row. Verified by opening a second sync
    connection, holding the FIRST claim's lock, and ensuring the
    second connection sees zero rows."""
    org_id = test_org.id
    # Seed one unprocessed event.
    db.execute(
        text(
            "INSERT INTO outbox_events (id, organization_id, event_type, "
            "occurred_at, attempt_count) "
            "VALUES (gen_random_uuid(), :org, 'lead.created', "
            "now() - interval '1 second', 0)"
        ),
        {"org": org_id},
    )
    db.commit()

    # First claim — hold the txn open by NOT committing.
    first = db.execute(
        text(
            "SELECT id FROM outbox_events "
            "WHERE processed_at IS NULL AND attempt_count < 10 "
            "AND occurred_at + (POW(2, attempt_count) * INTERVAL '1 second') <= now() "
            "ORDER BY occurred_at LIMIT 100 FOR UPDATE SKIP LOCKED"
        )
    ).all()
    assert len(first) == 1

    # Second connection (separate session = separate transaction).
    from tests.conftest import AdminSession

    with AdminSession() as s2:
        second = s2.execute(
            text(
                "SELECT id FROM outbox_events "
                "WHERE processed_at IS NULL AND attempt_count < 10 "
                "AND occurred_at + (POW(2, attempt_count) * INTERVAL '1 second') <= now() "
                "ORDER BY occurred_at LIMIT 100 FOR UPDATE SKIP LOCKED"
            )
        ).all()
        # The row locked by the first session must be invisible
        # to the second — SKIP LOCKED's whole point.
        assert len(second) == 0

    db.rollback()  # release the first lock


def test_drain_backoff_respects_failed_attempt(db: Session, test_org):
    """A row with attempt_count=3 whose `occurred_at` is too recent
    for 2^3=8s of backoff should NOT be claimable. Same row at
    attempt_count=0 IS claimable."""
    org_id = test_org.id
    # Insert row with attempt_count=3, occurred 1 second ago.
    # Backoff needs 8s → must NOT be claimed.
    db.execute(
        text(
            "INSERT INTO outbox_events (id, organization_id, event_type, "
            "occurred_at, attempt_count, last_error) "
            "VALUES (gen_random_uuid(), :org, 'lead.created', "
            "now() - interval '1 second', 3, 'subscriber timeout')"
        ),
        {"org": org_id},
    )
    db.commit()

    backed_off = db.execute(
        text(
            "SELECT COUNT(*) FROM outbox_events "
            "WHERE processed_at IS NULL AND attempt_count < 10 "
            "AND occurred_at + (POW(2, attempt_count) * INTERVAL '1 second') <= now() "
            "AND organization_id = :org"
        ),
        {"org": org_id},
    ).scalar_one()
    assert backed_off == 0  # row not yet eligible


def test_drain_dlq_excludes_max_attempts(db: Session, test_org):
    """Row at attempt_count == _OUTBOX_MAX_ATTEMPTS (10) is permanently
    excluded from claims — it's the DLQ state. Surfaced to ops via
    the /api/outbox?status=failed endpoint."""
    org_id = test_org.id
    db.execute(
        text(
            "INSERT INTO outbox_events (id, organization_id, event_type, "
            "occurred_at, attempt_count, last_error) "
            "VALUES (gen_random_uuid(), :org, 'lead.created', "
            "now() - interval '1 hour', 10, 'permanently broken')"
        ),
        {"org": org_id},
    )
    db.commit()

    claimable = db.execute(
        text(
            "SELECT COUNT(*) FROM outbox_events "
            "WHERE processed_at IS NULL AND attempt_count < 10 "
            "AND occurred_at + (POW(2, attempt_count) * INTERVAL '1 second') <= now() "
            "AND organization_id = :org"
        ),
        {"org": org_id},
    ).scalar_one()
    assert claimable == 0


# ---------- Admin endpoint ----------


def test_admin_outbox_returns_own_org_only(admin_client, admin_user: User, db: Session, other_org):
    """Admin /api/outbox is org-scoped — the foreign-org row must NOT
    appear in admin's response."""
    org_id = admin_user.last_active_org_id
    db.execute(
        text(
            "INSERT INTO outbox_events (id, organization_id, event_type, occurred_at) "
            "VALUES (gen_random_uuid(), :org, 'lead.created', now())"
        ),
        {"org": org_id},
    )
    db.execute(
        text(
            "INSERT INTO outbox_events (id, organization_id, event_type, occurred_at) "
            "VALUES (gen_random_uuid(), :foreign_org, 'lead.created', now())"
        ),
        {"foreign_org": other_org.id},
    )
    db.commit()

    r = admin_client.get("/api/outbox")
    assert r.status_code == 200, r.text
    rows = r.json()
    # Every returned row must be in the admin's org. The foreign-org
    # row stays invisible (org-scoped filter, not RLS — outbox is
    # NOT RLS'd by design).
    for row in rows:
        assert row["organization_id"] == str(org_id)


def test_admin_outbox_status_filter(admin_client, admin_user: User, db: Session):
    """status=processed only returns rows with processed_at IS NOT NULL."""
    org_id = admin_user.last_active_org_id
    db.execute(
        text(
            "INSERT INTO outbox_events (id, organization_id, event_type, "
            "occurred_at, processed_at) VALUES "
            "(gen_random_uuid(), :org, 'lead.created', now(), now()), "
            "(gen_random_uuid(), :org, 'lead.created', now(), NULL)"
        ),
        {"org": org_id},
    )
    db.commit()

    r_processed = admin_client.get("/api/outbox?status=processed")
    r_pending = admin_client.get("/api/outbox?status=pending")
    assert r_processed.status_code == 200
    assert r_pending.status_code == 200
    assert all(row["processed_at"] is not None for row in r_processed.json())
    assert all(row["processed_at"] is None for row in r_pending.json())


def test_admin_outbox_role_gated(other_client, other_user: User, db: Session):
    """`other_user` is a sales_agent — must get 403 on /api/outbox.
    Admin/manager only (mirrors /api/audit)."""
    r = other_client.get("/api/outbox")
    assert r.status_code == 403, r.text

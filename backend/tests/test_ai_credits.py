"""AI-credit enforcement — 1 credit = 1 AI action, monthly, per plan.

Verifies the /credits meter and that user-facing AI actions (lead scoring,
assistant) 402 once the plan's monthly allowance is spent, while unlimited
plans never block. Usage is seeded straight into llm_usage (the counter).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def _seed_usage(db: Session, org_id, n: int):
    db.execute(
        text(
            "INSERT INTO llm_usage "
            "(id, organization_id, use_case, provider, model, input_tokens, output_tokens, created_at) "
            "SELECT gen_random_uuid(), :o, 'lead_scoring', 'ollama', 'm', 1, 1, now() "
            "FROM generate_series(1, :n)"
        ),
        {"o": str(org_id), "n": n},
    )


def test_credits_requires_auth(client):
    assert client.get("/api/llm-usage/credits").status_code == 401


def test_credits_status_free_plan(admin_client):
    body = admin_client.get("/api/llm-usage/credits").json()
    assert body["limit"] == 50  # Free plan allowance
    assert body["unlimited"] is False
    assert body["remaining"] == 50 - body["used"]
    assert body["resets_at"]


def test_credits_reflect_usage(admin_client, db: Session, test_org):
    _seed_usage(db, test_org.id, 10)
    db.commit()
    body = admin_client.get("/api/llm-usage/credits").json()
    assert body["used"] >= 10
    assert body["remaining"] <= 40


def test_scoring_blocked_when_exhausted(admin_client, db: Session, test_org):
    lead = admin_client.post("/api/leads", json={"first_name": "Cap", "last_name": "Test"}).json()
    _seed_usage(db, test_org.id, 50)  # hit the Free allowance
    db.commit()
    r = admin_client.post(f"/api/leads/{lead['id']}/score")
    assert r.status_code == 402


def test_async_scoring_also_blocked_when_exhausted(admin_client, db: Session, test_org):
    # /score-async is user-initiated too — it must not bypass the quota.
    lead = admin_client.post("/api/leads", json={"first_name": "Async", "last_name": "Cap"}).json()
    _seed_usage(db, test_org.id, 50)
    db.commit()
    r = admin_client.post(f"/api/leads/{lead['id']}/score-async")
    assert r.status_code == 402


def test_assistant_blocked_when_exhausted(admin_client, db: Session, test_org):
    _seed_usage(db, test_org.id, 50)
    db.commit()
    r = admin_client.post("/api/assistant/chat", json={"message": "hi"})
    assert r.status_code == 402


def test_unlimited_plan_never_blocks(admin_client, db: Session, test_org):
    db.execute(text("UPDATE organizations SET plan='premium' WHERE id=:o"), {"o": str(test_org.id)})
    _seed_usage(db, test_org.id, 100)
    db.commit()
    status = admin_client.get("/api/llm-usage/credits").json()
    assert status["unlimited"] is True
    assert status["limit"] is None
    # AI actions still go through (no 402) on an unlimited plan.
    assert admin_client.post("/api/assistant/chat", json={"message": "hi"}).status_code == 200

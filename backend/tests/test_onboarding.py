"""Onboarding backend (plan.md §3): sector pipeline templates +
the computed 5-step first-session checklist."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import CsrfAwareClient


def test_templates_catalog_lists_all_sectors(admin_client: CsrfAwareClient):
    r = admin_client.get("/api/onboarding/templates")
    assert r.status_code == 200
    catalog = {t["slug"]: t for t in r.json()}
    assert set(catalog) == {
        "agency",
        "saas",
        "consulting",
        "construction",
        "real-estate",
        "whatsapp-sales",
        "b2b-simple",
    }
    saas = catalog["saas"]
    assert saas["kind"] == "deal"
    # Every template ends in exactly one won + one lost stage.
    for tpl in catalog.values():
        assert sum(1 for s in tpl["stages"] if s["is_won"]) == 1
        assert sum(1 for s in tpl["stages"] if s["is_lost"]) == 1


def test_apply_template_creates_pipeline_with_stages(admin_client: CsrfAwareClient):
    r = admin_client.post("/api/onboarding/templates/saas/apply")
    assert r.status_code == 201, r.text
    pid = r.json()["pipeline_id"]

    detail = admin_client.get(f"/api/pipelines/{pid}").json()
    assert detail["kind"] == "deal"
    assert detail["name"] == "SaaS / Software"
    assert [s["name"] for s in detail["stages"]] == [
        "Demo scheduled",
        "Demo done",
        "Trial",
        "Negotiation",
        "Won",
        "Lost",
    ]
    assert detail["is_default"] is False

    # Re-applying the same template is a 409, not a duplicate.
    assert admin_client.post("/api/onboarding/templates/saas/apply").status_code == 409


def test_apply_template_set_default(admin_client: CsrfAwareClient):
    r = admin_client.post("/api/onboarding/templates/agency/apply", json={"set_default": True})
    assert r.status_code == 201, r.text
    pid = r.json()["pipeline_id"]
    assert admin_client.get(f"/api/pipelines/{pid}").json()["is_default"] is True


def test_apply_unknown_template_404(admin_client: CsrfAwareClient):
    assert admin_client.post("/api/onboarding/templates/nope/apply").status_code == 404


def test_apply_requires_privileged_role(other_client: CsrfAwareClient):
    assert other_client.post("/api/onboarding/templates/saas/apply").status_code == 403


def test_checklist_progression(admin_client: CsrfAwareClient, db: Session):
    # Fresh org: nothing done. (The auto-seeded default pipeline does
    # NOT count — the step tracks a deliberate setup action.)
    c = admin_client.get("/api/onboarding/checklist").json()
    assert c["completed"] == 0 and c["done"] is False
    by_key = {s["key"]: s["done"] for s in c["steps"]}
    assert set(by_key) == {
        "pipeline_ready",
        "first_lead",
        "next_action_set",
        "teammate_invited",
        "proposal_sent",
    }

    # 1. Apply a template → pipeline_ready.
    assert admin_client.post("/api/onboarding/templates/b2b-simple/apply").status_code == 201
    # 2. Create a lead → first_lead.
    assert (
        admin_client.post(
            "/api/leads", json={"first_name": "Check", "last_name": "List", "stage": "new"}
        ).status_code
        == 201
    )
    # 3. Create a deal and give it a next action (raw SQL — the ORM
    #    column belongs to the in-flight next-action lane).
    deal = admin_client.post("/api/deals", json={"title": "Checklist deal"}).json()
    db.execute(
        text("UPDATE deals SET next_action_at = now() + interval '1 day' WHERE id = :id"),
        {"id": deal["id"]},
    )
    db.commit()
    # 4. Invite a teammate.
    r = admin_client.post(
        "/api/orgs/current/invites",
        json={"email": "pytest-onboard-invite@example.com", "role": "sales_agent"},
    )
    assert r.status_code in (200, 201), r.text

    c = admin_client.get("/api/onboarding/checklist").json()
    by_key = {s["key"]: s["done"] for s in c["steps"]}
    assert by_key["pipeline_ready"] is True
    assert by_key["first_lead"] is True
    assert by_key["next_action_set"] is True
    assert by_key["teammate_invited"] is True
    assert by_key["proposal_sent"] is False  # no quote left draft
    assert c["completed"] == 4 and c["done"] is False

"""Web-to-Lead: admin CRUD + the public, unauthenticated submit path.

Admin CRUD is RLS-scoped and RBAC-gated (admin/manager mint forms). The
public ``POST /api/public/forms/{token}/submit`` resolves the tenant from
the token's embedded org, sets the RLS GUC, and creates a Lead — exercised
here over real HTTP with a cookie-less (anonymous) client. Cross-org rows
and direct assertions use the owner-role `db` session.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Lead, Organization, WebForm
from app.web_forms import mint_token
from tests.conftest import CsrfAwareClient


def _create_form(client: CsrfAwareClient, **overrides) -> dict:
    payload = {"name": "Contact Us"}
    payload.update(overrides)
    r = client.post("/api/forms", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _leads_in(db: Session, org_id: uuid.UUID) -> list[Lead]:
    db.expire_all()
    return list(
        db.execute(select(Lead).where(Lead.organization_id == org_id)).scalars().all()
    )


# ---------- Admin CRUD ----------


def test_create_form_mints_token(admin_client):
    form = _create_form(admin_client, name="Newsletter", default_source="Homepage")
    assert form["token"].startswith("crmf_")
    assert form["active"] is True
    assert form["submission_count"] == 0
    assert form["default_source"] == "Homepage"


def test_list_forms(admin_client):
    _create_form(admin_client, name="A")
    _create_form(admin_client, name="B")
    r = admin_client.get("/api/forms")
    assert r.status_code == 200, r.text
    names = {f["name"] for f in r.json()}
    assert {"A", "B"} <= names


def test_update_form(admin_client):
    form = _create_form(admin_client, name="Old")
    r = admin_client.patch(
        f"/api/forms/{form['id']}", json={"name": "New", "active": False}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "New"
    assert body["active"] is False
    # Token is immutable across an update — the embed must keep working.
    assert body["token"] == form["token"]


def test_delete_form(admin_client):
    form = _create_form(admin_client, name="Doomed")
    r = admin_client.delete(f"/api/forms/{form['id']}")
    assert r.status_code == 204, r.text
    assert admin_client.get("/api/forms").json() == [] or all(
        f["id"] != form["id"] for f in admin_client.get("/api/forms").json()
    )


def test_create_requires_privilege(other_client):
    # sales_agent is below the admin/manager bar for minting a form.
    r = other_client.post("/api/forms", json={"name": "Nope"})
    assert r.status_code == 403, r.text


def test_forms_are_org_scoped(db: Session, admin_client, other_org: Organization):
    # A form seeded in a different org must not appear in this org's list.
    foreign = WebForm(
        organization_id=other_org.id,
        name="Foreign",
        token=mint_token(other_org.id),
    )
    db.add(foreign)
    db.commit()
    r = admin_client.get("/api/forms")
    assert all(f["name"] != "Foreign" for f in r.json())


# ---------- Public submit ----------


def test_public_submit_creates_lead(db: Session, admin_client, test_org, admin_user):
    form = _create_form(admin_client, name="Capture", default_source="Landing")
    admin_client.cookies.clear()  # go anonymous for the public path
    r = admin_client.post(
        f"/api/public/forms/{form['token']}/submit",
        json={"first_name": "Jane", "last_name": "Doe", "email": "jane@acme.test"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    leads = _leads_in(db, test_org.id)
    assert len(leads) == 1
    lead = leads[0]
    assert lead.first_name == "Jane"
    assert lead.last_name == "Doe"
    assert lead.email == "jane@acme.test"
    assert lead.source == "Landing"
    # Owner inherited from the form's creator so the lead isn't orphaned.
    assert lead.owner_id == admin_user.id

    # submission_count bumped.
    db.expire_all()
    fresh = db.get(WebForm, uuid.UUID(form["id"]))
    assert fresh.submission_count == 1


def test_public_submit_splits_single_name(db: Session, admin_client, test_org):
    form = _create_form(admin_client, name="Capture")
    admin_client.cookies.clear()
    r = admin_client.post(
        f"/api/public/forms/{form['token']}/submit",
        json={"name": "Ada Lovelace", "email": "ada@acme.test"},
    )
    assert r.status_code == 200, r.text
    leads = _leads_in(db, test_org.id)
    assert len(leads) == 1
    assert leads[0].first_name == "Ada"
    assert leads[0].last_name == "Lovelace"


def test_public_submit_default_source(db: Session, admin_client, test_org):
    form = _create_form(admin_client, name="NoSource")  # default_source unset
    admin_client.cookies.clear()
    admin_client.post(
        f"/api/public/forms/{form['token']}/submit",
        json={"first_name": "No", "last_name": "Source"},
    )
    leads = _leads_in(db, test_org.id)
    assert leads[0].source == "Web Form"


def test_public_submit_honeypot_drops(db: Session, admin_client, test_org):
    form = _create_form(admin_client, name="Capture")
    admin_client.cookies.clear()
    r = admin_client.post(
        f"/api/public/forms/{form['token']}/submit",
        json={"first_name": "Bot", "last_name": "Spam", "website": "http://spam"},
    )
    # Looks like success to the bot, but no lead is created.
    assert r.status_code == 200, r.text
    assert _leads_in(db, test_org.id) == []


def test_public_submit_form_encoded_redirects(admin_client):
    form = _create_form(admin_client, name="Capture", redirect_url="https://acme.test/thanks")
    admin_client.cookies.clear()
    r = admin_client.post(
        f"/api/public/forms/{form['token']}/submit",
        data={"first_name": "Form", "last_name": "Post"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "https://acme.test/thanks"


def test_public_submit_inactive_404(admin_client):
    form = _create_form(admin_client, name="Paused", active=False)
    admin_client.cookies.clear()
    r = admin_client.post(
        f"/api/public/forms/{form['token']}/submit",
        json={"first_name": "X", "last_name": "Y"},
    )
    assert r.status_code == 404, r.text


def test_public_submit_bad_token_404(client):
    r = client.post(
        "/api/public/forms/not-a-real-token/submit",
        json={"first_name": "X", "last_name": "Y"},
    )
    assert r.status_code == 404, r.text


def test_public_submit_forged_org_404(db: Session, admin_client, other_org):
    # Swap the token's org-hex prefix for another org's — the token string
    # no longer matches any row, so RLS-scoped lookup returns nothing.
    form = _create_form(admin_client, name="Capture")
    secret = form["token"].split("_", 2)[2]
    forged = f"crmf_{other_org.id.hex}_{secret}"
    admin_client.cookies.clear()
    r = admin_client.post(
        f"/api/public/forms/{forged}/submit",
        json={"first_name": "X", "last_name": "Y"},
    )
    assert r.status_code == 404, r.text


def test_public_submit_requires_name(admin_client):
    form = _create_form(admin_client, name="Capture")
    admin_client.cookies.clear()
    r = admin_client.post(
        f"/api/public/forms/{form['token']}/submit",
        json={"email": "noname@acme.test"},
    )
    assert r.status_code == 422, r.text


def test_public_submit_duplicate_email_graceful(db: Session, admin_client, test_org):
    form = _create_form(admin_client, name="Capture")
    admin_client.cookies.clear()
    body = {"first_name": "Dup", "last_name": "Email", "email": "dup@acme.test"}
    r1 = admin_client.post(f"/api/public/forms/{form['token']}/submit", json=body)
    r2 = admin_client.post(f"/api/public/forms/{form['token']}/submit", json=body)
    assert r1.status_code == 200, r1.text
    # Second submit hits the live unique-email index → swallowed as success.
    assert r2.status_code == 200, r2.text
    assert len(_leads_in(db, test_org.id)) == 1
    db.expire_all()
    fresh = db.get(WebForm, uuid.UUID(form["id"]))
    # Only the first submit produced a lead, so only it counted.
    assert fresh.submission_count == 1

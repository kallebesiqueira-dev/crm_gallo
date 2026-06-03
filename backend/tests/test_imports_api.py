"""Imports / Exports HTTP-surface tests (ADR-016).

Covers the endpoints' guards and contracts WITHOUT a running worker:
  * `GET /api/imports/template` — canonical headers per entity.
  * `POST /api/imports` guards — empty 400, 1-concurrent 409, daily-cap
    429 — and the happy 201 (file lands in S3, job created `pending`).
  * `GET /api/imports/{id}` cross-org → 404 (never 403).
  * `GET /api/exports/{entity}` — CSV stream, org-scoped, every cell
    formula-injection-safe (TD-22); unknown entity → 404.

Worker-side processing (parse→dedupe→write) is exercised in
`test_imports_worker.py`; here the job stays `pending`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings

settings = get_settings()


def _seed_import_job(db: Session, org_id, status: str = "pending") -> uuid.UUID:
    """Insert an ImportJob directly (owner role bypasses RLS)."""
    job_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO import_jobs "
            "(id, organization_id, entity_type, mode, status, filename, "
            " content_type, storage_key) "
            "VALUES (:id, :org, 'lead', 'create', :status, 'f.csv', "
            " 'text/csv', :key)"
        ),
        {"id": job_id, "org": org_id, "status": status, "key": f"org-{org_id}/imports/{job_id}"},
    )
    db.commit()
    return job_id


# ---------- Template ----------


def test_template_lead_headers(admin_client):
    body = admin_client.get("/api/imports/template?entity_type=lead").json()
    assert body["entity_type"] == "lead"
    assert "first_name*" in body["headers"]
    assert "last_name*" in body["headers"]


def test_template_unknown_entity_422(admin_client):
    # entity_type is an enum query param → FastAPI validation 422.
    assert admin_client.get("/api/imports/template?entity_type=deal").status_code == 422


# ---------- List ----------


def test_list_imports_empty_for_fresh_org(admin_client):
    assert admin_client.get("/api/imports").json() == []


# ---------- Create guards ----------


def test_create_empty_file_is_400(admin_client):
    files = {"file": ("empty.csv", b"", "text/csv")}
    r = admin_client.post("/api/imports", data={"entity_type": "lead"}, files=files)
    assert r.status_code == 400


def test_create_blocked_while_one_in_flight_409(admin_client, db, test_org):
    _seed_import_job(db, test_org.id, status="processing")
    files = {"file": ("c.csv", b"first_name,last_name\nA,B\n", "text/csv")}
    r = admin_client.post("/api/imports", data={"entity_type": "lead"}, files=files)
    assert r.status_code == 409


def test_create_blocked_over_daily_cap_429(admin_client, db, test_org):
    # Fill the rolling-24h cap with COMPLETED jobs (so they don't also
    # trip the 1-in-flight guard, which would mask the 429).
    for _ in range(settings.import_daily_cap):
        _seed_import_job(db, test_org.id, status="completed")
    files = {"file": ("c.csv", b"first_name,last_name\nA,B\n", "text/csv")}
    r = admin_client.post("/api/imports", data={"entity_type": "lead"}, files=files)
    assert r.status_code == 429


def test_create_happy_path_creates_pending_job(admin_client):
    files = {"file": ("contacts.csv", b"first_name,last_name\nMaria,Silva\n", "text/csv")}
    r = admin_client.post(
        "/api/imports", data={"entity_type": "lead", "mode": "create"}, files=files
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["entity_type"] == "lead"
    assert body["filename"] == "contacts.csv"
    # And it now shows up in the list.
    listed = admin_client.get("/api/imports").json()
    assert any(j["id"] == body["id"] for j in listed)


# ---------- Get / cross-org isolation ----------


def test_get_import_cross_org_is_404(admin_client, db, other_org):
    # A job belonging to ANOTHER org must look "not found", not 403.
    foreign_job = _seed_import_job(db, other_org.id)
    assert admin_client.get(f"/api/imports/{foreign_job}").status_code == 404


def test_get_import_unknown_id_is_404(admin_client):
    assert admin_client.get(f"/api/imports/{uuid.uuid4()}").status_code == 404


# ---------- Export ----------


def test_export_streams_csv_with_header(admin_client):
    admin_client.post(
        "/api/leads", json={"first_name": "Maria", "last_name": "Silva"}
    ).raise_for_status()
    r = admin_client.get("/api/exports/lead?format=csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.splitlines()
    assert lines[0].startswith("id,first_name,last_name")
    assert any("Maria" in ln and "Silva" in ln for ln in lines[1:])


def test_export_neutralises_formula_injection(admin_client):
    # A note crafted as a spreadsheet formula must be exported as inert
    # text (leading single quote) — TD-22.
    admin_client.post(
        "/api/leads",
        json={"first_name": "Evil", "last_name": "Row", "notes": "=cmd|'/c calc'!A1"},
    ).raise_for_status()
    r = admin_client.get("/api/exports/lead?format=csv")
    assert r.status_code == 200
    # The dangerous cell is present but defanged with a leading quote.
    assert "'=cmd" in r.text
    # The raw, un-escaped formula must NOT appear as a bare cell value.
    assert ",=cmd|" not in r.text


def test_export_is_org_scoped(admin_client, db, other_org):
    db.execute(
        text(
            "INSERT INTO leads (id, organization_id, first_name, last_name, stage) "
            "VALUES (gen_random_uuid(), :org, 'Foreign', 'Probe', 'new')"
        ),
        {"org": other_org.id},
    )
    db.commit()
    r = admin_client.get("/api/exports/lead?format=csv")
    assert r.status_code == 200
    assert "Foreign" not in r.text


def test_export_unknown_entity_is_404(admin_client):
    assert admin_client.get("/api/exports/deal?format=csv").status_code == 404


def test_export_bad_format_is_422(admin_client):
    assert admin_client.get("/api/exports/lead?format=xlsx").status_code == 422

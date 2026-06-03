"""End-to-end `process_import` worker tests (ADR-016).

Drives the real worker coroutine (download → parse → validate → dedupe →
write) against the database and MinIO, exercising every lifecycle branch:
create-mode dedupe skip, upsert-mode update, per-row validation errors,
and a whole-file parse failure.

Loop / RLS plumbing: the app's runtime asyncpg engine is bound to the
sync TestClient's portal loop, so reusing it from an `async def test`
(which runs on pytest-asyncio's session loop) would cross loops. We build
a dedicated async engine here, bound to the test loop, and attach the
same transaction-scoped org-GUC listener the runtime uses — so the worker
runs as `crm_app` under RLS exactly like production.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import register_org_guc, set_current_org_id
from app.storage import put_object
from app.worker.jobs import process_import

settings = get_settings()


@pytest.fixture
async def worker_ctx():
    """A worker `ctx` whose SessionLocal is bound to the test loop.

    Mirrors what the arq worker startup builds: a `crm_app` engine with
    the org-GUC begin listener so RLS is enforced inside the job."""
    engine = create_async_engine(settings.runtime_database_url, future=True)
    register_org_guc(engine)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield {"SessionLocal": SessionLocal}
    finally:
        await engine.dispose()


def _make_job(
    db: Session,
    org_id,
    created_by,
    *,
    mode: str = "create",
    entity: str = "lead",
) -> tuple[uuid.UUID, str]:
    """Insert a pending ImportJob (owner role, RLS-bypassing) and return
    its id + storage_key."""
    job_id = uuid.uuid4()
    key = f"org-{org_id}/imports/{job_id}"
    db.execute(
        text(
            "INSERT INTO import_jobs "
            "(id, organization_id, created_by_user_id, entity_type, mode, "
            " status, filename, content_type, storage_key) "
            "VALUES (:id, :org, :uid, :entity, :mode, 'pending', 'f.csv', "
            " 'text/csv', :key)"
        ),
        {"id": job_id, "org": org_id, "uid": created_by, "entity": entity, "mode": mode, "key": key},
    )
    db.commit()
    return job_id, key


def _job_row(db: Session, job_id) -> dict:
    row = db.execute(
        text(
            "SELECT status, total_rows, created_count, updated_count, "
            "skipped_count, error_count, error_report, error_message "
            "FROM import_jobs WHERE id = :id"
        ),
        {"id": job_id},
    ).mappings().one()
    return dict(row)


def _lead_count(db: Session, org_id) -> int:
    return db.execute(
        text("SELECT count(*) FROM leads WHERE organization_id = :org AND deleted_at IS NULL"),
        {"org": org_id},
    ).scalar_one()


async def test_create_mode_inserts_and_dedupes(worker_ctx, db, test_org, admin_user):
    # Two unique rows + one dup of row 1 (same email) + one dup by phone.
    csv = (
        b"first_name,last_name,email,phone\n"
        b"Maria,Silva,maria@example.com,+41 79 111 22 33\n"
        b"Joao,Souza,joao@example.com,\n"
        b"Maria,Dup,MARIA@example.com,\n"  # email dup (case-insensitive)
        b"Carlos,Phone,,+41791112233\n"  # phone dup of row 1
    )
    job_id, key = _make_job(db, test_org.id, admin_user.id)
    await put_object(key, csv, "text/csv")

    set_current_org_id(test_org.id)
    result = await process_import(worker_ctx, str(job_id), str(test_org.id))

    assert result["status"] == "completed"
    row = _job_row(db, job_id)
    assert row["status"] == "completed"
    assert row["total_rows"] == 4
    assert row["created_count"] == 2  # Maria + Joao
    assert row["skipped_count"] == 2  # email dup + phone dup
    assert row["error_count"] == 0
    assert _lead_count(db, test_org.id) == 2


async def test_create_mode_skips_existing_record(worker_ctx, db, test_org, admin_user):
    # Pre-seed a lead that the import row should match → skipped.
    db.execute(
        text(
            "INSERT INTO leads (id, organization_id, first_name, last_name, email, stage) "
            "VALUES (gen_random_uuid(), :org, 'Existing', 'Lead', 'dup@example.com', 'new')"
        ),
        {"org": test_org.id},
    )
    db.commit()
    csv = b"first_name,last_name,email\nNew,Person,fresh@example.com\nDup,Match,dup@example.com\n"
    job_id, key = _make_job(db, test_org.id, admin_user.id)
    await put_object(key, csv, "text/csv")

    set_current_org_id(test_org.id)
    await process_import(worker_ctx, str(job_id), str(test_org.id))

    row = _job_row(db, job_id)
    assert row["created_count"] == 1
    assert row["skipped_count"] == 1


async def test_upsert_mode_updates_existing(worker_ctx, db, test_org, admin_user):
    lead_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO leads (id, organization_id, first_name, last_name, email, company, stage) "
            "VALUES (:id, :org, 'Old', 'Name', 'up@example.com', 'OldCo', 'new')"
        ),
        {"id": lead_id, "org": test_org.id},
    )
    db.commit()
    # Same email → match; non-empty cells overwrite, blank cells leave alone.
    csv = b"first_name,last_name,email,company\nNewFirst,NewLast,up@example.com,NewCo\n"
    job_id, key = _make_job(db, test_org.id, admin_user.id, mode="upsert")
    await put_object(key, csv, "text/csv")

    set_current_org_id(test_org.id)
    await process_import(worker_ctx, str(job_id), str(test_org.id))

    row = _job_row(db, job_id)
    assert row["updated_count"] == 1
    assert row["created_count"] == 0
    updated = db.execute(
        text("SELECT first_name, company FROM leads WHERE id = :id"), {"id": lead_id}
    ).mappings().one()
    assert updated["first_name"] == "NewFirst"
    assert updated["company"] == "NewCo"


async def test_validation_errors_counted_and_reported(worker_ctx, db, test_org, admin_user):
    csv = (
        b"first_name,last_name,email\n"
        b"Good,Row,good@example.com\n"
        b",NoFirstName,x@example.com\n"  # missing required first_name
        b"Bad,Email,not-an-email\n"  # invalid email
    )
    job_id, key = _make_job(db, test_org.id, admin_user.id)
    await put_object(key, csv, "text/csv")

    set_current_org_id(test_org.id)
    await process_import(worker_ctx, str(job_id), str(test_org.id))

    row = _job_row(db, job_id)
    assert row["status"] == "completed"  # per-row errors don't fail the file
    assert row["created_count"] == 1
    assert row["error_count"] == 2
    assert row["error_report"] is not None
    rows_with_errors = {e["row"] for e in row["error_report"]}
    assert rows_with_errors == {3, 4}  # +2 offset: header is row 1


async def test_missing_required_column_fails_whole_file(worker_ctx, db, test_org, admin_user):
    # No last_name column at all → whole-file failure, nothing imported.
    csv = b"first_name,email\nMaria,maria@example.com\n"
    job_id, key = _make_job(db, test_org.id, admin_user.id)
    await put_object(key, csv, "text/csv")

    set_current_org_id(test_org.id)
    result = await process_import(worker_ctx, str(job_id), str(test_org.id))

    assert result["status"] == "failed"
    row = _job_row(db, job_id)
    assert row["status"] == "failed"
    assert "last_name" in (row["error_message"] or "")
    assert _lead_count(db, test_org.id) == 0


async def test_completed_job_is_not_reprocessed(worker_ctx, db, test_org, admin_user):
    job_id, key = _make_job(db, test_org.id, admin_user.id)
    db.execute(
        text("UPDATE import_jobs SET status = 'completed' WHERE id = :id"), {"id": job_id}
    )
    db.commit()
    await put_object(key, b"first_name,last_name\nA,B\n", "text/csv")

    set_current_org_id(test_org.id)
    result = await process_import(worker_ctx, str(job_id), str(test_org.id))
    assert result["status"] == "already_completed"
    assert _lead_count(db, test_org.id) == 0

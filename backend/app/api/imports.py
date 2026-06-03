"""Bulk import of leads / customers from CSV / XLSX (ADR-016 imports slice).

HTTP surface:
  * `POST   /api/imports` (multipart)     upload file → S3 + create job + enqueue
  * `GET    /api/imports`                 list this org's jobs (recent first)
  * `GET    /api/imports/{id}`            poll one job (SPA polls until terminal)
  * `GET    /api/imports/template`        canonical column headers for a stub file

The POST only uploads + records the job and hands the heavy lifting
(parse → validate → dedupe → write) to the `process_import` worker, so a
50k-row file never blocks the request. The SPA polls `GET /{id}` until
`status` is `completed` / `failed`.

Two guards keep one tenant from monopolising the single worker:
  * **1-concurrent** — a second upload while one is still pending/
    processing gets 409. Keeps imports serial per org so dedupe sees a
    settled table, and bounds worker load.
  * **daily cap** — more than `import_daily_cap` jobs in a rolling 24h
    gets 429. Stops a script (or a retry storm) from flooding the queue.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.config import get_settings
from app.database import get_db
from app.deps import get_current_org_id, get_current_user
from app.imports import get_spec
from app.models import ImportEntityType, ImportJob, ImportMode, ImportStatus, User
from app.schemas import ImportJobOut, ImportTemplateOut
from app.storage import put_object
from app.worker.queue import enqueue

router = APIRouter(prefix="/api/imports", tags=["imports"])

settings = get_settings()


def _import_object_key(org_id: uuid.UUID, job_id: uuid.UUID) -> str:
    """S3 key for an uploaded import file. Tenant-prefixed like attachments
    so a misconfigured bucket policy keeps the blast radius per-org."""
    return f"org-{org_id}/imports/{job_id}"


@router.get("/template", response_model=ImportTemplateOut)
async def import_template(
    entity_type: ImportEntityType,
    _: User = Depends(get_current_user),
) -> ImportTemplateOut:
    """Canonical headers (required ones suffixed `*`) for a starter file."""
    spec = get_spec(entity_type.value)
    return ImportTemplateOut(entity_type=entity_type, headers=spec.template_headers)


@router.get("", response_model=list[ImportJobOut])
async def list_imports(
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[ImportJobOut]:
    stmt = (
        select(ImportJob)
        .where(ImportJob.organization_id == org_id)
        .order_by(desc(ImportJob.created_at), desc(ImportJob.id))
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [ImportJobOut.model_validate(r) for r in rows]


@router.get("/{import_id}", response_model=ImportJobOut)
async def get_import(
    import_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> ImportJobOut:
    job = (
        await db.execute(
            select(ImportJob).where(
                ImportJob.id == import_id, ImportJob.organization_id == org_id
            )
        )
    ).scalar_one_or_none()
    if job is None:
        # Cross-org access is a 404, never a 403 — don't confirm the id exists.
        raise HTTPException(status_code=404, detail="Import job not found")
    return ImportJobOut.model_validate(job)


@router.post("", response_model=ImportJobOut, status_code=status.HTTP_201_CREATED)
async def create_import(
    entity_type: Annotated[ImportEntityType, Form()],
    file: Annotated[UploadFile, File()],
    mode: Annotated[ImportMode, Form()] = ImportMode.create,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> ImportJobOut:
    body = await file.read()
    size = len(body)
    if size == 0:
        raise HTTPException(status_code=400, detail="Empty upload")
    if size > settings.import_max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.import_max_upload_bytes} bytes",
        )

    # Guard 1 — one in-flight import per org. Keeps imports serial so the
    # worker's dedupe pass sees a settled table, and bounds queue load.
    inflight = (
        await db.execute(
            select(func.count())
            .select_from(ImportJob)
            .where(
                ImportJob.organization_id == org_id,
                ImportJob.status.in_([ImportStatus.pending, ImportStatus.processing]),
            )
        )
    ).scalar_one()
    if inflight:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An import is already in progress. Wait for it to finish.",
        )

    # Guard 2 — rolling-24h per-org cap. Stops a script/retry storm.
    since = datetime.now(UTC) - timedelta(hours=24)
    recent = (
        await db.execute(
            select(func.count())
            .select_from(ImportJob)
            .where(ImportJob.organization_id == org_id, ImportJob.created_at >= since)
        )
    ).scalar_one()
    if recent >= settings.import_daily_cap:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily import limit ({settings.import_daily_cap}) reached. Try again later.",
        )

    job_id = uuid.uuid4()
    key = _import_object_key(org_id, job_id)
    content_type = file.content_type or "application/octet-stream"

    # Upload to S3 FIRST so we never persist a job row pointing at a
    # missing object. A DB failure after this leaves an orphan blob
    # (acceptable — cheaper than the inverse).
    await put_object(key, body, content_type)

    job = ImportJob(
        id=job_id,
        organization_id=org_id,
        created_by_user_id=user.id,
        entity_type=entity_type,
        mode=mode,
        status=ImportStatus.pending,
        filename=file.filename or "import",
        content_type=content_type,
        storage_key=key,
    )
    db.add(job)
    await record_audit(
        db,
        actor=user,
        action="import.created",
        entity_type="import_job",
        entity_id=job_id,
        organization_id=org_id,
        metadata={
            "entity_type": entity_type.value,
            "mode": mode.value,
            "filename": job.filename,
            "size_bytes": size,
        },
    )
    await db.commit()
    await db.refresh(job)

    # Enqueue AFTER commit so the worker can't race ahead of the row it
    # needs to read. dedupe_key guards an accidental double-dispatch of
    # the same job id (React strict-mode double effect, retry-on-timeout).
    await enqueue(
        "process_import",
        str(job_id),
        str(org_id),
        dedupe_key=f"import:{job_id}",
        dedupe_ttl_seconds=3600,
    )
    return ImportJobOut.model_validate(job)

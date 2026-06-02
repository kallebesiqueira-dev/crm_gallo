"""File attachments on Lead / Customer / Deal.

CRUD surface:
  * `POST   /api/attachments` (multipart)        upload + create row
  * `GET    /api/attachments?entity_type=&entity_id=`  list
  * `GET    /api/attachments/{id}/download`      → presigned URL JSON
  * `DELETE /api/attachments/{id}`               soft-delete row + hard-delete blob

Upload flow:
  1. Browser POSTs multipart with `file`, `entity_type`, `entity_id`.
  2. Backend reads the bytes, enforces the size cap, computes sha256,
     uploads to S3 with key `org-{org}/{entity}/{entity_id}/{att_uuid}`,
     then commits the metadata row + a `file_attached` Activity.

Why upload-through-API instead of presigned-PUT-from-browser:
  * Simpler smoke story — one round-trip, one auth path.
  * The 25 MB cap rarely exceeds what the dev MinIO can swallow
    in a single request.
  * A pure presigned-upload would need a separate "claim this key"
    endpoint to bind it to the entity, which would also need anti-
    abuse rate limits (an attacker could otherwise mint signed URLs
    forever). Tracked as a P2 hardening.
"""

import hashlib
import uuid
from datetime import UTC
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.activities import ActivityType, record_activity
from app.audit import record_audit
from app.config import get_settings
from app.database import get_db
from app.deps import ensure_can_mutate, get_current_org_id, get_current_user
from app.models import FileAttachment, User
from app.schemas import FileAttachmentDownloadOut, FileAttachmentOut
from app.storage import delete_object, object_key, presigned_download_url, put_object

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

settings = get_settings()

EntityType = Literal["lead", "customer", "deal", "quote"]


def _serialize(att: FileAttachment, email: str | None, name: str | None) -> FileAttachmentOut:
    return FileAttachmentOut(
        id=att.id,
        entity_type=att.entity_type,
        entity_id=att.entity_id,
        filename=att.filename,
        content_type=att.content_type,
        size_bytes=att.size_bytes,
        sha256=att.sha256,
        uploader_user_id=att.uploader_user_id,
        uploader_email=email,
        uploader_name=name,
        created_at=att.created_at,
    )


async def _get_attachment_or_404(
    db: AsyncSession, attachment_id: uuid.UUID, org_id: uuid.UUID
) -> FileAttachment:
    result = await db.execute(
        select(FileAttachment).where(
            FileAttachment.id == attachment_id,
            FileAttachment.organization_id == org_id,
        )
    )
    att = result.scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return att


@router.get("", response_model=list[FileAttachmentOut])
async def list_attachments(
    entity_type: EntityType,
    entity_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[FileAttachmentOut]:
    uploader = aliased(User)
    stmt = (
        select(FileAttachment, uploader.email, uploader.full_name)
        .outerjoin(uploader, uploader.id == FileAttachment.uploader_user_id)
        .where(
            FileAttachment.organization_id == org_id,
            FileAttachment.entity_type == entity_type,
            FileAttachment.entity_id == entity_id,
        )
        .order_by(desc(FileAttachment.created_at), desc(FileAttachment.id))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return [_serialize(a, e, n) for a, e, n in result.all()]


@router.post(
    "",
    response_model=FileAttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    # FastAPI requires the file + form fields as explicit params; we
    # CANNOT use a Pydantic body model + multipart together.
    entity_type: Annotated[EntityType, Form()],
    entity_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> FileAttachmentOut:
    # Read the bytes in one shot. For our 25 MB cap that's fine in
    # memory; if we ever raise the cap, swap to streamed sha256 +
    # streamed S3 multipart upload.
    body = await file.read()
    size = len(body)
    if size == 0:
        raise HTTPException(status_code=400, detail="Empty upload")
    if size > settings.attachment_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.attachment_max_bytes} bytes",
        )

    sha = hashlib.sha256(body).hexdigest()
    att_id = uuid.uuid4()
    key = object_key(org_id, entity_type, entity_id, att_id)

    # Upload to S3 FIRST. If the bucket write fails we never persist
    # a row pointing at a missing object. The DB commit happens
    # after, so a DB failure leaves an orphan blob (acceptable —
    # cheaper than the inverse).
    await put_object(key, body, file.content_type or "application/octet-stream")

    att = FileAttachment(
        id=att_id,
        organization_id=org_id,
        uploader_user_id=user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        filename=file.filename or "unnamed",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=size,
        sha256=sha,
        storage_key=key,
    )
    db.add(att)
    await db.flush()

    await record_activity(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        activity_type=ActivityType.file_attached,
        organization_id=org_id,
        actor=user,
        content=att.filename,
        metadata={
            "attachment_id": str(att.id),
            "size_bytes": size,
            "content_type": att.content_type,
        },
    )
    await record_audit(
        db,
        actor=user,
        action="attachment.upload",
        entity_type="file_attachment",
        entity_id=att.id,
        organization_id=org_id,
        metadata={
            "target_entity_type": entity_type,
            "target_entity_id": str(entity_id),
            "filename": att.filename,
            "size_bytes": size,
        },
    )
    await db.commit()
    await db.refresh(att)
    return _serialize(att, user.email, user.full_name)


@router.get("/{attachment_id}/download", response_model=FileAttachmentDownloadOut)
async def download_attachment(
    attachment_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> FileAttachmentDownloadOut:
    """Return a short-lived presigned URL. The SPA redirects the
    browser there, and the file streams directly from S3 — no
    bytes flow through this API process."""
    att = await _get_attachment_or_404(db, attachment_id, org_id)
    url = await presigned_download_url(att.storage_key, filename=att.filename)
    return FileAttachmentDownloadOut(url=url, expires_in=settings.s3_download_url_ttl)


# Skip `-> None` annotation on the 204 handler: combined with
# implicit `from __future__ import annotations` elsewhere, FastAPI
# trips a "204 must not have a response body" assertion (see the
# comment on notes.delete_note for the full diagnosis).
@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime

    att = await _get_attachment_or_404(db, attachment_id, org_id)
    # Permissive ownership: uploader OR admin/manager. Same rule as
    # Lead/Note mutations.
    ensure_can_mutate(user, att.uploader_user_id)

    # Hard-delete the blob first — frees storage immediately and is
    # the operation most likely to fail (network to S3). If it errors
    # we don't soft-delete the row, so the user sees a clear failure
    # and can retry. If it succeeds and the DB commit fails, the
    # blob is gone but the row still points at it — the row's next
    # `download` will surface a 404 from S3, which we'd want to
    # handle gracefully (TODO once we have a real error path).
    await delete_object(att.storage_key)

    att.deleted_at = datetime.now(UTC)
    await record_activity(
        db,
        entity_type=att.entity_type,
        entity_id=att.entity_id,
        activity_type=ActivityType.file_removed,
        organization_id=org_id,
        actor=user,
        content=att.filename,
        metadata={"attachment_id": str(att.id)},
    )
    await record_audit(
        db,
        actor=user,
        action="attachment.delete",
        entity_type="file_attachment",
        entity_id=att.id,
        organization_id=org_id,
        metadata={"filename": att.filename},
    )
    await db.commit()

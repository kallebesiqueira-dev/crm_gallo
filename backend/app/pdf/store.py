"""Persist a generated PDF as a `FileAttachment` (ADR-016).

Generated documents reuse the exact same storage path as user uploads:
the bytes go to S3 under the tenant-prefixed object key and a
`FileAttachment` row indexes them. That means a generated deal PDF
shows up in the existing `GET /api/attachments` list and downloads
through the existing presigned-URL endpoint — no new download surface.

The S3 put happens before the row is added (mirror of
`api/attachments.upload_attachment`): if the bucket write fails we never
persist a row pointing at a missing object. The caller owns the commit.
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FileAttachment
from app.storage import object_key, put_object


async def store_pdf_attachment(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    filename: str,
    pdf_bytes: bytes,
    uploader_user_id: uuid.UUID | None = None,
) -> FileAttachment:
    """Upload `pdf_bytes` to S3 and add a `FileAttachment` row for it.

    `uploader_user_id` is None for system-generated documents (the row
    still records who/what via the audit trail at the call site). Adds
    + flushes the row but does NOT commit — the caller's transaction
    decides when the metadata becomes visible.
    """
    sha = hashlib.sha256(pdf_bytes).hexdigest()
    att_id = uuid.uuid4()
    key = object_key(organization_id, entity_type, entity_id, att_id)

    await put_object(key, pdf_bytes, "application/pdf")

    att = FileAttachment(
        id=att_id,
        organization_id=organization_id,
        uploader_user_id=uploader_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        filename=filename,
        content_type="application/pdf",
        size_bytes=len(pdf_bytes),
        sha256=sha,
        storage_key=key,
    )
    db.add(att)
    await db.flush()
    return att

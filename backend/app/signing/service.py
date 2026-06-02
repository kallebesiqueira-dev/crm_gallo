"""Persist the signed artifact + audit trail to S3 (ADR-016).

For the manual provider there is no vendor-returned signed PDF, so the
legal record is the signing audit trail — who typed what name, from which
IP / user-agent, when. We store it as a JSON object in S3 and index it
with a `FileAttachment` (entity_type="signature_request"), reusing the
exact storage + presigned-download path as every other attachment. Real
providers will instead store the vendor's signed PDF + their audit trail
here.

Mirror of `app/pdf/store.store_pdf_attachment`: the S3 put happens before
the row is added, and the caller owns the commit.
"""

from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FileAttachment
from app.storage import object_key, put_object

ENTITY_SIGNATURE_REQUEST = "signature_request"


async def store_signature_artifact(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    request_id: uuid.UUID,
    filename: str,
    audit_trail: dict,
) -> FileAttachment:
    """Upload the signing audit trail as a JSON object and index it with a
    `FileAttachment`. Returns the row (added + flushed, NOT committed)."""
    body = json.dumps(audit_trail, sort_keys=True, default=str).encode("utf-8")
    sha = hashlib.sha256(body).hexdigest()
    att_id = uuid.uuid4()
    key = object_key(organization_id, ENTITY_SIGNATURE_REQUEST, request_id, att_id)

    await put_object(key, body, "application/json")

    att = FileAttachment(
        id=att_id,
        organization_id=organization_id,
        uploader_user_id=None,
        entity_type=ENTITY_SIGNATURE_REQUEST,
        entity_id=request_id,
        filename=filename,
        content_type="application/json",
        size_bytes=len(body),
        sha256=sha,
        storage_key=key,
    )
    db.add(att)
    await db.flush()
    return att

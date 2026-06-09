"""Profile photos for customers, companies and the current user.

  * `GET  /api/avatars/{entity_type}/{entity_id}`  → {"url": presigned | null}
  * `POST /api/avatars/{entity_type}/{entity_id}`  (multipart `file`) → {"url"}

`entity_type` is customer | company | user. The `user` target is restricted to
the caller's OWN row (you can only set your own photo). Images live in the same
S3 bucket as attachments, under a fixed per-entity key so a re-upload overwrites
the old photo; clients render the returned time-limited presigned URL inline.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.config import get_settings
from app.database import get_db
from app.deps import get_current_org_id, get_current_user
from app.models import Company, Customer, User
from app.storage import presigned_download_url, put_object

router = APIRouter(prefix="/api/avatars", tags=["avatars"])

settings = get_settings()

AvatarEntity = Literal["customer", "company", "user"]
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


async def _resolve(
    entity_type: str,
    entity_id: uuid.UUID,
    user: User,
    org_id: uuid.UUID,
    db: AsyncSession,
) -> User | Customer | Company:
    """The row whose avatar we're reading/writing, or 404. `user` is locked
    to the caller; customer/company are org-scoped."""
    if entity_type == "user":
        if entity_id != user.id:
            raise HTTPException(status_code=404, detail="Not found")
        return user
    if entity_type == "customer":
        obj: Customer | Company | None = (
            await db.execute(
                select(Customer).where(Customer.id == entity_id, Customer.organization_id == org_id)
            )
        ).scalar_one_or_none()
    elif entity_type == "company":
        obj = (
            await db.execute(
                select(Company).where(Company.id == entity_id, Company.organization_id == org_id)
            )
        ).scalar_one_or_none()
    else:
        raise HTTPException(status_code=404, detail="Unknown entity")
    if obj is None or obj.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


def _key(entity_type: str, entity_id: uuid.UUID, org_id: uuid.UUID) -> str:
    if entity_type == "user":
        return f"avatars/user/{entity_id}"
    return f"org-{org_id}/avatars/{entity_type}/{entity_id}"


@router.get("/{entity_type}/{entity_id}")
async def get_avatar(
    entity_type: AvatarEntity,
    entity_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | None]:
    obj = await _resolve(entity_type, entity_id, user, org_id, db)
    url = await presigned_download_url(obj.avatar_key) if obj.avatar_key else None
    return {"url": url}


@router.post("/{entity_type}/{entity_id}")
async def upload_avatar(
    entity_type: AvatarEntity,
    entity_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | None]:
    obj = await _resolve(entity_type, entity_id, user, org_id, db)
    if (file.content_type or "") not in _ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Avatar must be a JPEG, PNG, WebP or GIF image")
    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="Empty upload")
    if len(body) > settings.attachment_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image too large"
        )

    key = _key(entity_type, entity_id, org_id)
    await put_object(key, body, file.content_type or "image/png")
    obj.avatar_key = key
    await record_audit(
        db,
        actor=user,
        action=f"{entity_type}.avatar.update",
        entity_type=entity_type,
        entity_id=entity_id,
        organization_id=org_id,
    )
    await db.commit()
    return {"url": await presigned_download_url(key)}

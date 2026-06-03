"""API-key management CRUD — admin-only, per-org (ADR-016).

Keys are MINTED here by an admin via the browser (cookie + CSRF), the
same trust model as outgoing webhooks. The minted token is the bearer
credential the Public API (`/api/v1`) validates in `app.api_auth`.

Secret handling mirrors `WebhookEndpoint.secret`:
  * The plaintext token is generated server-side and returned ONCE on
    create (`ApiKeyCreated.token`). After that only `display_prefix`
    (a non-secret label) is ever exposed.
  * At rest we store `sha256(token)` — a leaked DB row can't be turned
    back into a usable key.

Revocation is soft (`revoked_at` timestamp, not a row delete) so the
audit trail of which key did what survives. A revoked key is still
listed (greyed out in the UI) so an admin can see it was retired.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api_keys import decode_scopes, encode_scopes, mint_token
from app.audit import record_audit
from app.database import get_db
from app.deps import get_current_org_id, require_roles
from app.models import ApiKey, User, UserRole
from app.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


def _to_out(key: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=key.id,
        organization_id=key.organization_id,
        name=key.name,
        display_prefix=key.display_prefix,
        scopes=sorted(decode_scopes(key.scopes), key=lambda s: s.value),
        last_used_at=key.last_used_at,
        expires_at=key.expires_at,
        revoked_at=key.revoked_at,
        created_at=key.created_at,
    )


async def _get_or_404(db: AsyncSession, key_id: uuid.UUID, org_id: uuid.UUID) -> ApiKey:
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.organization_id == org_id)
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    return key


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[ApiKeyOut]:
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.organization_id == org_id)
        .order_by(desc(ApiKey.created_at))
    )
    return [_to_out(k) for k in result.scalars().all()]


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreated:
    token, hashed, display_prefix = mint_token(org_id)
    key = ApiKey(
        organization_id=org_id,
        name=payload.name,
        hashed_key=hashed,
        display_prefix=display_prefix,
        scopes=encode_scopes(payload.scopes),
        expires_at=payload.expires_at,
        created_by_user_id=user.id,
    )
    db.add(key)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="api_key.create",
        entity_type="api_key",
        entity_id=key.id,
        organization_id=org_id,
        metadata={"name": key.name, "scopes": [s.value for s in payload.scopes]},
    )
    await db.commit()
    await db.refresh(key)
    base = _to_out(key)
    return ApiKeyCreated(**base.model_dump(), token=token)


@router.get("/{key_id}", response_model=ApiKeyOut)
async def get_api_key(
    key_id: uuid.UUID,
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyOut:
    return _to_out(await _get_or_404(db, key_id, org_id))


@router.delete("/{key_id}", response_model=ApiKeyOut)
async def revoke_api_key(
    key_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyOut:
    """Soft-revoke: stamp `revoked_at`. Idempotent — revoking an already
    revoked key is a no-op that returns the current state. Returns the
    key (not 204) so the UI can reflect the revoked timestamp without a
    re-fetch."""
    key = await _get_or_404(db, key_id, org_id)
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        await record_audit(
            db,
            actor=user,
            action="api_key.revoke",
            entity_type="api_key",
            entity_id=key.id,
            organization_id=org_id,
            metadata={"name": key.name},
        )
        await db.commit()
        await db.refresh(key)
    return _to_out(key)

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.custom_fields import ENTITY_TYPES
from app.database import get_db
from app.deps import get_current_org_id, get_current_user, require_roles
from app.models import (
    Company,
    Customer,
    Deal,
    EntityTag,
    Lead,
    Tag,
    User,
    UserRole,
)
from app.schemas import (
    EntityTagsOut,
    TagAssign,
    TagBulk,
    TagCreate,
    TagOut,
    TagUpdate,
)

router = APIRouter(prefix="/api/tags", tags=["tags"])

# Renaming/deleting a tag changes it for everyone, so gate those to
# admin/manager. Creating, listing, and (un)assigning are daily-driver
# actions open to any member.
manage = require_roles(UserRole.admin, UserRole.manager)

# Polymorphic target registry — maps the entity_type slug to its model so
# we can verify an entity exists (and is in-org, not soft-deleted) before
# attaching a tag. Mirrors ENTITY_TYPES in app/custom_fields.py.
_ENTITY_MODELS: dict[str, type] = {
    "lead": Lead,
    "customer": Customer,
    "deal": Deal,
    "company": Company,
}


def _raise_for_duplicate_name(exc: IntegrityError) -> None:
    if "uq_tag_org_name" in str(exc.orig):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A tag with this name already exists.",
        ) from exc
    raise exc


async def _get_tag_or_404(db: AsyncSession, tag_id: uuid.UUID, org_id: uuid.UUID) -> Tag:
    result = await db.execute(
        select(Tag).where(Tag.id == tag_id, Tag.organization_id == org_id)
    )
    tag = result.scalar_one_or_none()
    if not tag or tag.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag


async def _existing_entity_ids(
    db: AsyncSession, org_id: uuid.UUID, entity_type: str, ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Subset of `ids` that exist in-org for this entity type (the global
    soft-delete filter auto-excludes deleted rows)."""
    model = _ENTITY_MODELS[entity_type]
    if not ids:
        return set()
    rows = await db.execute(
        select(model.id).where(model.organization_id == org_id, model.id.in_(ids))
    )
    return set(rows.scalars().all())


async def _tags_for(
    db: AsyncSession, org_id: uuid.UUID, entity_type: str, ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[Tag]]:
    """Batch-load live tags for a set of entities, keyed by entity_id."""
    if not ids:
        return {}
    rows = await db.execute(
        select(EntityTag.entity_id, Tag)
        .join(Tag, Tag.id == EntityTag.tag_id)
        .where(
            EntityTag.organization_id == org_id,
            EntityTag.entity_type == entity_type,
            EntityTag.entity_id.in_(ids),
            Tag.deleted_at.is_(None),
        )
        .order_by(Tag.name.asc())
    )
    out: dict[uuid.UUID, list[Tag]] = defaultdict(list)
    for entity_id, tag in rows.all():
        out[entity_id].append(tag)
    return out


def _validate_entity_type(entity_type: str) -> None:
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=422, detail="Unknown entity_type")


# ---------- Tag definitions ----------
@router.get("", response_model=list[TagOut])
async def list_tags(
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[Tag]:
    rows = await db.execute(
        select(Tag).where(Tag.organization_id == org_id).order_by(Tag.name.asc())
    )
    return list(rows.scalars().all())


@router.post("", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(
    payload: TagCreate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Tag:
    tag = Tag(**payload.model_dump(), organization_id=org_id)
    db.add(tag)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        _raise_for_duplicate_name(exc)
    await record_audit(
        db,
        actor=user,
        action="tag.create",
        entity_type="tag",
        entity_id=tag.id,
        organization_id=org_id,
        metadata={"name": tag.name},
    )
    await db.commit()
    await db.refresh(tag)
    return tag


@router.patch("/{tag_id}", response_model=TagOut)
async def update_tag(
    tag_id: uuid.UUID,
    payload: TagUpdate,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Tag:
    tag = await _get_tag_or_404(db, tag_id, org_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(tag, field, value)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        _raise_for_duplicate_name(exc)
    await record_audit(
        db,
        actor=user,
        action="tag.update",
        entity_type="tag",
        entity_id=tag.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    await db.refresh(tag)
    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    tag_id: uuid.UUID,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    tag = await _get_tag_or_404(db, tag_id, org_id)
    # Soft-delete the tag but hard-remove its attachments so no chips
    # linger on entities pointing at a dead tag.
    await db.execute(
        delete(EntityTag).where(
            EntityTag.tag_id == tag.id, EntityTag.organization_id == org_id
        )
    )
    tag.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="tag.soft_delete",
        entity_type="tag",
        entity_id=tag.id,
        organization_id=org_id,
    )
    await db.commit()


# ---------- Assignments ----------
@router.get("/assignments", response_model=list[EntityTagsOut])
async def list_assignments(
    entity_type: str = Query(...),
    entity_ids: str = Query(..., description="Comma-separated entity UUIDs"),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[EntityTagsOut]:
    _validate_entity_type(entity_type)
    try:
        ids = [uuid.UUID(x) for x in entity_ids.split(",") if x.strip()]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid entity_ids") from exc
    by_entity = await _tags_for(db, org_id, entity_type, ids)
    return [
        EntityTagsOut(
            entity_id=eid,
            tags=[TagOut.model_validate(t) for t in by_entity.get(eid, [])],
        )
        for eid in ids
    ]


@router.post("/assign", response_model=list[TagOut])
async def assign_tag(
    payload: TagAssign,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[Tag]:
    await _get_tag_or_404(db, payload.tag_id, org_id)
    existing = await _existing_entity_ids(
        db, org_id, payload.entity_type, [payload.entity_id]
    )
    if payload.entity_id not in existing:
        raise HTTPException(status_code=404, detail="Entity not found")
    # Idempotent: unique constraint means a re-assign is a no-op.
    link = EntityTag(
        organization_id=org_id,
        tag_id=payload.tag_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
    )
    db.add(link)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()  # already attached — fall through to return current
    await db.commit()
    by_entity = await _tags_for(db, org_id, payload.entity_type, [payload.entity_id])
    return by_entity.get(payload.entity_id, [])


@router.post("/unassign", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_tag(
    payload: TagAssign,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.execute(
        delete(EntityTag).where(
            EntityTag.organization_id == org_id,
            EntityTag.tag_id == payload.tag_id,
            EntityTag.entity_type == payload.entity_type,
            EntityTag.entity_id == payload.entity_id,
        )
    )
    await db.commit()


@router.post("/bulk")
async def bulk_tag(
    payload: TagBulk,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add or remove a set of tags across a set of entities of one type."""
    # Only operate on tags + entities that actually exist in-org.
    tag_rows = await db.execute(
        select(Tag.id).where(
            Tag.organization_id == org_id,
            Tag.id.in_(payload.tag_ids),
            Tag.deleted_at.is_(None),
        )
    )
    valid_tag_ids = set(tag_rows.scalars().all())
    valid_entity_ids = await _existing_entity_ids(
        db, org_id, payload.entity_type, payload.entity_ids
    )

    if payload.action == "remove":
        result = await db.execute(
            delete(EntityTag).where(
                EntityTag.organization_id == org_id,
                EntityTag.tag_id.in_(valid_tag_ids or [uuid.uuid4()]),
                EntityTag.entity_type == payload.entity_type,
                EntityTag.entity_id.in_(valid_entity_ids or [uuid.uuid4()]),
            )
        )
        affected = result.rowcount or 0
    else:
        # Add: skip pairs that already exist to stay idempotent.
        existing_pairs = await db.execute(
            select(EntityTag.tag_id, EntityTag.entity_id).where(
                EntityTag.organization_id == org_id,
                EntityTag.entity_type == payload.entity_type,
                EntityTag.tag_id.in_(valid_tag_ids or [uuid.uuid4()]),
                EntityTag.entity_id.in_(valid_entity_ids or [uuid.uuid4()]),
            )
        )
        have = set(existing_pairs.all())
        affected = 0
        for tid in valid_tag_ids:
            for eid in valid_entity_ids:
                if (tid, eid) in have:
                    continue
                db.add(
                    EntityTag(
                        organization_id=org_id,
                        tag_id=tid,
                        entity_type=payload.entity_type,
                        entity_id=eid,
                    )
                )
                affected += 1

    await record_audit(
        db,
        actor=user,
        action=f"tag.bulk_{payload.action}",
        entity_type="tag",
        entity_id=None,
        organization_id=org_id,
        metadata={
            "entity_type": payload.entity_type,
            "tags": len(valid_tag_ids),
            "entities": len(valid_entity_ids),
            "affected": affected,
        },
    )
    await db.commit()
    return {"affected": affected}

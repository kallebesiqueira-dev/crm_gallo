import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.custom_fields import ENTITY_TYPES
from app.database import get_db
from app.deps import get_current_org_id, get_current_user, require_roles
from app.models import CustomFieldDefinition, CustomFieldType, User, UserRole
from app.schemas import (
    CustomFieldDefinitionCreate,
    CustomFieldDefinitionOut,
    CustomFieldDefinitionUpdate,
)

router = APIRouter(prefix="/api/custom-fields", tags=["custom-fields"])

# Managing the schema is an admin/manager job; reading definitions is open
# to any member (every entity form needs them to render).
manage = require_roles(UserRole.admin, UserRole.manager)


def _raise_for_duplicate_key(exc: IntegrityError) -> None:
    if "uq_custom_field_def_org_entity_key" in str(exc.orig):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A field with this key already exists for this entity type.",
        ) from exc
    raise exc


async def _get_or_404(
    db: AsyncSession, def_id: uuid.UUID, org_id: uuid.UUID
) -> CustomFieldDefinition:
    result = await db.execute(
        select(CustomFieldDefinition).where(
            CustomFieldDefinition.id == def_id,
            CustomFieldDefinition.organization_id == org_id,
        )
    )
    defn = result.scalar_one_or_none()
    if not defn or defn.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Custom field not found")
    return defn


@router.get("", response_model=list[CustomFieldDefinitionOut])
async def list_definitions(
    entity_type: str | None = Query(default=None),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[CustomFieldDefinition]:
    stmt = select(CustomFieldDefinition).where(
        CustomFieldDefinition.organization_id == org_id
    )
    if entity_type is not None:
        if entity_type not in ENTITY_TYPES:
            raise HTTPException(status_code=422, detail="Unknown entity_type")
        stmt = stmt.where(CustomFieldDefinition.entity_type == entity_type)
    stmt = stmt.order_by(
        CustomFieldDefinition.entity_type.asc(),
        CustomFieldDefinition.position.asc(),
        CustomFieldDefinition.label.asc(),
    )
    return list((await db.execute(stmt)).scalars().all())


@router.post(
    "", response_model=CustomFieldDefinitionOut, status_code=status.HTTP_201_CREATED
)
async def create_definition(
    payload: CustomFieldDefinitionCreate,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> CustomFieldDefinition:
    defn = CustomFieldDefinition(**payload.model_dump(), organization_id=org_id)
    db.add(defn)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        _raise_for_duplicate_key(exc)
    await record_audit(
        db,
        actor=user,
        action="custom_field.create",
        entity_type="custom_field_definition",
        entity_id=defn.id,
        organization_id=org_id,
        metadata={"entity_type": defn.entity_type, "key": defn.key},
    )
    await db.commit()
    await db.refresh(defn)
    return defn


@router.patch("/{def_id}", response_model=CustomFieldDefinitionOut)
async def update_definition(
    def_id: uuid.UUID,
    payload: CustomFieldDefinitionUpdate,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> CustomFieldDefinition:
    defn = await _get_or_404(db, def_id, org_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(defn, field, value)
    # Keep the select/options invariant: only select/multiselect carry
    # options; everything else clears them.
    if defn.field_type not in (CustomFieldType.select, CustomFieldType.multiselect):
        defn.options = None
    elif not defn.options:
        raise HTTPException(
            status_code=422,
            detail="select / multiselect fields require a non-empty options list",
        )
    await record_audit(
        db,
        actor=user,
        action="custom_field.update",
        entity_type="custom_field_definition",
        entity_id=defn.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    await db.refresh(defn)
    return defn


@router.delete("/{def_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_definition(
    def_id: uuid.UUID,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    defn = await _get_or_404(db, def_id, org_id)
    defn.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="custom_field.soft_delete",
        entity_type="custom_field_definition",
        entity_id=defn.id,
        organization_id=org_id,
    )
    await db.commit()

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.database import get_db
from app.deps import get_current_org_id, get_current_user, require_roles
from app.models import User, UserRole, WebForm
from app.schemas import WebFormCreate, WebFormOut, WebFormUpdate
from app.web_forms import mint_token

router = APIRouter(prefix="/api/forms", tags=["forms"])

# Minting/editing/deleting a capture form changes the org's public front
# door, so gate mutations to admin/manager. Listing is read-only and open
# to any member (same bar as tags/duplicates management).
manage = require_roles(UserRole.admin, UserRole.manager)


async def _get_form_or_404(db: AsyncSession, form_id: uuid.UUID, org_id: uuid.UUID) -> WebForm:
    result = await db.execute(
        select(WebForm).where(WebForm.id == form_id, WebForm.organization_id == org_id)
    )
    form = result.scalar_one_or_none()
    if form is None:
        raise HTTPException(status_code=404, detail="Form not found")
    return form


@router.get("", response_model=list[WebFormOut])
async def list_forms(
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[WebForm]:
    rows = await db.execute(
        select(WebForm).where(WebForm.organization_id == org_id).order_by(WebForm.created_at.desc())
    )
    return list(rows.scalars().all())


@router.post("", response_model=WebFormOut, status_code=status.HTTP_201_CREATED)
async def create_form(
    payload: WebFormCreate,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> WebForm:
    form = WebForm(
        **payload.model_dump(),
        organization_id=org_id,
        token=mint_token(org_id),
        created_by_user_id=user.id,
    )
    db.add(form)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="web_form.create",
        entity_type="web_form",
        entity_id=form.id,
        organization_id=org_id,
        metadata={"name": form.name},
    )
    await db.commit()
    await db.refresh(form)
    return form


@router.patch("/{form_id}", response_model=WebFormOut)
async def update_form(
    form_id: uuid.UUID,
    payload: WebFormUpdate,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> WebForm:
    form = await _get_form_or_404(db, form_id, org_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(form, field, value)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="web_form.update",
        entity_type="web_form",
        entity_id=form.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    await db.refresh(form)
    return form


@router.delete("/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_form(
    form_id: uuid.UUID,
    user: User = Depends(manage),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    form = await _get_form_or_404(db, form_id, org_id)
    # Hard delete — no soft-delete on web_forms; an `active` toggle pauses
    # capture, full removal retires the embed.
    await db.delete(form)
    await record_audit(
        db,
        actor=user,
        action="web_form.delete",
        entity_type="web_form",
        entity_id=form_id,
        organization_id=org_id,
    )
    await db.commit()

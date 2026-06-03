"""Merge-field document templates — CRUD + field catalog (ADR-016).

Reusable, operator-authored document bodies with `{{ token }}` merge
fields. Reading is open to any org member; create / update / delete are
gated to admin + manager (these seed legal contract text — a sales agent
shouldn't be editing the boilerplate). Applying a template to a contract
lives in `app/api/contracts.py` (it mutates a contract, not a template).

`is_default` is at most one live template per (org, doc_type) — enforced
here (toggling on clears the previous default), not in the schema.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.database import get_db
from app.deps import get_current_org_id, get_current_user, require_roles
from app.documents import FIELD_CATALOG
from app.logging_setup import get_logger
from app.models import DocumentTemplate, DocumentType, User, UserRole
from app.schemas import (
    DocumentTemplateCreate,
    DocumentTemplateOut,
    DocumentTemplateUpdate,
    MergeFieldOut,
)

router = APIRouter(prefix="/api/document-templates", tags=["document-templates"])
log = get_logger(__name__)

# Create/update/delete: admins + managers only.
require_manager = require_roles(UserRole.admin, UserRole.manager)


async def _get_template_or_404(
    db: AsyncSession, template_id: uuid.UUID, org_id: uuid.UUID
) -> DocumentTemplate:
    tpl = (
        await db.execute(
            select(DocumentTemplate).where(
                DocumentTemplate.id == template_id,
                DocumentTemplate.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if not tpl or tpl.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl


async def _clear_other_defaults(
    db: AsyncSession,
    org_id: uuid.UUID,
    doc_type: DocumentType,
    keep_id: uuid.UUID | None,
) -> None:
    """Demote any other default of this (org, doc_type)."""
    others = (
        await db.execute(
            select(DocumentTemplate).where(
                DocumentTemplate.organization_id == org_id,
                DocumentTemplate.doc_type == doc_type,
                DocumentTemplate.is_default.is_(True),
            )
        )
    ).scalars().all()
    for other in others:
        if keep_id is None or other.id != keep_id:
            other.is_default = False


@router.get("/fields", response_model=list[MergeFieldOut])
async def list_merge_fields(
    doc_type: DocumentType = Query(default=DocumentType.contract),
    _: User = Depends(get_current_user),
) -> list[MergeFieldOut]:
    """The allow-listed merge-field catalog for the UI field picker.

    `doc_type` is accepted for forward-compatibility; only `contract` is
    wired today, so the catalog is the same for every value.
    """
    return [MergeFieldOut(**f.__dict__) for f in FIELD_CATALOG]


@router.get("", response_model=list[DocumentTemplateOut])
async def list_templates(
    doc_type: DocumentType | None = Query(default=None),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentTemplate]:
    stmt = select(DocumentTemplate).where(DocumentTemplate.organization_id == org_id)
    if doc_type is not None:
        stmt = stmt.where(DocumentTemplate.doc_type == doc_type)
    stmt = stmt.order_by(DocumentTemplate.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


@router.get("/{template_id}", response_model=DocumentTemplateOut)
async def get_template(
    template_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> DocumentTemplate:
    return await _get_template_or_404(db, template_id, org_id)


@router.post("", response_model=DocumentTemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: DocumentTemplateCreate,
    user: User = Depends(require_manager),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> DocumentTemplate:
    tpl = DocumentTemplate(
        organization_id=org_id,
        doc_type=payload.doc_type,
        name=payload.name,
        body=payload.body,
        is_default=payload.is_default,
        created_by_user_id=user.id,
    )
    db.add(tpl)
    await db.flush()
    if tpl.is_default:
        await _clear_other_defaults(db, org_id, tpl.doc_type, keep_id=tpl.id)

    await record_audit(
        db,
        actor=user,
        action="document_template.create",
        entity_type="document_template",
        entity_id=tpl.id,
        organization_id=org_id,
        metadata={"name": tpl.name, "doc_type": tpl.doc_type.value},
    )
    await db.commit()
    return await _get_template_or_404(db, tpl.id, org_id)


@router.patch("/{template_id}", response_model=DocumentTemplateOut)
async def update_template(
    template_id: uuid.UUID,
    payload: DocumentTemplateUpdate,
    user: User = Depends(require_manager),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> DocumentTemplate:
    tpl = await _get_template_or_404(db, template_id, org_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(tpl, field, value)
    if changes.get("is_default") is True:
        await _clear_other_defaults(db, org_id, tpl.doc_type, keep_id=tpl.id)

    await record_audit(
        db,
        actor=user,
        action="document_template.update",
        entity_type="document_template",
        entity_id=tpl.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    return await _get_template_or_404(db, tpl.id, org_id)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    user: User = Depends(require_manager),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    tpl = await _get_template_or_404(db, template_id, org_id)
    tpl.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="document_template.soft_delete",
        entity_type="document_template",
        entity_id=tpl.id,
        organization_id=org_id,
    )
    await db.commit()

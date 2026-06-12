"""GDPR right-to-erasure + data-portability endpoints (plan.md §5).

Two operations per contact-bearing entity (Lead, Customer), admin-only:

  POST /api/{leads|customers}/{id}/forget
      Right to erasure. Anonymizes every PII column in place — the row
      and its id SURVIVE so the audit trail keeps an anchor (TD-33's
      "opaque id + erased PII projection") — then soft-deletes it so it
      leaves every list. Attached notes are hard-deleted (their body is
      free-form PII); the entity's timeline keeps its event skeleton
      but loses content/metadata. Idempotent: forgetting twice is a
      no-op with the same response.

  GET /api/{leads|customers}/{id}/export
      Data portability. One JSON document with the entity's stored
      fields, its notes, its timeline and (for customers) associated
      deals — what we'd hand the data subject on request.

Known residuals after /forget (documented, follow-ups):
  * S3/R2 avatar objects (only the key is cleared here)
  * WhatsApp message bodies in `messages`
  * PII embedded in historical audit_logs metadata (TD-33)

Self-contained module — local helpers, no shared-schema changes — so
it composes with the in-flight work on models.py/schemas.py.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.database import get_db
from app.deps import get_current_org_id, require_roles
from app.models import Activity, Customer, Deal, Lead, Note, Organization, User, UserRole

router = APIRouter(prefix="/api", tags=["gdpr"])

_ANON_FIRST = "Anonymized"

# Per-entity erasure recipe: (model, activities/notes entity string,
# columns nulled out). first_name/last_name are NOT NULL → fixed
# placeholders; everything else nullable → None; custom_fields can
# carry arbitrary PII → emptied.
_LEAD_WIPE = (
    "email",
    "phone",
    "company",
    "industry",
    "country",
    "company_size",
    "budget",
    "source",
    "notes",
)
_CUSTOMER_WIPE = (
    "email",
    "phone",
    "company",
    "industry",
    "country",
    "address",
    "website",
    "notes",
    "avatar_key",
    "ai_summary",
    "ai_summary_updated_at",
)


async def _get_or_404(db: AsyncSession, model, entity_id: uuid.UUID, org_id: uuid.UUID):
    row = (
        await db.execute(
            select(model)
            .where(model.id == entity_id, model.organization_id == org_id)
            .execution_options(include_deleted=True)  # forget must reach trashed rows too
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return row


async def _forget(
    db: AsyncSession,
    *,
    model,
    entity_str: str,
    wipe_fields: tuple[str, ...],
    entity_id: uuid.UUID,
    org_id: uuid.UUID,
    # None when the retention sweep (no human actor) drives the erasure.
    user: User | None,
    via: str = "api",
) -> dict[str, Any]:
    row = await _get_or_404(db, model, entity_id, org_id)

    row.first_name = _ANON_FIRST
    row.last_name = str(row.id)[:8]  # NOT NULL + keeps rows distinguishable in audit views
    for field in wipe_fields:
        setattr(row, field, None)
    row.custom_fields = {}
    row.version = row.version + 1
    if row.deleted_at is None:
        row.deleted_at = datetime.now(UTC)

    # Notes are free-form PII — remove them outright (hard delete, not
    # trash: an erasure request can't leave the text recoverable).
    await db.execute(
        delete(Note)
        .where(
            Note.organization_id == org_id,
            Note.entity_type == entity_str,
            Note.entity_id == entity_id,
        )
        # Already-trashed notes must not survive an erasure request —
        # opt out of the SoftDeleteMixin global filter.
        .execution_options(include_deleted=True)
    )
    # Timeline keeps its skeleton (types + timestamps prove WHAT
    # happened) but loses anything quotable.
    await db.execute(
        update(Activity)
        .where(
            Activity.organization_id == org_id,
            Activity.entity_type == entity_str,
            Activity.entity_id == entity_id,
        )
        .values(content=None, metadata_json=None)
    )

    # Metadata intentionally PII-free: just how the erasure was driven
    # ("api" = an admin clicked, "retention" = the daily policy sweep).
    await record_audit(
        db,
        actor=user,
        action=f"{entity_str}.gdpr_forget",
        entity_type=entity_str,
        entity_id=entity_id,
        organization_id=org_id,
        metadata={"via": via},
    )
    await db.commit()
    return {"status": "forgotten", "id": str(entity_id)}


def _row_to_dict(row, fields: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in fields:
        value = getattr(row, f)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, uuid.UUID):
            value = str(value)
        out[f] = value
    return out


_LEAD_EXPORT = (
    "id",
    "first_name",
    "last_name",
    "email",
    "phone",
    "company",
    "industry",
    "country",
    "company_size",
    "budget",
    "source",
    "notes",
    "stage",
    "custom_fields",
    "created_at",
    "updated_at",
)
_CUSTOMER_EXPORT = (
    "id",
    "first_name",
    "last_name",
    "email",
    "phone",
    "company",
    "industry",
    "country",
    "address",
    "website",
    "notes",
    "custom_fields",
    "created_at",
    "updated_at",
)


async def _export(
    db: AsyncSession,
    *,
    model,
    entity_str: str,
    export_fields: tuple[str, ...],
    entity_id: uuid.UUID,
    org_id: uuid.UUID,
    user: User,
) -> dict[str, Any]:
    row = await _get_or_404(db, model, entity_id, org_id)

    notes = (
        (
            await db.execute(
                select(Note).where(
                    Note.organization_id == org_id,
                    Note.entity_type == entity_str,
                    Note.entity_id == entity_id,
                )
            )
        )
        .scalars()
        .all()
    )
    activities = (
        (
            await db.execute(
                select(Activity)
                .where(
                    Activity.organization_id == org_id,
                    Activity.entity_type == entity_str,
                    Activity.entity_id == entity_id,
                )
                .order_by(Activity.created_at)
            )
        )
        .scalars()
        .all()
    )

    payload: dict[str, Any] = {
        "entity_type": entity_str,
        "exported_at": datetime.now(UTC).isoformat(),
        entity_str: _row_to_dict(row, export_fields),
        "notes": [{"body": n.body, "created_at": n.created_at.isoformat()} for n in notes],
        "timeline": [
            {
                "type": a.type,
                "content": a.content,
                "metadata": json.loads(a.metadata_json) if a.metadata_json else None,
                "created_at": a.created_at.isoformat(),
            }
            for a in activities
        ],
    }
    if model is Customer:
        deals = (
            (
                await db.execute(
                    select(Deal).where(
                        Deal.organization_id == org_id, Deal.customer_id == entity_id
                    )
                )
            )
            .scalars()
            .all()
        )
        payload["deals"] = [
            {
                "id": str(d.id),
                "title": d.title,
                "stage": d.stage.value,
                "value": float(d.value),
                "created_at": d.created_at.isoformat(),
            }
            for d in deals
        ]

    await record_audit(
        db,
        actor=user,
        action=f"{entity_str}.gdpr_export",
        entity_type=entity_str,
        entity_id=entity_id,
        organization_id=org_id,
        commit=True,
    )
    return payload


# ---------- Routes (admin-only: erasure is destructive, export hands
# over everything we hold on a person — both are DPO-desk operations,
# not day-to-day sales actions) ----------


@router.post("/leads/{lead_id}/forget")
async def forget_lead(
    lead_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _forget(
        db,
        model=Lead,
        entity_str="lead",
        wipe_fields=_LEAD_WIPE,
        entity_id=lead_id,
        org_id=org_id,
        user=user,
    )


@router.get("/leads/{lead_id}/export")
async def export_lead(
    lead_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _export(
        db,
        model=Lead,
        entity_str="lead",
        export_fields=_LEAD_EXPORT,
        entity_id=lead_id,
        org_id=org_id,
        user=user,
    )


@router.post("/customers/{customer_id}/forget")
async def forget_customer(
    customer_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _forget(
        db,
        model=Customer,
        entity_str="customer",
        wipe_fields=_CUSTOMER_WIPE,
        entity_id=customer_id,
        org_id=org_id,
        user=user,
    )


@router.get("/customers/{customer_id}/export")
async def export_customer(
    customer_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _export(
        db,
        model=Customer,
        entity_str="customer",
        export_fields=_CUSTOMER_EXPORT,
        entity_id=customer_id,
        org_id=org_id,
        user=user,
    )


# ---------- Retention policy (plan.md §5, second half) ----------


class GdprSettingsOut(BaseModel):
    retention_months: int | None


class GdprSettingsIn(BaseModel):
    # 1..120 months; null switches retention off. The floor guards the
    # footgun of a 0/negative value silently anonymizing everything.
    retention_months: int | None = Field(default=None, ge=1, le=120)


@router.get("/gdpr/settings", response_model=GdprSettingsOut)
async def get_gdpr_settings(
    _: User = Depends(require_roles(UserRole.admin)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> GdprSettingsOut:
    org = await db.get(Organization, org_id)
    return GdprSettingsOut(retention_months=org.retention_months if org else None)


@router.patch("/gdpr/settings", response_model=GdprSettingsOut)
async def update_gdpr_settings(
    payload: GdprSettingsIn,
    user: User = Depends(require_roles(UserRole.admin)),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> GdprSettingsOut:
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    previous = org.retention_months
    org.retention_months = payload.retention_months
    await record_audit(
        db,
        actor=user,
        action="org.gdpr_settings_update",
        entity_type="organization",
        entity_id=org_id,
        organization_id=org_id,
        metadata={"retention_months": payload.retention_months, "previous": previous},
    )
    await db.commit()
    return GdprSettingsOut(retention_months=org.retention_months)


# Hard cap per org per sweep — a freshly-enabled 2-year policy on a
# 50k-lead org anonymizes in daily 200-lead bites instead of one
# multi-minute transaction storm.
RETENTION_SWEEP_LIMIT = 200


async def enforce_org_retention(
    db: AsyncSession,
    org_id: uuid.UUID,
    months: int,
    limit: int = RETENTION_SWEEP_LIMIT,
) -> int:
    """Anonymize this org's LEADS idle past the policy cutoff, via the
    same `_forget` core as POST /forget (notes purged, timeline
    stripped, audit row `lead.gdpr_forget` via=retention). Leads only
    by design: customers are paying relationships — auto-erasing them
    needs a human. Caller (the worker) has set the RLS GUC. Returns
    the number anonymized; already-forgotten rows are naturally
    excluded by the soft-delete filter."""
    cutoff = datetime.now(UTC) - timedelta(days=months * 30)
    lead_ids = (
        (
            await db.execute(
                select(Lead.id)
                .where(Lead.organization_id == org_id, Lead.updated_at < cutoff)
                .order_by(Lead.updated_at)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    for lead_id in lead_ids:
        await _forget(
            db,
            model=Lead,
            entity_str="lead",
            wipe_fields=_LEAD_WIPE,
            entity_id=lead_id,
            org_id=org_id,
            user=None,
            via="retention",
        )
    return len(lead_ids)

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.activities import ENTITY_COMPANY, ActivityType, record_activity
from app.api._concurrency import check_if_match
from app.audit import record_audit
from app.custom_fields import validate_custom_fields
from app.database import get_db
from app.deps import ensure_can_mutate, get_current_org_id, get_current_user
from app.models import Company, Customer, Deal, Lead, User
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, CursorPage, paginate
from app.schemas import (
    CompanyCreate,
    CompanyOut,
    CompanyUpdate,
    CustomerOut,
    DealOut,
    LeadOut,
)

router = APIRouter(prefix="/api/companies", tags=["companies"])


# Tenant-scoped via `get_current_org_id` — see customers.py for the
# enforcement model. `organization_id` is set server-side on create and
# stripped on update; cross-org reads return 404, not 403.


def _raise_for_duplicate_name(exc: IntegrityError) -> None:
    """Map the per-org case-insensitive name collision
    (`uq_companies_org_name`) to a 409; re-raise anything else."""
    if "uq_companies_org_name" in str(exc.orig):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A company with this name already exists in this workspace.",
        ) from exc
    raise exc


class CompanyRollup(BaseModel):
    """What the Account detail page renders: the company plus the
    contacts (customers + leads) and deals that hang off it."""

    company: CompanyOut
    customers: list[CustomerOut]
    leads: list[LeadOut]
    deals: list[DealOut]


async def _get_company_or_404(
    db: AsyncSession, company_id: uuid.UUID, org_id: uuid.UUID
) -> Company:
    result = await db.execute(
        select(Company).where(Company.id == company_id, Company.organization_id == org_id)
    )
    company = result.scalar_one_or_none()
    if not company or company.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.get("", response_model=CursorPage[CompanyOut])
async def list_companies(
    q: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, description="opaque keyset cursor"),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> CursorPage:
    stmt = select(Company).where(Company.organization_id == org_id)
    if q:
        stmt = stmt.where(Company.name.ilike(f"%{q}%"))
    return await paginate(db, stmt, Company, limit=limit, cursor=cursor)


@router.post("", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
async def create_company(
    payload: CompanyCreate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Company:
    data = payload.model_dump()
    data["owner_id"] = data.get("owner_id") or user.id
    data["custom_fields"] = await validate_custom_fields(
        db, org_id, "company", data.get("custom_fields"), partial=False
    )
    company = Company(**data, organization_id=org_id)
    db.add(company)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        _raise_for_duplicate_name(exc)
    await record_audit(
        db,
        actor=user,
        action="company.create",
        entity_type="company",
        entity_id=company.id,
        organization_id=org_id,
    )
    await record_activity(
        db,
        entity_type=ENTITY_COMPANY,
        entity_id=company.id,
        activity_type=ActivityType.created,
        organization_id=org_id,
        actor=user,
    )
    await db.commit()
    await db.refresh(company)
    return company


@router.get("/{company_id}", response_model=CompanyOut)
async def get_company(
    company_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Company:
    return await _get_company_or_404(db, company_id, org_id)


@router.get("/{company_id}/rollup", response_model=CompanyRollup)
async def get_company_rollup(
    company_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> CompanyRollup:
    company = await _get_company_or_404(db, company_id, org_id)
    customers = (
        (
            await db.execute(
                select(Customer)
                .where(Customer.organization_id == org_id, Customer.company_id == company_id)
                .order_by(Customer.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    leads = (
        (
            await db.execute(
                select(Lead)
                .where(Lead.organization_id == org_id, Lead.company_id == company_id)
                .order_by(Lead.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    deals = (
        (
            await db.execute(
                select(Deal)
                .where(Deal.organization_id == org_id, Deal.company_id == company_id)
                .order_by(Deal.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return CompanyRollup(
        company=CompanyOut.model_validate(company),
        customers=[CustomerOut.model_validate(c) for c in customers],
        leads=[LeadOut.model_validate(lead) for lead in leads],
        deals=[DealOut.model_validate(d) for d in deals],
    )


@router.patch("/{company_id}", response_model=CompanyOut)
async def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> Company:
    company = await _get_company_or_404(db, company_id, org_id)
    ensure_can_mutate(user, company.owner_id)
    check_if_match(
        entity="company",
        entity_id=company.id,
        current_version=company.version,
        if_match=if_match,
    )
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("organization_id", None)
    if "custom_fields" in changes:
        changes["custom_fields"] = await validate_custom_fields(
            db,
            org_id,
            "company",
            changes["custom_fields"],
            existing=company.custom_fields,
            partial=True,
        )
    for field, value in changes.items():
        setattr(company, field, value)
    company.version = company.version + 1
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        _raise_for_duplicate_name(exc)
    await record_audit(
        db,
        actor=user,
        action="company.update",
        entity_type="company",
        entity_id=company.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await record_activity(
        db,
        entity_type=ENTITY_COMPANY,
        entity_id=company.id,
        activity_type=ActivityType.updated,
        organization_id=org_id,
        actor=user,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    await db.refresh(company)
    return company


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    company = await _get_company_or_404(db, company_id, org_id)
    ensure_can_mutate(user, company.owner_id)
    company.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="company.soft_delete",
        entity_type="company",
        entity_id=company.id,
        organization_id=org_id,
    )
    await db.commit()

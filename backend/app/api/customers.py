import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.database import get_db
from app.deps import ensure_can_mutate, get_current_org_id, get_current_user
from app.models import Customer, User
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, CursorPage, paginate
from app.schemas import CustomerCreate, CustomerOut, CustomerUpdate
from app.services.ai_assistant import summarize_customer

router = APIRouter(prefix="/api/customers", tags=["customers"])


# Tenant-scoped via `get_current_org_id` — see leads.py docstring for the
# enforcement model. `organization_id` is set server-side on create and
# stripped on update; cross-org reads return 404, not 403.


async def _get_customer_or_404(
    db: AsyncSession, customer_id: uuid.UUID, org_id: uuid.UUID
) -> Customer:
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.organization_id == org_id)
    )
    customer = result.scalar_one_or_none()
    if not customer or customer.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.get("", response_model=CursorPage[CustomerOut])
async def list_customers(
    q: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, description="opaque keyset cursor"),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> CursorPage:
    stmt = select(Customer).where(Customer.organization_id == org_id)
    if q:
        # FTS via the stored search_vector column + GIN index
        # (migration 062fbc7b628d). Same pattern as leads — see
        # the comment there.
        stmt = stmt.where(
            sa.text("search_vector @@ websearch_to_tsquery('simple', :q)").bindparams(q=q)
        )
    return await paginate(db, stmt, Customer, limit=limit, cursor=cursor)


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    data = payload.model_dump()
    data["owner_id"] = data.get("owner_id") or user.id
    customer = Customer(**data, organization_id=org_id)
    db.add(customer)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="customer.create",
        entity_type="customer",
        entity_id=customer.id,
        organization_id=org_id,
    )
    await db.commit()
    await db.refresh(customer)
    return customer


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    return await _get_customer_or_404(db, customer_id, org_id)


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    customer = await _get_customer_or_404(db, customer_id, org_id)
    ensure_can_mutate(user, customer.owner_id)
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("organization_id", None)
    for field, value in changes.items():
        setattr(customer, field, value)
    await record_audit(
        db,
        actor=user,
        action="customer.update",
        entity_type="customer",
        entity_id=customer.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    await db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    customer = await _get_customer_or_404(db, customer_id, org_id)
    ensure_can_mutate(user, customer.owner_id)
    customer.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="customer.soft_delete",
        entity_type="customer",
        entity_id=customer.id,
        organization_id=org_id,
    )
    await db.commit()


@router.post("/{customer_id}/summarize", response_model=CustomerOut)
async def summarize(
    customer_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    customer = await _get_customer_or_404(db, customer_id, org_id)
    ensure_can_mutate(user, customer.owner_id)
    summary = await summarize_customer(customer)
    customer.ai_summary = summary
    customer.ai_summary_updated_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="customer.summarize",
        entity_type="customer",
        entity_id=customer.id,
        organization_id=org_id,
    )
    await db.commit()
    await db.refresh(customer)
    return customer

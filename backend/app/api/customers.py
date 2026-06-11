import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.activities import ENTITY_CUSTOMER, ActivityType, record_activity
from app.api._concurrency import check_if_match
from app.api._errors import raise_for_duplicate_email
from app.api.dashboard import invalidate_dashboard_cache
from app.audit import record_audit
from app.custom_fields import validate_custom_fields
from app.database import get_db
from app.deps import ensure_can_mutate, get_current_org_id, get_current_user
from app.events import EventType, record_event
from app.metrics import SEARCH_TRGM_FALLBACK
from app.models import Customer, Deal, DealStage, Task, TaskStatus, User
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
        # (migration 062fbc7b628d). Falls back to trigram similarity
        # when FTS returns no hits (handles typos).
        fts_filter = sa.text("search_vector @@ websearch_to_tsquery('simple', :q)").bindparams(q=q)
        has_fts = (
            await db.execute(
                select(sa.literal(1))
                .where(Customer.organization_id == org_id, fts_filter)
                .limit(1)
            )
        ).first() is not None
        if has_fts:
            stmt = stmt.where(fts_filter)
        else:
            SEARCH_TRGM_FALLBACK.labels(entity_type="customer").inc()
            stmt = stmt.where(
                sa.or_(
                    sa.func.similarity(Customer.first_name, q) > 0.3,
                    sa.func.similarity(Customer.last_name, q) > 0.3,
                    sa.func.similarity(Customer.email, q) > 0.3,
                    sa.func.similarity(Customer.company, q) > 0.3,
                )
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
    data["custom_fields"] = await validate_custom_fields(
        db, org_id, "customer", data.get("custom_fields"), partial=False
    )
    customer = Customer(**data, organization_id=org_id)
    db.add(customer)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise_for_duplicate_email(exc, "customer")
    await record_audit(
        db,
        actor=user,
        action="customer.create",
        entity_type="customer",
        entity_id=customer.id,
        organization_id=org_id,
    )
    await record_activity(
        db,
        entity_type=ENTITY_CUSTOMER,
        entity_id=customer.id,
        activity_type=ActivityType.created,
        organization_id=org_id,
        actor=user,
    )
    await record_event(
        db,
        event_type=EventType.customer_created,
        organization_id=org_id,
        payload={
            "customer_id": customer.id,
            "owner_id": customer.owner_id,
            "company_id": customer.company_id,
            "actor_user_id": user.id,
        },
    )
    await db.commit()
    await invalidate_dashboard_cache(org_id)
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
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> Customer:
    customer = await _get_customer_or_404(db, customer_id, org_id)
    ensure_can_mutate(user, customer.owner_id)
    check_if_match(
        entity="customer",
        entity_id=customer.id,
        current_version=customer.version,
        if_match=if_match,
    )
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("organization_id", None)
    if "custom_fields" in changes:
        changes["custom_fields"] = await validate_custom_fields(
            db,
            org_id,
            "customer",
            changes["custom_fields"],
            existing=customer.custom_fields,
            partial=True,
        )
    for field, value in changes.items():
        setattr(customer, field, value)
    customer.version = customer.version + 1
    # Flush the entity change HERE so a per-org email collision surfaces as
    # a 409 now. record_activity/record_audit below issue their own flush,
    # which would otherwise raise the IntegrityError outside any handler
    # (escaping as a 500) before we reach the commit.
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise_for_duplicate_email(exc, "customer")
    await record_audit(
        db,
        actor=user,
        action="customer.update",
        entity_type="customer",
        entity_id=customer.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await record_activity(
        db,
        entity_type=ENTITY_CUSTOMER,
        entity_id=customer.id,
        activity_type=ActivityType.updated,
        organization_id=org_id,
        actor=user,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    await invalidate_dashboard_cache(org_id)
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
    await invalidate_dashboard_cache(org_id)


@router.post("/{customer_id}/summarize", response_model=CustomerOut)
async def summarize(
    customer_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Customer:
    customer = await _get_customer_or_404(db, customer_id, org_id)
    ensure_can_mutate(user, customer.owner_id)

    # Enrich the LLM prompt with open deals + pending tasks so the
    # summary reflects actual pipeline state, not just profile fields.
    open_deals = (
        await db.execute(
            select(Deal.title, Deal.value, Deal.currency, Deal.stage).where(
                Deal.customer_id == customer.id,
                Deal.organization_id == org_id,
                Deal.stage.notin_([DealStage.won, DealStage.lost]),
                Deal.deleted_at.is_(None),
            )
        )
    ).all()
    open_tasks = (
        await db.execute(
            select(Task.title, Task.due_date, Task.priority).where(
                Task.customer_id == customer.id,
                Task.organization_id == org_id,
                Task.status != TaskStatus.done,
                Task.deleted_at.is_(None),
            ).order_by(Task.due_date.asc().nullslast()).limit(5)
        )
    ).all()

    summary = await summarize_customer(customer, open_deals=open_deals, open_tasks=open_tasks)
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

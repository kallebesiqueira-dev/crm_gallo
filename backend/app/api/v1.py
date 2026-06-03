"""Public API v1 — the bearer-authenticated, versioned external surface.

This router does NOT re-implement business logic. It is a thin adapter:
authenticate with an API key (`require_api_key`), then delegate to the
SAME handler functions the cookie-authed `/api/leads` and `/api/customers`
routes use — so audit, activity, outbox events, ownership defaults and
org-scoping all behave identically whether a request arrives from the
browser or from an integrator's bearer key. The only differences are the
credential (key vs cookie) and the path version (`/api/v1`).

Scope enforcement (read for GET, write for POST) and the per-key rate
limit are handled inside `require_api_key`; by the time a handler runs,
the principal is authorised for the verb.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import customers as customers_api
from app.api import leads as leads_api
from app.api.versioning import stamp_version
from app.api_auth import ApiPrincipal, require_api_key
from app.database import get_db
from app.models import LeadStage
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, CursorPage
from app.schemas import CustomerCreate, CustomerOut, LeadCreate, LeadOut

router = APIRouter(prefix="/api/v1", tags=["public-api-v1"], dependencies=[Depends(stamp_version)])


# ---------- Leads ----------


@router.get("/leads", response_model=CursorPage[LeadOut])
async def v1_list_leads(
    stage: LeadStage | None = None,
    q: str | None = Query(default=None, description="search by name/email/company"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, description="opaque keyset cursor"),
    principal: ApiPrincipal = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> CursorPage:
    return await leads_api.list_leads(
        stage=stage,
        team_id=None,
        q=q,
        limit=limit,
        cursor=cursor,
        _=principal.user,
        org_id=principal.org_id,
        db=db,
    )


@router.post("/leads", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def v1_create_lead(
    payload: LeadCreate,
    principal: ApiPrincipal = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await leads_api.create_lead(
        payload=payload, user=principal.user, org_id=principal.org_id, db=db
    )


@router.get("/leads/{lead_id}", response_model=LeadOut)
async def v1_get_lead(
    lead_id: uuid.UUID,
    principal: ApiPrincipal = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await leads_api._get_lead_or_404(db, lead_id, principal.org_id)


# ---------- Customers ----------


@router.get("/customers", response_model=CursorPage[CustomerOut])
async def v1_list_customers(
    q: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, description="opaque keyset cursor"),
    principal: ApiPrincipal = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> CursorPage:
    return await customers_api.list_customers(
        q=q, limit=limit, cursor=cursor, _=principal.user, org_id=principal.org_id, db=db
    )


@router.post("/customers", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def v1_create_customer(
    payload: CustomerCreate,
    principal: ApiPrincipal = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await customers_api.create_customer(
        payload=payload, user=principal.user, org_id=principal.org_id, db=db
    )


@router.get("/customers/{customer_id}", response_model=CustomerOut)
async def v1_get_customer(
    customer_id: uuid.UUID,
    principal: ApiPrincipal = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
):
    return await customers_api._get_customer_or_404(db, customer_id, principal.org_id)

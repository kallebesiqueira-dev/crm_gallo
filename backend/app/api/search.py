"""Unified global search (/api/search) — powers the ⌘K command palette.

One round-trip across the user-searchable entities (leads, customers,
companies) instead of the SPA fanning out to three list endpoints. It does
NOT re-implement search: it delegates to the very same list handlers (with
their FTS + pg_trgm typo fallback and RLS scoping), so ranking and tenant
isolation stay identical to the per-entity lists.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import companies as companies_api
from app.api import customers as customers_api
from app.api import leads as leads_api
from app.database import get_db
from app.deps import get_current_org_id, get_current_user
from app.models import User
from app.schemas import SearchResults

router = APIRouter(prefix="/api/search", tags=["search"])

# Below this the palette shows commands/navigation only — too short to be a
# meaningful entity query (and keeps trigram scans off single keystrokes).
_MIN_QUERY_LEN = 2


@router.get("", response_model=SearchResults)
async def global_search(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> SearchResults:
    if len(q.strip()) < _MIN_QUERY_LEN:
        return SearchResults()

    leads = await leads_api.list_leads(
        stage=None, team_id=None, q=q, limit=limit, cursor=None, _=user, org_id=org_id, db=db
    )
    customers = await customers_api.list_customers(
        q=q, limit=limit, cursor=None, _=user, org_id=org_id, db=db
    )
    companies = await companies_api.list_companies(
        q=q, limit=limit, cursor=None, _=user, org_id=org_id, db=db
    )
    return SearchResults(leads=leads.items, customers=customers.items, companies=companies.items)

"""FX rates — current EUR-based exchange rates for the display layer.

Read-only and tenant-agnostic (rates are global reference data). Any
authenticated user can read them so the frontend can offer a display-
currency selector (EUR/CHF/USD/GBP/…) and convert the dashboard's EUR
headlines client-side. The numbers are refreshed by the worker's
`refresh_fx_rates` cron from the ECB feed; see `app.services.fx`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import FxRatesOut
from app.services import fx

router = APIRouter(prefix="/api/fx", tags=["fx"])


@router.get("/rates", response_model=FxRatesOut)
async def get_rates(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FxRatesOut:
    snap = await fx.get_snapshot(db)
    return FxRatesOut(
        base=fx.BASE,
        rates={k: float(v) for k, v in snap.rates.items()},
        as_of=snap.as_of,
        source=snap.source,
    )

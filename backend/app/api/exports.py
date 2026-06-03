"""Streaming CSV export of leads / customers (ADR-016 exports slice).

`GET /api/exports/{entity_type}?format=csv` streams the org's rows as a
CSV download. The body is produced by `app.exports.stream_csv`, a keyset-
paged async generator, so a large export flows at constant memory instead
of materialising every row first.

Formula-injection safety (TD-22) is handled inside `stream_csv` /
`csv_safe` — every exported cell that would be read as a spreadsheet
formula is neutralised. See `app/exports.py` for the rationale.

Streaming + the request-scoped DB session: FastAPI runs a `yield`
dependency's teardown AFTER the response body is fully sent, so the
`get_db` session (and its transaction-scoped RLS GUC) stays valid for
the whole stream — the generator's paged SELECTs all run under the
current org's GUC.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_org_id, get_current_user
from app.exports import EXPORT_ENTITY_TYPES, stream_csv
from app.models import User

router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.get("/{entity_type}")
async def export_entity(
    entity_type: str,
    format: Annotated[str, Query(pattern="^csv$")] = "csv",
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream `entity_type` rows for the current org as a CSV attachment.

    Only `csv` is offered today (the `format` query param is validated to
    it); an XLSX export would mean buffering the whole sheet, which defeats
    the streaming goal — deferred until there's demand.
    """
    if entity_type not in EXPORT_ENTITY_TYPES:
        # Mirror the cross-org 404 convention: an unknown export target is
        # "not found", not a 422 leaking the valid set.
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Unknown export entity")

    stamp = datetime.now(UTC).strftime("%Y%m%d")
    filename = f"{entity_type}s-{stamp}.csv"
    return StreamingResponse(
        stream_csv(db, entity_type, org_id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

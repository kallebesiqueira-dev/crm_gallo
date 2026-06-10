"""Dead-letter queue inspection — admin-only.

GET  /api/admin/dlq          list failed jobs (newest first)
GET  /api/admin/dlq/count    total entry count
DELETE /api/admin/dlq        purge all entries
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from app.deps import require_roles
from app.models import User, UserRole
from app.redis_client import get_redis
from app.worker.dlq import DLQ_KEY

router = APIRouter(prefix="/api/admin/dlq", tags=["admin"])


class DLQEntry(BaseModel):
    job_id: str
    function: str
    job_try: int
    failed_at: str
    exception_type: str
    exception_msg: str
    traceback: str = ""


@router.get("", response_model=list[DLQEntry])
async def list_dlq(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    _: User = Depends(require_roles(UserRole.admin)),
) -> list[DLQEntry]:
    """Return dead jobs, most recent first."""
    r = get_redis()
    raw = await r.lrange(DLQ_KEY, offset, offset + limit - 1)
    return [DLQEntry(**json.loads(item)) for item in raw]


@router.get("/count")
async def dlq_count(
    _: User = Depends(require_roles(UserRole.admin)),
) -> dict[str, int]:
    r = get_redis()
    return {"count": await r.llen(DLQ_KEY)}


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def purge_dlq(
    _: User = Depends(require_roles(UserRole.admin)),
) -> None:
    """Remove all dead-letter entries."""
    r = get_redis()
    await r.delete(DLQ_KEY)

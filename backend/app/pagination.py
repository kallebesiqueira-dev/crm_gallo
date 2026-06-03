"""Keyset (cursor) pagination — TD-11.

Limit/offset diverges under concurrent writes (a row inserted on page 1
shifts everything, so page 2 repeats or skips rows) and Postgres still
scans+discards `offset` rows, so it degrades past ~10k. Keyset paging
seeks straight to the cursor on the `(created_at, id)` index, so cost is
flat regardless of depth and the result set is stable under inserts.

Sort key is `(created_at DESC, id DESC)` — `created_at` is the visible
order, `id` is the tiebreaker that makes the key unique (two rows with
the same timestamp must still have a total order or the cursor could
straddle them). The cursor is an opaque base64 blob so clients never
build or reason about it; only this module encodes/decodes it.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import datetime
from typing import Generic, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import Select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")

# Hard ceiling so a client can't ask for an unbounded page.
MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50


class CursorPage(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "id": str(row_id)})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(raw)
        return datetime.fromisoformat(data["c"]), uuid.UUID(str(data["id"]))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cursor"
        ) from exc


async def paginate(
    db: AsyncSession,
    stmt: Select,
    model: type,
    *,
    limit: int,
    cursor: str | None,
) -> CursorPage:
    """Apply keyset paging to `stmt` and run it.

    `stmt` must already carry every filter (org scope, search, etc.) but
    NOT order_by/limit/offset — those belong to the sort key and are
    applied here. `model` supplies the `created_at`/`id` columns.
    """
    if cursor:
        c_created, c_id = decode_cursor(cursor)
        # Row-value comparison: rows strictly "after" the cursor in
        # (created_at DESC, id DESC) order. Postgres evaluates the tuple
        # lexicographically and the planner can drive it off the index.
        stmt = stmt.where(tuple_(model.created_at, model.id) < (c_created, c_id))

    # Fetch one extra to learn whether a further page exists without a
    # second COUNT query.
    stmt = stmt.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
    rows = list((await db.execute(stmt)).scalars().all())

    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
    # model_construct: skip re-validation here; FastAPI's response_model
    # coerces each ORM row to its Out schema on the way out.
    return CursorPage.model_construct(items=rows, next_cursor=next_cursor, has_more=has_more)

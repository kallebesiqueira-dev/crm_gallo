"""Contract number generation (ADR-016).

Mirrors `app/services/quotes.next_quote_number` — a per-org, zero-padded
human-facing identifier (`C-000007`). Kept out of the route so the
worker and tests can call the same logic.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contract


async def next_contract_number(db: AsyncSession, organization_id: uuid.UUID) -> str:
    """Next human-facing contract number for the org, e.g. `C-000007`.

    Zero-padded so lexicographic max == numeric max. Includes
    soft-deleted rows (`include_deleted=True`) so a deleted contract's
    number is never silently reused while another revision of it may
    still reference the sequence. Callers must hold a per-org advisory
    lock (see `create_contract`) to make the read-then-insert race-safe;
    the `(organization_id, number, version)` unique index is the backstop
    if two creates still collide.
    """
    result = await db.execute(
        select(func.max(Contract.number))
        .where(Contract.organization_id == organization_id)
        .execution_options(include_deleted=True)
    )
    current = result.scalar_one_or_none()
    if current is None:
        return "C-000001"
    try:
        n = int(current.rsplit("-", 1)[1]) + 1
    except (IndexError, ValueError):
        # Defensive: a manually-inserted non-conforming number. Fall
        # back to 1; the unique index still guards against a collision.
        n = 1
    return f"C-{n:06d}"

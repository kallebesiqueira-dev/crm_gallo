"""Streaming CSV export of leads / customers (ADR-016 exports slice, TD-22).

Two things matter here:

  * **Formula-injection safety (TD-22).** A cell whose value starts with
    `= + - @`, a tab or a CR is a spreadsheet-formula vector: open the
    exported CSV in Excel/Sheets and `=cmd|'/c calc'!A1` (or a data-
    exfiltration `=IMPORTXML(...)`) executes. We neutralise every such
    cell by prefixing a single quote, per the OWASP CSV-injection
    guidance. This runs on EVERY exported value, not just user-notes.

  * **Streaming (don't materialise all rows).** The export is an async
    generator that pages the table with a keyset cursor and yields CSV
    text per batch, so a 100k-row export streams at constant memory
    instead of building one giant string.

Org scope + soft-delete exclusion come for free: the queries filter on
`organization_id` and the global `SoftDeleteMixin` loader criterion
already drops deleted rows from every SELECT.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer, Lead

# A leading char in this set turns a CSV cell into a live formula in
# Excel / LibreOffice / Google Sheets. Tab and CR are included because
# they can smuggle a formula past a naive "first char" check in some
# spreadsheet importers.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Rows fetched per keyset page. Big enough to amortise round-trips,
# small enough that one page's objects stay cheap in memory.
_EXPORT_PAGE_SIZE = 1000


def csv_safe(value: Any) -> str:
    """Render `value` as a spreadsheet-injection-safe string.

    Enums → `.value`, Decimal/UUID/datetime → their canonical string,
    None → "". Any result that begins with a formula trigger is prefixed
    with `'` so the spreadsheet treats it as literal text.
    """
    if value is None:
        return ""
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, datetime):
        text = value.isoformat()
    elif isinstance(value, Decimal | uuid.UUID):
        text = str(value)
    else:
        text = str(value)
    if text and text[0] in _FORMULA_PREFIXES:
        text = "'" + text
    return text


@dataclass(frozen=True)
class ExportColumn:
    header: str
    attr: str


_LEAD_EXPORT_COLUMNS = [
    ExportColumn("id", "id"),
    ExportColumn("first_name", "first_name"),
    ExportColumn("last_name", "last_name"),
    ExportColumn("email", "email"),
    ExportColumn("phone", "phone"),
    ExportColumn("company", "company"),
    ExportColumn("industry", "industry"),
    ExportColumn("country", "country"),
    ExportColumn("company_size", "company_size"),
    ExportColumn("budget", "budget"),
    ExportColumn("source", "source"),
    ExportColumn("stage", "stage"),
    ExportColumn("ai_score", "ai_score"),
    ExportColumn("ai_priority", "ai_priority"),
    ExportColumn("notes", "notes"),
    ExportColumn("created_at", "created_at"),
]

_CUSTOMER_EXPORT_COLUMNS = [
    ExportColumn("id", "id"),
    ExportColumn("first_name", "first_name"),
    ExportColumn("last_name", "last_name"),
    ExportColumn("email", "email"),
    ExportColumn("phone", "phone"),
    ExportColumn("company", "company"),
    ExportColumn("industry", "industry"),
    ExportColumn("country", "country"),
    ExportColumn("address", "address"),
    ExportColumn("website", "website"),
    ExportColumn("notes", "notes"),
    ExportColumn("created_at", "created_at"),
]

_EXPORT_CONFIG = {
    "lead": (Lead, _LEAD_EXPORT_COLUMNS),
    "customer": (Customer, _CUSTOMER_EXPORT_COLUMNS),
}

EXPORT_ENTITY_TYPES = tuple(_EXPORT_CONFIG.keys())


def _encode_row(values: list[str]) -> str:
    """One CSV record as text. csv.writer handles comma/quote/newline
    escaping; we pass already-injection-safe cell strings in."""
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\r\n").writerow(values)
    return buf.getvalue()


async def stream_csv(db: AsyncSession, entity_type: str, org_id: uuid.UUID) -> AsyncIterator[str]:
    """Yield the export as CSV text, header first, then keyset-paged rows.

    Keyset on `(created_at, id)` so paging is stable and index-friendly
    (mirrors the cursor-pagination ADR) rather than OFFSET, which would
    re-scan on every page.
    """
    model, columns = _EXPORT_CONFIG[entity_type]

    yield _encode_row([c.header for c in columns])

    last_created: datetime | None = None
    last_id: uuid.UUID | None = None
    while True:
        stmt = (
            select(model)
            .where(model.organization_id == org_id)
            .order_by(model.created_at.asc(), model.id.asc())
            .limit(_EXPORT_PAGE_SIZE)
        )
        if last_created is not None:
            # Strict keyset: rows after the last (created_at, id) seen.
            stmt = stmt.where(
                (model.created_at > last_created)
                | ((model.created_at == last_created) & (model.id > last_id))
            )
        rows = (await db.execute(stmt)).scalars().all()
        if not rows:
            break
        for row in rows:
            yield _encode_row([csv_safe(getattr(row, c.attr)) for c in columns])
        last_created = rows[-1].created_at
        last_id = rows[-1].id
        if len(rows) < _EXPORT_PAGE_SIZE:
            break

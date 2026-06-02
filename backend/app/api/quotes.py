"""Versioned quotes / proposals — CRUD + status state machine (ADR-016).

State machine (the ONLY legal transitions; anything else → 409):

    draft  ──send──▶  sent  ──accept──▶  accepted   (terminal)
                       │
                       └────decline──▶   declined    (terminal)

`draft` is the only mutable status — editing a sent/accepted/declined
quote is rejected. Re-issuing instead clones the quote into a fresh
`draft` at `version + 1` (POST /{id}/resend); the prior row keeps its
terminal status and points forward via `superseded_by`. Totals are
always recomputed server-side from the line items (never trusted from
the client).
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import record_audit
from app.database import get_db
from app.deps import ensure_can_mutate, get_current_org_id, get_current_user
from app.events import EventType, record_event
from app.logging_setup import get_logger
from app.models import Quote, QuoteLineItem, QuoteStatus, User
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, CursorPage, paginate
from app.schemas import QuoteCreate, QuoteOut, QuoteUpdate
from app.services.quotes import next_quote_number, recompute_totals

router = APIRouter(prefix="/api/quotes", tags=["quotes"])
log = get_logger(__name__)


async def _get_quote_or_404(db: AsyncSession, quote_id: uuid.UUID, org_id: uuid.UUID) -> Quote:
    result = await db.execute(
        select(Quote)
        .where(Quote.id == quote_id, Quote.organization_id == org_id)
        .options(selectinload(Quote.line_items))
    )
    quote = result.scalar_one_or_none()
    if not quote or quote.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote


def _require_draft(quote: Quote) -> None:
    if quote.status != QuoteStatus.draft:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Quote is {quote.status.value}; only draft quotes are editable. "
                "Use POST /{id}/resend to issue a new version."
            ),
        )


@router.get("", response_model=CursorPage[QuoteOut])
async def list_quotes(
    status_filter: QuoteStatus | None = Query(default=None, alias="status"),
    deal_id: uuid.UUID | None = Query(default=None),
    customer_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, description="opaque keyset cursor"),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> CursorPage:
    stmt = (
        select(Quote)
        .where(Quote.organization_id == org_id)
        .options(selectinload(Quote.line_items))
    )
    if status_filter is not None:
        stmt = stmt.where(Quote.status == status_filter)
    if deal_id is not None:
        stmt = stmt.where(Quote.deal_id == deal_id)
    if customer_id is not None:
        stmt = stmt.where(Quote.customer_id == customer_id)
    return await paginate(db, stmt, Quote, limit=limit, cursor=cursor)


@router.post("", response_model=QuoteOut, status_code=status.HTTP_201_CREATED)
async def create_quote(
    payload: QuoteCreate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Quote:
    # Per-org advisory lock makes the read-then-insert of the quote
    # number race-safe (two concurrent creates can't grab the same
    # number). hashtext → int4, fits the bigint lock-key param; the
    # lock auto-releases at transaction end. The partial unique index
    # (organization_id, number, version) is the backstop.
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"quote_number:{org_id}"))))
    number = await next_quote_number(db, org_id)

    data = payload.model_dump(exclude={"line_items"})
    data["owner_id"] = data.get("owner_id") or user.id
    quote = Quote(
        **data,
        organization_id=org_id,
        number=number,
        version=1,
        status=QuoteStatus.draft,
    )
    for item in payload.line_items:
        quote.line_items.append(QuoteLineItem(organization_id=org_id, **item.model_dump()))
    recompute_totals(quote)
    db.add(quote)
    await db.flush()

    await record_audit(
        db,
        actor=user,
        action="quote.create",
        entity_type="quote",
        entity_id=quote.id,
        organization_id=org_id,
        metadata={"number": quote.number, "version": quote.version, "total": quote.total},
    )
    await record_event(
        db,
        event_type=EventType.quote_created,
        organization_id=org_id,
        payload={
            "quote_id": quote.id,
            "number": quote.number,
            "version": quote.version,
            "total": quote.total,
            "owner_id": quote.owner_id,
            "actor_user_id": user.id,
        },
    )
    await db.commit()
    return await _get_quote_or_404(db, quote.id, org_id)


@router.get("/{quote_id}", response_model=QuoteOut)
async def get_quote(
    quote_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Quote:
    return await _get_quote_or_404(db, quote_id, org_id)


@router.patch("/{quote_id}", response_model=QuoteOut)
async def update_quote(
    quote_id: uuid.UUID,
    payload: QuoteUpdate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Quote:
    quote = await _get_quote_or_404(db, quote_id, org_id)
    ensure_can_mutate(user, quote.owner_id)
    _require_draft(quote)

    changes = payload.model_dump(exclude_unset=True)
    new_items = changes.pop("line_items", None)
    for field, value in changes.items():
        setattr(quote, field, value)
    if new_items is not None:
        # Full replace — orphaned rows are deleted via cascade.
        quote.line_items.clear()
        for item in new_items:
            quote.line_items.append(QuoteLineItem(organization_id=org_id, **item))
    recompute_totals(quote)

    await record_audit(
        db,
        actor=user,
        action="quote.update",
        entity_type="quote",
        entity_id=quote.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys()), "line_items_replaced": new_items is not None},
    )
    await db.commit()
    return await _get_quote_or_404(db, quote.id, org_id)


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quote(
    quote_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    quote = await _get_quote_or_404(db, quote_id, org_id)
    ensure_can_mutate(user, quote.owner_id)
    quote.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="quote.soft_delete",
        entity_type="quote",
        entity_id=quote.id,
        organization_id=org_id,
    )
    await db.commit()


@router.post("/{quote_id}/pdf", status_code=status.HTTP_202_ACCEPTED)
async def generate_quote_pdf_endpoint(
    quote_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Enqueue a quote PDF (ADR-016) and return 202.

    The worker renders the document and attaches it to the quote, so it
    surfaces in `GET /api/attachments?entity_type=quote&...` and downloads
    via the existing presigned-URL endpoint. Idempotent within a 5-minute
    window — a double-click returns `{queued: false}`.
    """
    quote = await _get_quote_or_404(db, quote_id, org_id)
    ensure_can_mutate(user, quote.owner_id)

    from app.worker.queue import enqueue

    job = await enqueue(
        "generate_quote_pdf",
        str(quote.id),
        str(org_id),
        dedupe_key=f"quote_pdf:{quote.id}",
        dedupe_ttl_seconds=300,
    )
    if job is None:
        return {"queued": False, "dedupe": True}
    return {"queued": True, "job_id": job.job_id}


# ---------- State machine transitions ----------
@router.post("/{quote_id}/send", response_model=QuoteOut)
async def send_quote(
    quote_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Quote:
    quote = await _get_quote_or_404(db, quote_id, org_id)
    ensure_can_mutate(user, quote.owner_id)
    if quote.status != QuoteStatus.draft:
        raise HTTPException(
            status_code=409,
            detail=f"Only a draft quote can be sent (current: {quote.status.value}).",
        )
    if not quote.line_items:
        raise HTTPException(status_code=422, detail="Cannot send a quote with no line items.")
    quote.status = QuoteStatus.sent
    quote.sent_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="quote.send",
        entity_type="quote",
        entity_id=quote.id,
        organization_id=org_id,
        metadata={"number": quote.number, "version": quote.version},
    )
    await record_event(
        db,
        event_type=EventType.quote_sent,
        organization_id=org_id,
        payload={
            "quote_id": quote.id,
            "number": quote.number,
            "version": quote.version,
            "total": quote.total,
            "owner_id": quote.owner_id,
            "actor_user_id": user.id,
        },
    )
    await db.commit()
    return await _get_quote_or_404(db, quote.id, org_id)


@router.post("/{quote_id}/accept", response_model=QuoteOut)
async def accept_quote(
    quote_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Quote:
    return await _terminate(
        db,
        quote_id,
        org_id,
        user,
        from_status=QuoteStatus.sent,
        to_status=QuoteStatus.accepted,
        ts_field="accepted_at",
        action="quote.accept",
        event_type=EventType.quote_accepted,
    )


@router.post("/{quote_id}/decline", response_model=QuoteOut)
async def decline_quote(
    quote_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Quote:
    return await _terminate(
        db,
        quote_id,
        org_id,
        user,
        from_status=QuoteStatus.sent,
        to_status=QuoteStatus.declined,
        ts_field="declined_at",
        action="quote.decline",
        event_type=EventType.quote_declined,
    )


async def _terminate(
    db: AsyncSession,
    quote_id: uuid.UUID,
    org_id: uuid.UUID,
    user: User,
    *,
    from_status: QuoteStatus,
    to_status: QuoteStatus,
    ts_field: str,
    action: str,
    event_type: EventType,
) -> Quote:
    quote = await _get_quote_or_404(db, quote_id, org_id)
    ensure_can_mutate(user, quote.owner_id)
    if quote.status != from_status:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Quote must be {from_status.value} to become {to_status.value}; "
                f"current: {quote.status.value}."
            ),
        )
    quote.status = to_status
    setattr(quote, ts_field, datetime.now(UTC))
    await record_audit(
        db,
        actor=user,
        action=action,
        entity_type="quote",
        entity_id=quote.id,
        organization_id=org_id,
        metadata={"number": quote.number, "version": quote.version},
    )
    await record_event(
        db,
        event_type=event_type,
        organization_id=org_id,
        payload={
            "quote_id": quote.id,
            "number": quote.number,
            "version": quote.version,
            "total": quote.total,
            "owner_id": quote.owner_id,
            "actor_user_id": user.id,
        },
    )
    await db.commit()
    return await _get_quote_or_404(db, quote.id, org_id)


@router.post("/{quote_id}/resend", response_model=QuoteOut, status_code=status.HTTP_201_CREATED)
async def resend_quote(
    quote_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Quote:
    """Re-issue a quote as a fresh draft at version + 1.

    Allowed once a quote has left draft (sent / accepted / declined /
    expired) — you don't re-issue something still being drafted; just
    edit it. The new revision deep-copies the line items, keeps the same
    `number`, and starts as `draft`; the prior row points forward via
    `superseded_by`.
    """
    old = await _get_quote_or_404(db, quote_id, org_id)
    ensure_can_mutate(user, old.owner_id)
    if old.status == QuoteStatus.draft:
        raise HTTPException(
            status_code=409,
            detail="Quote is still a draft — edit it directly instead of re-issuing.",
        )

    # Highest existing version for this number, across soft-deleted rows
    # too, so a re-issue never reuses a version another revision held.
    max_version = (
        await db.execute(
            select(func.max(Quote.version))
            .where(Quote.organization_id == org_id, Quote.number == old.number)
            .execution_options(include_deleted=True)
        )
    ).scalar_one()

    new = Quote(
        organization_id=org_id,
        deal_id=old.deal_id,
        customer_id=old.customer_id,
        number=old.number,
        version=(max_version or old.version) + 1,
        status=QuoteStatus.draft,
        title=old.title,
        currency=old.currency,
        tax_rate=old.tax_rate,
        valid_until=old.valid_until,
        notes=old.notes,
        owner_id=old.owner_id,
    )
    for item in old.line_items:
        new.line_items.append(
            QuoteLineItem(
                organization_id=org_id,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                sort_index=item.sort_index,
            )
        )
    recompute_totals(new)
    db.add(new)
    await db.flush()
    old.superseded_by = new.id

    await record_audit(
        db,
        actor=user,
        action="quote.resend",
        entity_type="quote",
        entity_id=new.id,
        organization_id=org_id,
        metadata={"number": new.number, "from_version": old.version, "to_version": new.version},
    )
    await db.commit()
    return await _get_quote_or_404(db, new.id, org_id)

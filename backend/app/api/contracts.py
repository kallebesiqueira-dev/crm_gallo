"""Versioned contracts / agreements — CRUD + status state machine (ADR-016).

State machine (the ONLY legal transitions; anything else → 409):

    draft ──send──▶ sent ──sign──▶ signed ──activate──▶ active
                                     │                     │
                                     └──terminate──────────┴──▶ terminated

`draft` is the only mutable status — editing a sent/signed/active
contract is rejected. Re-issuing instead clones the contract into a
fresh `draft` at `version + 1` (POST /{id}/resend); the prior row keeps
its terminal status and points forward via `superseded_by`. `expired`
is reached only by a future cron (auto_renew / end_date), never an
endpoint. Unlike a quote there are no line items — a contract carries a
single agreed `value`; itemisation lives on the linked source quote.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.database import get_db
from app.deps import ensure_can_mutate, get_current_org_id, get_current_user
from app.events import EventType, record_event
from app.logging_setup import get_logger
from app.models import Contract, ContractStatus, Quote, QuoteStatus, User
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, CursorPage, paginate
from app.schemas import ContractCreate, ContractOut, ContractUpdate
from app.services.contracts import next_contract_number

router = APIRouter(prefix="/api/contracts", tags=["contracts"])
log = get_logger(__name__)


async def _get_contract_or_404(
    db: AsyncSession, contract_id: uuid.UUID, org_id: uuid.UUID
) -> Contract:
    result = await db.execute(
        select(Contract).where(
            Contract.id == contract_id, Contract.organization_id == org_id
        )
    )
    contract = result.scalar_one_or_none()
    if not contract or contract.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return contract


def _require_draft(contract: Contract) -> None:
    if contract.status != ContractStatus.draft:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Contract is {contract.status.value}; only draft contracts are editable. "
                "Use POST /{id}/resend to issue a new version."
            ),
        )


@router.get("", response_model=CursorPage[ContractOut])
async def list_contracts(
    status_filter: ContractStatus | None = Query(default=None, alias="status"),
    deal_id: uuid.UUID | None = Query(default=None),
    customer_id: uuid.UUID | None = Query(default=None),
    quote_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, description="opaque keyset cursor"),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> CursorPage:
    stmt = select(Contract).where(Contract.organization_id == org_id)
    if status_filter is not None:
        stmt = stmt.where(Contract.status == status_filter)
    if deal_id is not None:
        stmt = stmt.where(Contract.deal_id == deal_id)
    if customer_id is not None:
        stmt = stmt.where(Contract.customer_id == customer_id)
    if quote_id is not None:
        stmt = stmt.where(Contract.quote_id == quote_id)
    return await paginate(db, stmt, Contract, limit=limit, cursor=cursor)


@router.post("", response_model=ContractOut, status_code=status.HTTP_201_CREATED)
async def create_contract(
    payload: ContractCreate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Contract:
    # Per-org advisory lock makes the read-then-insert of the contract
    # number race-safe (two concurrent creates can't grab the same
    # number). hashtext → int4, fits the bigint lock-key param; the
    # lock auto-releases at transaction end. The partial unique index
    # (organization_id, number, version) is the backstop.
    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"contract_number:{org_id}")))
    )
    number = await next_contract_number(db, org_id)

    data = payload.model_dump()
    data["owner_id"] = data.get("owner_id") or user.id
    contract = Contract(
        **data,
        organization_id=org_id,
        number=number,
        version=1,
        status=ContractStatus.draft,
    )
    db.add(contract)
    await db.flush()

    await record_audit(
        db,
        actor=user,
        action="contract.create",
        entity_type="contract",
        entity_id=contract.id,
        organization_id=org_id,
        metadata={"number": contract.number, "version": contract.version},
    )
    await record_event(
        db,
        event_type=EventType.contract_created,
        organization_id=org_id,
        payload={
            "contract_id": contract.id,
            "number": contract.number,
            "version": contract.version,
            "value": contract.value,
            "owner_id": contract.owner_id,
            "actor_user_id": user.id,
        },
    )
    await db.commit()
    return await _get_contract_or_404(db, contract.id, org_id)


@router.post(
    "/from-quote/{quote_id}",
    response_model=ContractOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_contract_from_quote(
    quote_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Contract:
    """Draft a contract pre-filled from an accepted quote.

    Convenience over the bare create — copies the quote's title, total
    (→ contract `value`), currency, and deal/customer links. The quote
    must be `accepted` (you don't paper a proposal the customer hasn't
    agreed to). The new contract starts as a `draft` you then refine
    (term, renewal, body) before sending.
    """
    quote = (
        await db.execute(
            select(Quote).where(Quote.id == quote_id, Quote.organization_id == org_id)
        )
    ).scalar_one_or_none()
    if not quote or quote.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.status != QuoteStatus.accepted:
        raise HTTPException(
            status_code=409,
            detail=f"Quote must be accepted to draft a contract (current: {quote.status.value}).",
        )

    await db.execute(
        select(func.pg_advisory_xact_lock(func.hashtext(f"contract_number:{org_id}")))
    )
    number = await next_contract_number(db, org_id)

    contract = Contract(
        organization_id=org_id,
        number=number,
        version=1,
        status=ContractStatus.draft,
        title=quote.title,
        currency=quote.currency,
        value=quote.total,
        quote_id=quote.id,
        deal_id=quote.deal_id,
        customer_id=quote.customer_id,
        owner_id=user.id,
    )
    db.add(contract)
    await db.flush()

    await record_audit(
        db,
        actor=user,
        action="contract.create_from_quote",
        entity_type="contract",
        entity_id=contract.id,
        organization_id=org_id,
        metadata={"number": contract.number, "quote_id": str(quote.id)},
    )
    await record_event(
        db,
        event_type=EventType.contract_created,
        organization_id=org_id,
        payload={
            "contract_id": contract.id,
            "number": contract.number,
            "version": contract.version,
            "value": contract.value,
            "quote_id": quote.id,
            "owner_id": contract.owner_id,
            "actor_user_id": user.id,
        },
    )
    await db.commit()
    return await _get_contract_or_404(db, contract.id, org_id)


@router.get("/{contract_id}", response_model=ContractOut)
async def get_contract(
    contract_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Contract:
    return await _get_contract_or_404(db, contract_id, org_id)


@router.patch("/{contract_id}", response_model=ContractOut)
async def update_contract(
    contract_id: uuid.UUID,
    payload: ContractUpdate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Contract:
    contract = await _get_contract_or_404(db, contract_id, org_id)
    ensure_can_mutate(user, contract.owner_id)
    _require_draft(contract)

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(contract, field, value)

    await record_audit(
        db,
        actor=user,
        action="contract.update",
        entity_type="contract",
        entity_id=contract.id,
        organization_id=org_id,
        metadata={"fields": list(changes.keys())},
    )
    await db.commit()
    return await _get_contract_or_404(db, contract.id, org_id)


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    contract = await _get_contract_or_404(db, contract_id, org_id)
    ensure_can_mutate(user, contract.owner_id)
    contract.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="contract.soft_delete",
        entity_type="contract",
        entity_id=contract.id,
        organization_id=org_id,
    )
    await db.commit()


@router.post("/{contract_id}/pdf", status_code=status.HTTP_202_ACCEPTED)
async def generate_contract_pdf_endpoint(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
):
    """Enqueue a contract PDF (ADR-016) and return 202.

    The worker renders the document and attaches it to the contract, so it
    surfaces in `GET /api/attachments?entity_type=contract&...` and
    downloads via the existing presigned-URL endpoint. Idempotent within a
    5-minute window — a double-click returns `{queued: false}`.
    """
    contract = await _get_contract_or_404(db, contract_id, org_id)
    ensure_can_mutate(user, contract.owner_id)

    from app.worker.queue import enqueue

    job = await enqueue(
        "generate_contract_pdf",
        str(contract.id),
        str(org_id),
        dedupe_key=f"contract_pdf:{contract.id}",
        dedupe_ttl_seconds=300,
    )
    if job is None:
        return {"queued": False, "dedupe": True}
    return {"queued": True, "job_id": job.job_id}


# ---------- State machine transitions ----------
@router.post("/{contract_id}/send", response_model=ContractOut)
async def send_contract(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Contract:
    contract = await _get_contract_or_404(db, contract_id, org_id)
    ensure_can_mutate(user, contract.owner_id)
    if contract.status != ContractStatus.draft:
        raise HTTPException(
            status_code=409,
            detail=f"Only a draft contract can be sent (current: {contract.status.value}).",
        )
    contract.status = ContractStatus.sent
    contract.sent_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="contract.send",
        entity_type="contract",
        entity_id=contract.id,
        organization_id=org_id,
        metadata={"number": contract.number, "version": contract.version},
    )
    await record_event(
        db,
        event_type=EventType.contract_sent,
        organization_id=org_id,
        payload={
            "contract_id": contract.id,
            "number": contract.number,
            "version": contract.version,
            "value": contract.value,
            "owner_id": contract.owner_id,
            "actor_user_id": user.id,
        },
    )
    await db.commit()
    return await _get_contract_or_404(db, contract.id, org_id)


@router.post("/{contract_id}/sign", response_model=ContractOut)
async def sign_contract(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Contract:
    return await _transition(
        db,
        contract_id,
        org_id,
        user,
        from_status=ContractStatus.sent,
        to_status=ContractStatus.signed,
        ts_field="signed_at",
        action="contract.sign",
        event_type=EventType.contract_signed,
    )


@router.post("/{contract_id}/activate", response_model=ContractOut)
async def activate_contract(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Contract:
    return await _transition(
        db,
        contract_id,
        org_id,
        user,
        from_status=ContractStatus.signed,
        to_status=ContractStatus.active,
        ts_field="activated_at",
        action="contract.activate",
        event_type=EventType.contract_activated,
    )


@router.post("/{contract_id}/terminate", response_model=ContractOut)
async def terminate_contract(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Contract:
    """Terminate a signed or active contract.

    The one transition with two valid source states — you can kill an
    agreement that was signed but never activated, or one already in
    force. `_transition` only checks a single `from_status`, so this is
    handled inline.
    """
    contract = await _get_contract_or_404(db, contract_id, org_id)
    ensure_can_mutate(user, contract.owner_id)
    if contract.status not in (ContractStatus.signed, ContractStatus.active):
        raise HTTPException(
            status_code=409,
            detail=(
                "Only a signed or active contract can be terminated "
                f"(current: {contract.status.value})."
            ),
        )
    contract.status = ContractStatus.terminated
    contract.terminated_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="contract.terminate",
        entity_type="contract",
        entity_id=contract.id,
        organization_id=org_id,
        metadata={"number": contract.number, "version": contract.version},
    )
    await record_event(
        db,
        event_type=EventType.contract_terminated,
        organization_id=org_id,
        payload={
            "contract_id": contract.id,
            "number": contract.number,
            "version": contract.version,
            "value": contract.value,
            "owner_id": contract.owner_id,
            "actor_user_id": user.id,
        },
    )
    await db.commit()
    return await _get_contract_or_404(db, contract.id, org_id)


async def _transition(
    db: AsyncSession,
    contract_id: uuid.UUID,
    org_id: uuid.UUID,
    user: User,
    *,
    from_status: ContractStatus,
    to_status: ContractStatus,
    ts_field: str,
    action: str,
    event_type: EventType,
) -> Contract:
    contract = await _get_contract_or_404(db, contract_id, org_id)
    ensure_can_mutate(user, contract.owner_id)
    if contract.status != from_status:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Contract must be {from_status.value} to become {to_status.value}; "
                f"current: {contract.status.value}."
            ),
        )
    contract.status = to_status
    setattr(contract, ts_field, datetime.now(UTC))
    await record_audit(
        db,
        actor=user,
        action=action,
        entity_type="contract",
        entity_id=contract.id,
        organization_id=org_id,
        metadata={"number": contract.number, "version": contract.version},
    )
    await record_event(
        db,
        event_type=event_type,
        organization_id=org_id,
        payload={
            "contract_id": contract.id,
            "number": contract.number,
            "version": contract.version,
            "value": contract.value,
            "owner_id": contract.owner_id,
            "actor_user_id": user.id,
        },
    )
    await db.commit()
    return await _get_contract_or_404(db, contract.id, org_id)


@router.post(
    "/{contract_id}/resend", response_model=ContractOut, status_code=status.HTTP_201_CREATED
)
async def resend_contract(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> Contract:
    """Re-issue a contract as a fresh draft at version + 1.

    Allowed once a contract has left draft (sent / signed / active /
    terminated / expired) — you don't re-issue something still being
    drafted; just edit it. The new revision copies the terms, keeps the
    same `number`, and starts as `draft`; the prior row points forward
    via `superseded_by`.
    """
    old = await _get_contract_or_404(db, contract_id, org_id)
    ensure_can_mutate(user, old.owner_id)
    if old.status == ContractStatus.draft:
        raise HTTPException(
            status_code=409,
            detail="Contract is still a draft — edit it directly instead of re-issuing.",
        )

    # Highest existing version for this number, across soft-deleted rows
    # too, so a re-issue never reuses a version another revision held.
    max_version = (
        await db.execute(
            select(func.max(Contract.version))
            .where(Contract.organization_id == org_id, Contract.number == old.number)
            .execution_options(include_deleted=True)
        )
    ).scalar_one()

    new = Contract(
        organization_id=org_id,
        quote_id=old.quote_id,
        deal_id=old.deal_id,
        customer_id=old.customer_id,
        number=old.number,
        version=(max_version or old.version) + 1,
        status=ContractStatus.draft,
        title=old.title,
        currency=old.currency,
        value=old.value,
        effective_date=old.effective_date,
        end_date=old.end_date,
        auto_renew=old.auto_renew,
        renewal_term_months=old.renewal_term_months,
        body=old.body,
        notes=old.notes,
        owner_id=old.owner_id,
    )
    db.add(new)
    await db.flush()
    old.superseded_by = new.id

    await record_audit(
        db,
        actor=user,
        action="contract.resend",
        entity_type="contract",
        entity_id=new.id,
        organization_id=org_id,
        metadata={"number": new.number, "from_version": old.version, "to_version": new.version},
    )
    await db.commit()
    return await _get_contract_or_404(db, new.id, org_id)

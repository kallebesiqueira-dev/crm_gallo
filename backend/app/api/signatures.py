"""E-signature requests on quotes — CRUD + signing state machine (ADR-016).

State machine (the ONLY legal transitions; anything else → 409):

    drafted ──send──▶ sent ──view──▶ viewed ──sign──▶ signed   (terminal)
                       │               │
                       └────decline────┴──▶ declined            (terminal)
    (drafted|sent|viewed) ──cancel──▶ cancelled                 (terminal)

Two signing surfaces feed `signed`:
  * the MANUAL provider — the external signer opens an opaque token link and
    signs in-app (`GET`/`POST /sign/{token}`, unauthenticated; the token is
    the credential, like an org-invite link);
  * a VENDOR provider (Skribble/Scrive) — completion arrives via the inbound,
    HMAC-verified webhook (`POST /webhook`).

A request signs exactly one document — a quote XOR a contract (`quote_id` /
`contract_id`, guarded by a DB CHECK). Completion side effect: signing a
request whose quote is still `sent` transitions that quote to `accepted` (a
signed quote IS an acceptance); signing a request whose contract is still
`sent` transitions that contract to `signed`.

RLS note: `signature_requests` is tenant-isolated by the `app.current_org_id`
GUC. The unauthenticated token + webhook paths have no logged-in user, so the
tenant is recovered from the bearer token (`{org_hex}.{secret}`) / the signed
webpayload's `organization_id` and applied via `set_current_org_id` BEFORE the
first query — otherwise RLS filters the row out.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.config import get_settings
from app.database import get_db, set_current_org_id
from app.deps import ensure_can_mutate, get_current_org_id, get_current_user
from app.events import EventType, record_event
from app.logging_setup import get_logger
from app.models import (
    Contract,
    ContractStatus,
    FileAttachment,
    Organization,
    Quote,
    QuoteStatus,
    SignatureRequest,
    SignatureStatus,
    User,
)
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, CursorPage, paginate
from app.schemas import (
    SignatureDeclineIn,
    SignatureRequestCreate,
    SignatureRequestOut,
    SignatureSignContext,
    SignatureSignIn,
)
from app.signing import get_provider, store_signature_artifact
from app.webhook_sign import SIGNATURE_HEADER, verify_signature

router = APIRouter(prefix="/api/signatures", tags=["signatures"])
log = get_logger(__name__)

# Non-terminal states a request can be cancelled from.
_CANCELLABLE = {SignatureStatus.drafted, SignatureStatus.sent, SignatureStatus.viewed}
# States the signer can act on (sign / view / decline) once the envelope is out.
_OPEN_FOR_SIGNER = {SignatureStatus.sent, SignatureStatus.viewed}


def _doc_ref(req: SignatureRequest) -> dict:
    """The document this request signs, for event payloads — exactly one of
    the two is set."""
    return {"quote_id": req.quote_id, "contract_id": req.contract_id}


# ---------- token helpers ----------
def _mint_sign_token(org_id: uuid.UUID) -> str:
    """Self-describing bearer token: `{org_hex}.{secret}`. The org prefix
    lets the unauthenticated sign endpoint set the RLS GUC before the
    lookup; the 128-bit secret is what actually gates access (the prefix
    is not a secret — org ids aren't confidential)."""
    return f"{org_id.hex}.{secrets.token_urlsafe(16)}"


def _org_from_token(token: str) -> uuid.UUID | None:
    prefix = token.split(".", 1)[0]
    try:
        return uuid.UUID(hex=prefix)
    except ValueError:
        return None


def _signing_url(token: str | None) -> str | None:
    if not token:
        return None
    base = get_settings().frontend_base_url.rstrip("/")
    return f"{base}/sign/{token}"


def _to_out(req: SignatureRequest, *, signing_url: str | None = None) -> SignatureRequestOut:
    out = SignatureRequestOut.model_validate(req)
    if signing_url is not None:
        out = out.model_copy(update={"signing_url": signing_url})
    return out


def _client_ip(request: Request) -> str | None:
    # X-Forwarded-For (first hop) when behind a proxy, else the socket peer.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


# ---------- shared loaders ----------
async def _get_request_or_404(
    db: AsyncSession, request_id: uuid.UUID, org_id: uuid.UUID
) -> SignatureRequest:
    result = await db.execute(
        select(SignatureRequest).where(
            SignatureRequest.id == request_id,
            SignatureRequest.organization_id == org_id,
        )
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Signature request not found")
    return req


async def _get_request_by_token(db: AsyncSession, token: str) -> SignatureRequest:
    """Resolve a request from its bearer token. Sets the RLS GUC from the
    token's org prefix first so the (RLS-scoped) lookup can see the row."""
    org_id = _org_from_token(token)
    if org_id is None:
        raise HTTPException(status_code=404, detail="Signature request not found")
    set_current_org_id(org_id)
    result = await db.execute(
        select(SignatureRequest).where(
            SignatureRequest.sign_token == token,
            SignatureRequest.organization_id == org_id,
        )
    )
    req = result.scalar_one_or_none()
    if req is None:
        # 404 for a bad/forged token — no signal about which orgs exist.
        raise HTTPException(status_code=404, detail="Signature request not found")
    return req


async def _maybe_accept_quote(
    db: AsyncSession, *, quote_id: uuid.UUID, org_id: uuid.UUID
) -> None:
    """A completed signature accepts the still-open quote it signed."""
    quote = (
        await db.execute(
            select(Quote).where(Quote.id == quote_id, Quote.organization_id == org_id)
        )
    ).scalar_one_or_none()
    if quote is None or quote.status != QuoteStatus.sent:
        return
    quote.status = QuoteStatus.accepted
    quote.accepted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=None,
        action="quote.accept",
        entity_type="quote",
        entity_id=quote.id,
        organization_id=org_id,
        metadata={"number": quote.number, "version": quote.version, "via": "signature"},
    )
    await record_event(
        db,
        event_type=EventType.quote_accepted,
        organization_id=org_id,
        payload={
            "quote_id": quote.id,
            "number": quote.number,
            "version": quote.version,
            "total": quote.total,
            "owner_id": quote.owner_id,
            "via": "signature",
        },
    )


async def _maybe_sign_contract(
    db: AsyncSession, *, contract_id: uuid.UUID, org_id: uuid.UUID
) -> None:
    """A completed signature moves the still-open contract to `signed`
    (mirrors the contract state machine's manual sign transition)."""
    contract = (
        await db.execute(
            select(Contract).where(Contract.id == contract_id, Contract.organization_id == org_id)
        )
    ).scalar_one_or_none()
    if contract is None or contract.status != ContractStatus.sent:
        return
    contract.status = ContractStatus.signed
    contract.signed_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=None,
        action="contract.sign",
        entity_type="contract",
        entity_id=contract.id,
        organization_id=org_id,
        metadata={"number": contract.number, "version": contract.version, "via": "signature"},
    )
    await record_event(
        db,
        event_type=EventType.contract_signed,
        organization_id=org_id,
        payload={
            "contract_id": contract.id,
            "number": contract.number,
            "version": contract.version,
            "value": contract.value,
            "owner_id": contract.owner_id,
            "via": "signature",
        },
    )


async def _load_document_summary(
    db: AsyncSession, req: SignatureRequest
) -> tuple[str, str, str, float, str] | None:
    """(document_type, number, title, total, currency) for the signed
    document, or None if it has since been deleted. Exactly one of
    quote_id/contract_id is set (DB CHECK)."""
    if req.quote_id is not None:
        q = (
            await db.execute(select(Quote).where(Quote.id == req.quote_id))
        ).scalar_one_or_none()
        if q is None:
            return None
        return ("quote", q.number, q.title, float(q.total), q.currency)
    c = (
        await db.execute(select(Contract).where(Contract.id == req.contract_id))
    ).scalar_one_or_none()
    if c is None:
        return None
    return ("contract", c.number, c.title, float(c.value), c.currency)


async def _complete_signature(
    db: AsyncSession,
    req: SignatureRequest,
    *,
    typed_name: str | None,
    ip: str | None,
    user_agent: str | None,
    via: str,
) -> None:
    """Mark a request `signed`, persist the audit trail to S3, and advance the
    underlying document (quote → accepted, contract → signed). Shared by the
    manual sign endpoint and the inbound vendor webhook. Caller commits."""
    now = datetime.now(UTC)
    summary = await _load_document_summary(db, req)
    doc_type = summary[0] if summary else ("quote" if req.quote_id else "contract")
    doc_number = summary[1] if summary else None

    audit_trail = {
        "signature_request_id": str(req.id),
        "document_type": doc_type,
        "quote_id": str(req.quote_id) if req.quote_id else None,
        "contract_id": str(req.contract_id) if req.contract_id else None,
        "document_number": doc_number,
        "provider": req.provider,
        "signer_name": req.signer_name,
        "signer_email": req.signer_email,
        "typed_name": typed_name,
        "signed_ip": ip,
        "signed_user_agent": user_agent,
        "signed_at": now.isoformat(),
        "via": via,
    }
    att = await store_signature_artifact(
        db,
        organization_id=req.organization_id,
        request_id=req.id,
        filename=f"signature-{doc_number or req.id}-audit.json",
        audit_trail=audit_trail,
    )

    req.status = SignatureStatus.signed
    req.signed_at = now
    req.signed_ip = ip
    req.signed_user_agent = user_agent
    req.signed_document_key = att.storage_key

    await record_audit(
        db,
        actor=None,
        action="signature.sign",
        entity_type="signature_request",
        entity_id=req.id,
        organization_id=req.organization_id,
        metadata={"provider": req.provider, "via": via, "artifact_id": str(att.id)},
    )
    await record_event(
        db,
        event_type=EventType.signature_signed,
        organization_id=req.organization_id,
        payload={
            "signature_request_id": req.id,
            **_doc_ref(req),
            "provider": req.provider,
            "signer_email": req.signer_email,
            "via": via,
        },
    )
    if req.quote_id is not None:
        await _maybe_accept_quote(db, quote_id=req.quote_id, org_id=req.organization_id)
    else:
        await _maybe_sign_contract(db, contract_id=req.contract_id, org_id=req.organization_id)


# ---------- authenticated CRUD ----------
@router.get("", response_model=CursorPage[SignatureRequestOut])
async def list_signature_requests(
    quote_id: uuid.UUID | None = Query(default=None),
    contract_id: uuid.UUID | None = Query(default=None),
    status_filter: SignatureStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(default=None, description="opaque keyset cursor"),
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> CursorPage:
    stmt = select(SignatureRequest).where(SignatureRequest.organization_id == org_id)
    if quote_id is not None:
        stmt = stmt.where(SignatureRequest.quote_id == quote_id)
    if contract_id is not None:
        stmt = stmt.where(SignatureRequest.contract_id == contract_id)
    if status_filter is not None:
        stmt = stmt.where(SignatureRequest.status == status_filter)
    return await paginate(db, stmt, SignatureRequest, limit=limit, cursor=cursor)


@router.post("", response_model=SignatureRequestOut, status_code=status.HTTP_201_CREATED)
async def create_signature_request(
    payload: SignatureRequestCreate,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> SignatureRequestOut:
    # Exactly one of quote_id/contract_id is set (schema validator + DB CHECK).
    # Resolve the referenced document, enforce it is in `sent` state, and link
    # its most recent generated PDF as the (informational) source attachment.
    entity_type: str
    entity_id: uuid.UUID
    if payload.quote_id is not None:
        quote = (
            await db.execute(
                select(Quote).where(Quote.id == payload.quote_id, Quote.organization_id == org_id)
            )
        ).scalar_one_or_none()
        if quote is None or quote.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Quote not found")
        if quote.status != QuoteStatus.sent:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Only a sent quote can be sent for signature "
                    f"(current: {quote.status.value})."
                ),
            )
        entity_type, entity_id = "quote", quote.id
    else:
        contract = (
            await db.execute(
                select(Contract).where(
                    Contract.id == payload.contract_id, Contract.organization_id == org_id
                )
            )
        ).scalar_one_or_none()
        if contract is None or contract.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Contract not found")
        if contract.status != ContractStatus.sent:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Only a sent contract can be sent for signature "
                    f"(current: {contract.status.value})."
                ),
            )
        entity_type, entity_id = "contract", contract.id

    # Link the most recent generated PDF as the source document, if one exists
    # — purely informational (the signer sees the summary; the PDF is the
    # formal artifact). None is fine.
    doc_id = (
        await db.execute(
            select(FileAttachment.id)
            .where(
                FileAttachment.entity_type == entity_type,
                FileAttachment.entity_id == entity_id,
                FileAttachment.organization_id == org_id,
            )
            .order_by(FileAttachment.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    req = SignatureRequest(
        organization_id=org_id,
        quote_id=payload.quote_id,
        contract_id=payload.contract_id,
        provider=get_settings().signing_provider.lower(),
        status=SignatureStatus.drafted,
        signer_name=payload.signer_name,
        signer_email=str(payload.signer_email),
        message=payload.message,
        document_attachment_id=doc_id,
        owner_id=user.id,
    )
    db.add(req)
    await db.flush()
    await record_audit(
        db,
        actor=user,
        action="signature.create",
        entity_type="signature_request",
        entity_id=req.id,
        organization_id=org_id,
        metadata={f"{entity_type}_id": str(entity_id), "provider": req.provider},
    )
    await db.commit()
    return _to_out(await _get_request_or_404(db, req.id, org_id))


@router.get("/{request_id}", response_model=SignatureRequestOut)
async def get_signature_request(
    request_id: uuid.UUID,
    _: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> SignatureRequestOut:
    req = await _get_request_or_404(db, request_id, org_id)
    return _to_out(req, signing_url=_signing_url(req.sign_token))


@router.post("/{request_id}/send", response_model=SignatureRequestOut)
async def send_signature_request(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> SignatureRequestOut:
    """drafted → sent. Mints the signing link and hands the envelope to the
    configured provider. Manual is fully in-app; vendor adapters create the
    envelope here (raise loudly until configured)."""
    req = await _get_request_or_404(db, request_id, org_id)
    ensure_can_mutate(user, req.owner_id)
    if req.status != SignatureStatus.drafted:
        raise HTTPException(
            status_code=409,
            detail=f"Only a drafted request can be sent (current: {req.status.value}).",
        )

    req.sign_token = _mint_sign_token(org_id)
    req.status = SignatureStatus.sent
    req.sent_at = datetime.now(UTC)

    provider = get_provider()
    handle = await provider.create_envelope(req)
    if handle.external_id is not None:
        req.external_id = handle.external_id

    await record_audit(
        db,
        actor=user,
        action="signature.send",
        entity_type="signature_request",
        entity_id=req.id,
        organization_id=org_id,
        metadata={"provider": req.provider, "signer_email": req.signer_email},
    )
    await record_event(
        db,
        event_type=EventType.signature_requested,
        organization_id=org_id,
        payload={
            "signature_request_id": req.id,
            **_doc_ref(req),
            "provider": req.provider,
            "signer_email": req.signer_email,
        },
    )
    await db.commit()
    req = await _get_request_or_404(db, req.id, org_id)
    return _to_out(req, signing_url=handle.signing_url or _signing_url(req.sign_token))


@router.post("/{request_id}/cancel", response_model=SignatureRequestOut)
async def cancel_signature_request(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> SignatureRequestOut:
    req = await _get_request_or_404(db, request_id, org_id)
    ensure_can_mutate(user, req.owner_id)
    if req.status not in _CANCELLABLE:
        raise HTTPException(
            status_code=409,
            detail=f"A {req.status.value} request cannot be cancelled.",
        )
    req.status = SignatureStatus.cancelled
    await record_audit(
        db,
        actor=user,
        action="signature.cancel",
        entity_type="signature_request",
        entity_id=req.id,
        organization_id=org_id,
    )
    await record_event(
        db,
        event_type=EventType.signature_cancelled,
        organization_id=org_id,
        payload={"signature_request_id": req.id, **_doc_ref(req)},
    )
    await db.commit()
    return _to_out(await _get_request_or_404(db, req.id, org_id))


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_signature_request(
    request_id: uuid.UUID,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    req = await _get_request_or_404(db, request_id, org_id)
    ensure_can_mutate(user, req.owner_id)
    req.deleted_at = datetime.now(UTC)
    await record_audit(
        db,
        actor=user,
        action="signature.soft_delete",
        entity_type="signature_request",
        entity_id=req.id,
        organization_id=org_id,
    )
    await db.commit()


# ---------- unauthenticated signer surface (manual provider) ----------
@router.get("/sign/{token}", response_model=SignatureSignContext)
async def view_signing_page(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> SignatureSignContext:
    """The signer's view of the envelope. No auth — the token is the
    credential. Fetching marks a `sent` request `viewed`."""
    req = await _get_request_by_token(db, token)
    if req.status in (SignatureStatus.signed, SignatureStatus.countersigned):
        raise HTTPException(status_code=410, detail="This document has already been signed.")
    if req.status in (SignatureStatus.declined, SignatureStatus.cancelled):
        raise HTTPException(status_code=410, detail=f"This request was {req.status.value}.")

    summary = await _load_document_summary(db, req)
    if summary is None:
        raise HTTPException(status_code=404, detail="The document no longer exists.")
    doc_type, doc_number, doc_title, doc_total, doc_currency = summary
    org_name = (
        await db.execute(select(Organization.name).where(Organization.id == req.organization_id))
    ).scalar_one_or_none() or "CRM Gallo"

    if req.status == SignatureStatus.sent:
        req.status = SignatureStatus.viewed
        req.viewed_at = datetime.now(UTC)
        await record_event(
            db,
            event_type=EventType.signature_viewed,
            organization_id=req.organization_id,
            payload={"signature_request_id": req.id, **_doc_ref(req)},
        )
        await db.commit()

    return SignatureSignContext(
        status=req.status,
        signer_name=req.signer_name,
        document_type=doc_type,
        document_number=doc_number,
        document_title=doc_title,
        document_total=doc_total,
        document_currency=doc_currency,
        organization_name=org_name,
    )


@router.post("/sign/{token}", response_model=SignatureRequestOut)
async def submit_signature(
    token: str,
    payload: SignatureSignIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SignatureRequestOut:
    """The signer signs (manual provider). Captures IP / user-agent
    server-side as the consent record."""
    req = await _get_request_by_token(db, token)
    if req.status not in _OPEN_FOR_SIGNER:
        raise HTTPException(
            status_code=409,
            detail=f"This request is {req.status.value} and can no longer be signed.",
        )
    await _complete_signature(
        db,
        req,
        typed_name=payload.typed_name,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:400] or None,
        via="manual",
    )
    await db.commit()
    return _to_out(await _get_request_by_token(db, token))


@router.post("/sign/{token}/decline", response_model=SignatureRequestOut)
async def decline_signature(
    token: str,
    payload: SignatureDeclineIn,
    db: AsyncSession = Depends(get_db),
) -> SignatureRequestOut:
    req = await _get_request_by_token(db, token)
    if req.status not in _OPEN_FOR_SIGNER:
        raise HTTPException(
            status_code=409,
            detail=f"This request is {req.status.value} and can no longer be declined.",
        )
    req.status = SignatureStatus.declined
    req.declined_at = datetime.now(UTC)
    req.decline_reason = payload.reason
    await record_event(
        db,
        event_type=EventType.signature_declined,
        organization_id=req.organization_id,
        payload={"signature_request_id": req.id, **_doc_ref(req)},
    )
    await db.commit()
    return _to_out(await _get_request_by_token(db, token))


# ---------- inbound vendor webhook ----------
@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def signature_webhook(
    request: Request,
    signature: str | None = Header(default=None, alias=SIGNATURE_HEADER),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Inbound completion events from a vendor provider (Skribble/Scrive),
    HMAC-verified with `SIGNING_WEBHOOK_SECRET` (the existing webhook-sign
    format). The signed body carries `organization_id` (envelope metadata)
    so the RLS GUC can be set before the lookup.

    Body shape:
        {"organization_id": "...", "external_id": "...",
         "event": "viewed|signed|declined"}

    No auth (the vendor is the caller); the HMAC + the per-envelope
    `external_id` are what bind the event to a request. Unverified or
    unconfigured → reject, never apply state blindly.
    """
    secret = get_settings().signing_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Signature webhook is not configured")
    if not signature:
        raise HTTPException(status_code=400, detail=f"Missing {SIGNATURE_HEADER} header")

    body = await request.body()
    if not verify_signature(secret, body, signature):
        log.warning("signature_webhook.invalid_signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        data = json.loads(body)
        org_id = uuid.UUID(str(data["organization_id"]))
        external_id = str(data["external_id"])
        event = str(data["event"])
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Malformed webhook payload") from exc

    set_current_org_id(org_id)
    req = (
        await db.execute(
            select(SignatureRequest).where(
                SignatureRequest.external_id == external_id,
                SignatureRequest.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if req is None:
        # Unknown envelope (already cleaned up, or wrong org metadata). 2xx
        # so the vendor doesn't hammer retries for an event we can't place.
        log.info("signature_webhook.unknown_envelope", external_id=external_id)
        return

    if event == "viewed":
        if req.status == SignatureStatus.sent:
            req.status = SignatureStatus.viewed
            req.viewed_at = datetime.now(UTC)
            await record_event(
                db,
                event_type=EventType.signature_viewed,
                organization_id=org_id,
                payload={"signature_request_id": req.id, **_doc_ref(req)},
            )
            await db.commit()
    elif event == "signed":
        if req.status in _OPEN_FOR_SIGNER:
            await _complete_signature(
                db, req, typed_name=None, ip=None, user_agent=None, via="webhook"
            )
            await db.commit()
    elif event == "declined":
        if req.status in _OPEN_FOR_SIGNER:
            req.status = SignatureStatus.declined
            req.declined_at = datetime.now(UTC)
            await record_event(
                db,
                event_type=EventType.signature_declined,
                organization_id=org_id,
                payload={"signature_request_id": req.id, **_doc_ref(req)},
            )
            await db.commit()
    else:
        log.info("signature_webhook.ignored_event", event=event, external_id=external_id)

"""Public (unauthenticated) API surface — landing-page chatbot.

Every endpoint here is rate-limited per IP, input-sanitised by Pydantic, and
degrades to a safe static answer instead of erroring, so the marketing site
keeps working with the AI turned off or unreachable. No secrets are returned.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit
from app.config import get_settings
from app.database import get_db, set_current_org_id
from app.models import Lead, WebForm
from app.rate_limit import limiter
from app.services.chatbot import answer_question
from app.web_forms import parse_org_id

settings = get_settings()
router = APIRouter(prefix="/api/public", tags=["public"])

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 8

# Bots fill every field they see; this one is hidden via CSS in the embed
# snippet, so a human leaves it blank. A non-empty value => drop the
# submission silently (return success so the bot gets no signal).
HONEYPOT_FIELD = "website"
DEFAULT_THANK_YOU = "/?web_form=ok"

# Column caps on app.models.Lead — truncate untrusted input to fit so an
# oversized field can't 500 the public endpoint.
_LEAD_LIMITS = {
    "first_name": 120,
    "last_name": 120,
    "email": 255,
    "phone": 50,
    "company": 255,
}


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatbotRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    # Short rolling context. Capped server-side regardless of what's sent.
    history: list[ChatTurn] | None = Field(default=None, max_length=MAX_HISTORY_TURNS * 2)
    locale: str | None = Field(default=None, max_length=8)


class ChatbotResponse(BaseModel):
    message: str
    source: Literal["ai", "fallback"]


@router.post("/chatbot", response_model=ChatbotResponse)
@limiter.limit(f"{settings.rate_limit_chatbot_per_minute}/minute")
async def chatbot(request: Request, payload: ChatbotRequest) -> ChatbotResponse:
    """Landing-page pre-sales assistant. Public + per-IP rate-limited.

    `request` is required by the SlowAPI limiter. Input is sanitised (trim +
    length caps from the schema); the answer never echoes secrets and always
    falls back to a static professional reply on AI failure.
    """
    history = [
        (turn.role, turn.content.strip())
        for turn in (payload.history or [])
        if turn.content.strip()
    ][-MAX_HISTORY_TURNS:]
    text, source = await answer_question(payload.message, history, payload.locale)
    return ChatbotResponse(message=text, source=source)


# ---------- Web-to-Lead public capture ----------
async def _read_submission(request: Request) -> tuple[dict[str, str], bool]:
    """Parse a form post into a flat str→str dict, plus whether the caller
    wants a JSON reply (vs. a browser redirect).

    Accepts both ``application/x-www-form-urlencoded`` / ``multipart`` (a raw
    HTML ``<form>``, which needs no CORS) and ``application/json`` (a fetch
    caller). Values are coerced to plain strings; the endpoint owns
    validation and truncation.
    """
    ctype = request.headers.get("content-type", "")
    accept = request.headers.get("accept", "")
    if ctype.startswith("application/json"):
        try:
            raw = await request.json()
        except Exception:
            raw = {}
        data = raw if isinstance(raw, dict) else {}
        parsed = {k: ("" if v is None else str(v)) for k, v in data.items()}
        return parsed, True
    form = await request.form()
    parsed = {k: str(v) for k, v in form.items()}
    wants_json = "application/json" in accept
    return parsed, wants_json


def _split_name(data: dict[str, str]) -> tuple[str, str]:
    """Derive (first_name, last_name) — both NOT NULL on Lead. Accepts an
    explicit first/last pair or a single ``name`` field split on whitespace."""
    first = (data.get("first_name") or "").strip()
    last = (data.get("last_name") or "").strip()
    if not first:
        full = (data.get("name") or "").strip()
        if full:
            parts = full.split(None, 1)
            first = parts[0]
            if not last and len(parts) > 1:
                last = parts[1]
    return first, last


def _clip(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return value[: _LEAD_LIMITS[field]]


@router.post("/forms/{token}/submit")
@limiter.limit(f"{settings.rate_limit_form_submit_per_minute}/minute")
async def submit_form(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Public, unauthenticated Web-to-Lead capture.

    The ``token`` embeds its owning org, so we recover the tenant, set the
    RLS GUC, and look the form up UNDER row-level security before any session
    exists (see ``app.web_forms``). A forged/cross-org token sets the wrong
    GUC → zero rows → 404, so this can't reach into another tenant.

    Anti-spam (free tier): a hidden honeypot field + a per-IP rate limit.
    Turnstile/hCaptcha can layer on later.
    """
    org_id = parse_org_id(token)
    if org_id is None:
        raise HTTPException(status_code=404, detail="Form not found")
    set_current_org_id(org_id)

    form = (
        await db.execute(
            select(WebForm).where(
                WebForm.token == token,
                WebForm.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    # 404 alike for bad token, cross-org, or paused form — no signal to a
    # probing client about which tokens/orgs exist.
    if form is None or not form.active:
        raise HTTPException(status_code=404, detail="Form not found")

    data, wants_json = await _read_submission(request)

    def _ok() -> Response:
        if wants_json:
            return JSONResponse({"ok": True})
        target = form.redirect_url or DEFAULT_THANK_YOU
        # 303 so the browser follows with GET (POST/redirect/GET).
        return RedirectResponse(url=target, status_code=303)

    # Honeypot: a bot filled the hidden field → silently accept, create
    # nothing. Looks identical to success so the bot learns nothing.
    if (data.get(HONEYPOT_FIELD) or "").strip():
        return _ok()

    first_name, last_name = _split_name(data)
    if not first_name:
        raise HTTPException(status_code=422, detail="Name is required")

    lead = Lead(
        organization_id=org_id,
        first_name=first_name[: _LEAD_LIMITS["first_name"]],
        last_name=last_name[: _LEAD_LIMITS["last_name"]],
        email=_clip(data.get("email"), "email"),
        phone=_clip(data.get("phone"), "phone"),
        company=_clip(data.get("company"), "company"),
        notes=(data.get("message") or data.get("notes") or "").strip() or None,
        source=form.default_source or "Web Form",
        owner_id=form.created_by_user_id,
    )
    db.add(lead)
    try:
        await db.flush()
    except IntegrityError:
        # Live unique-email index: a returning visitor whose email is already
        # a lead. Treat as success — don't leak that they're already known,
        # and don't error a legitimate resubmit.
        await db.rollback()
        return _ok()

    form.submission_count += 1
    await record_audit(
        db,
        actor=None,
        action="web_form.submit",
        entity_type="lead",
        entity_id=lead.id,
        organization_id=org_id,
        metadata={"form_id": str(form.id), "source": lead.source},
    )
    await db.commit()
    return _ok()

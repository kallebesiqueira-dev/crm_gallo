"""Report-an-issue support form.

`POST /api/support` (multipart) takes a category + title + description (plus the
auto-captured page URL / user-agent and an optional screenshot) and emails the
report to the support inbox. Email goes out via the configured provider directly
(one recipient, one language — no need for the localized template pipeline). The
optional screenshot is stored in the attachments bucket and linked from the mail.
"""

import uuid
from html import escape as h
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_org_id, get_current_user
from app.email import RenderedEmail, get_provider
from app.logging_setup import get_logger
from app.models import User
from app.storage import presigned_download_url, put_object

router = APIRouter(prefix="/api/support", tags=["support"])

settings = get_settings()
log = get_logger(__name__)

SUPPORT_INBOX = "gallo-crm@hotmail.com"
_ALLOWED_IMG = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_CATEGORIES = {"technical", "bug", "feature", "question", "other"}


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def report_issue(
    category: Annotated[str, Form()],
    title: Annotated[str, Form()],
    description: Annotated[str, Form()],
    page_url: Annotated[str, Form()] = "",
    user_agent: Annotated[str, Form()] = "",
    screenshot: Annotated[UploadFile | None, File()] = None,
    user: User = Depends(get_current_user),
    org_id: uuid.UUID = Depends(get_current_org_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    title = title.strip()
    description = description.strip()
    if not title or not description:
        raise HTTPException(status_code=400, detail="Title and description are required")
    if category not in _CATEGORIES:
        category = "other"

    # Optional screenshot → attachments bucket, linked (not embedded) in the mail.
    shot_url: str | None = None
    if screenshot is not None and screenshot.filename:
        if (screenshot.content_type or "") not in _ALLOWED_IMG:
            raise HTTPException(status_code=400, detail="Screenshot must be an image")
        body = await screenshot.read()
        if len(body) > settings.attachment_max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Screenshot too large"
            )
        if body:
            key = f"org-{org_id}/support/{uuid.uuid4()}"
            await put_object(key, body, screenshot.content_type or "image/png")
            shot_url = await presigned_download_url(key, filename="screenshot.png")

    subject = f"[CRM Gallo • {category}] {title}"
    rows = [
        ("Category", category),
        ("From", f"{user.full_name} <{user.email}>"),
        ("Org", str(org_id)),
        ("Page", page_url or "—"),
        ("Browser", user_agent or "—"),
    ]
    # All cells escaped — title/description/page_url/user-agent are user input.
    meta_html = "".join(
        f"<tr><td style='padding:2px 10px;color:#888'>{h(k)}</td>"
        f"<td style='padding:2px 10px'>{h(v)}</td></tr>"
        for k, v in rows
    )
    shot_html = (
        f"<p style='margin-top:12px'><a href='{h(shot_url)}'>View screenshot</a></p>"
        if shot_url
        else ""
    )
    html = (
        f"<h2 style='margin:0 0 8px'>{h(title)}</h2>"
        f"<p style='white-space:pre-wrap;margin:0 0 16px'>{h(description)}</p>"
        f"<table style='border-top:1px solid #eee;font-size:13px'>{meta_html}</table>" + shot_html
    )
    text = (
        f"{title}\n\n{description}\n\n"
        + "\n".join(f"{k}: {v}" for k, v in rows)
        + (f"\n\nScreenshot: {shot_url}" if shot_url else "")
    )

    try:
        await get_provider().send(
            to=SUPPORT_INBOX, message=RenderedEmail(subject=subject, html=html, text=text)
        )
    except Exception:
        log.exception("support.email_failed", category=category, user=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send your report right now. Please try again.",
        ) from None

    log.info(
        "support.reported", category=category, user=str(user.id), has_shot=shot_url is not None
    )
    return {"ok": True}

"""WhatsApp Business Cloud API plumbing — signature, parsing, sending.

Pure functions + a thin httpx send. No DB, no FastAPI: the API layer
(`app.api.whatsapp`) and the worker (`send_whatsapp_message`) call into
here so the transport/format details live in one testable place.

Security boundary: `verify_signature` is the ONLY thing that lets an
inbound POST mutate tenant data. Meta signs every webhook body with
`X-Hub-Signature-256 = sha256=HMAC-SHA256(app_secret, raw_body)`; we
recompute over the EXACT bytes received (never the re-serialized JSON,
which would differ) and compare in constant time.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
import structlog

from app.config import get_settings
from app.models import MessageStatus, MessageType

log = structlog.get_logger(__name__)

SIGNATURE_HEADER = "X-Hub-Signature-256"
_SIGNATURE_PREFIX = "sha256="
_SEND_TIMEOUT_S = 15.0

# Meta message `type` string → our MessageType enum. Anything absent maps to
# `unsupported` so an unmodeled payload is persisted, not dropped.
_TYPE_MAP: dict[str, MessageType] = {
    "text": MessageType.text,
    "image": MessageType.image,
    "document": MessageType.document,
    "audio": MessageType.audio,
    "video": MessageType.video,
    "sticker": MessageType.sticker,
    "location": MessageType.location,
    "contacts": MessageType.contacts,
}

# Meta status `status` string → our MessageStatus enum.
_STATUS_MAP: dict[str, MessageStatus] = {
    "sent": MessageStatus.sent,
    "delivered": MessageStatus.delivered,
    "read": MessageStatus.read,
    "failed": MessageStatus.failed,
}


class WhatsAppNotConfigured(RuntimeError):
    """Raised when an inbound POST arrives but WHATSAPP_APP_SECRET is unset —
    we refuse to accept unverifiable messages rather than trust the network."""


class WhatsAppSendError(RuntimeError):
    """A Graph API send failed. Carries the HTTP status + Meta error body so
    the worker can persist a useful `Message.error` and decide on retry."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(slots=True)
class InboundMessage:
    phone_number_id: str
    contact_wa_id: str
    contact_name: str | None
    wa_message_id: str
    type: MessageType
    body: str | None
    media_id: str | None
    timestamp: datetime


@dataclass(slots=True)
class StatusUpdate:
    phone_number_id: str
    wa_message_id: str
    status: MessageStatus
    timestamp: datetime
    error: str | None = None


@dataclass(slots=True)
class ParsedWebhook:
    messages: list[InboundMessage] = field(default_factory=list)
    statuses: list[StatusUpdate] = field(default_factory=list)


def verify_signature(raw_body: bytes, header: str | None) -> bool:
    """Constant-time-verify Meta's `X-Hub-Signature-256` over the raw body.

    Returns False (never raises) for a missing/malformed header or a
    mismatch. Raises `WhatsAppNotConfigured` only when the app secret itself
    is unset — that's an operator error the caller turns into a 503, distinct
    from a forged request (403).
    """
    settings = get_settings()
    secret = settings.whatsapp_app_secret
    if not secret:
        raise WhatsAppNotConfigured("WHATSAPP_APP_SECRET is not set")
    if not header or not header.startswith(_SIGNATURE_PREFIX):
        return False
    provided = header[len(_SIGNATURE_PREFIX) :]
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


def verify_challenge(mode: str | None, token: str | None) -> bool:
    """The one-time GET handshake: Meta calls `?hub.mode=subscribe&
    hub.verify_token=<X>&hub.challenge=<Y>`; we echo the challenge iff the
    token matches our configured `WHATSAPP_VERIFY_TOKEN`. Empty config → always
    False, so the webhook can't be wired against an unconfigured deploy."""
    settings = get_settings()
    expected = settings.whatsapp_verify_token
    if not expected:
        return False
    return mode == "subscribe" and token is not None and hmac.compare_digest(token, expected)


def _epoch_to_dt(value: str | int | None) -> datetime:
    """Meta sends unix-epoch SECONDS as a string. Fall back to now() on a
    malformed value rather than dropping the message."""
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return datetime.now(UTC)


def _extract_body_and_media(msg: dict, mtype: MessageType) -> tuple[str | None, str | None]:
    """Pull the human body + a media id out of one Meta message object."""
    if mtype is MessageType.text:
        return (msg.get("text") or {}).get("body"), None
    if mtype in (
        MessageType.image,
        MessageType.document,
        MessageType.video,
        MessageType.audio,
        MessageType.sticker,
    ):
        media = msg.get(mtype.value) or {}
        return media.get("caption"), media.get("id")
    if mtype is MessageType.location:
        loc = msg.get("location") or {}
        name = loc.get("name") or loc.get("address")
        coords = f"{loc.get('latitude')},{loc.get('longitude')}"
        return (name or coords), None
    if mtype is MessageType.contacts:
        contacts = msg.get("contacts") or []
        names = [
            (c.get("name") or {}).get("formatted_name")
            for c in contacts
            if (c.get("name") or {}).get("formatted_name")
        ]
        return (", ".join(names) or None), None
    # unsupported — keep the type string as the body so the agent sees *what*
    # arrived even though we don't render it richly.
    return f"[unsupported message type: {msg.get('type')}]", None


def parse_webhook(payload: dict) -> ParsedWebhook:
    """Flatten Meta's nested `entry[].changes[].value` envelope into two flat
    lists: inbound messages and outbound-status callbacks. Each item carries
    its `phone_number_id` so the caller routes it to the right tenant.

    Defensive throughout — a partial/garbage payload yields whatever could be
    parsed instead of raising, because Meta retries hard on a non-200 and a
    crash here would create a redelivery storm.
    """
    result = ParsedWebhook()
    if not isinstance(payload, dict):
        return result
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            phone_number_id = metadata.get("phone_number_id")
            if not phone_number_id:
                continue

            # Build a wa_id → profile-name index from the `contacts` block.
            names: dict[str, str] = {}
            for c in value.get("contacts") or []:
                wa_id = c.get("wa_id")
                name = (c.get("profile") or {}).get("name")
                if wa_id and name:
                    names[wa_id] = name

            for msg in value.get("messages") or []:
                wamid = msg.get("id")
                sender = msg.get("from")
                if not wamid or not sender:
                    continue
                mtype = _TYPE_MAP.get(msg.get("type", ""), MessageType.unsupported)
                body, media_id = _extract_body_and_media(msg, mtype)
                result.messages.append(
                    InboundMessage(
                        phone_number_id=phone_number_id,
                        contact_wa_id=sender,
                        contact_name=names.get(sender),
                        wa_message_id=wamid,
                        type=mtype,
                        body=body,
                        media_id=media_id,
                        timestamp=_epoch_to_dt(msg.get("timestamp")),
                    )
                )

            for st in value.get("statuses") or []:
                wamid = st.get("id")
                status = _STATUS_MAP.get(st.get("status", ""))
                if not wamid or status is None:
                    continue
                err = None
                errors = st.get("errors") or []
                if errors:
                    e0 = errors[0]
                    err = e0.get("title") or e0.get("message") or str(e0)
                result.statuses.append(
                    StatusUpdate(
                        phone_number_id=phone_number_id,
                        wa_message_id=wamid,
                        status=status,
                        timestamp=_epoch_to_dt(st.get("timestamp")),
                        error=err,
                    )
                )
    return result


async def _post_message(phone_number_id: str, access_token: str, payload: dict) -> str:
    """POST one `/messages` body to the Graph API and return Meta's `wamid`.

    Shared by every send shape (text, template, …). Raises `WhatsAppSendError`
    on any non-2xx — carrying the HTTP status so the worker can tell a terminal
    4xx (Meta rejected the message) from a transient 5xx/transport error worth
    retrying."""
    settings = get_settings()
    url = (
        f"{settings.whatsapp_graph_url}/{settings.whatsapp_api_version}"
        f"/{phone_number_id}/messages"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=_SEND_TIMEOUT_S) as client:
            r = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as e:
        raise WhatsAppSendError(f"transport error: {type(e).__name__}: {e}") from e

    if r.status_code >= 300:
        # Meta error body shape: {"error": {"message": "...", "code": 131047}}
        detail = r.text[:500]
        try:
            err = (r.json() or {}).get("error") or {}
            detail = err.get("message") or detail
        except ValueError:
            pass
        raise WhatsAppSendError(f"HTTP {r.status_code}: {detail}", status_code=r.status_code)

    data = r.json()
    messages = data.get("messages") or []
    if not messages or not messages[0].get("id"):
        raise WhatsAppSendError("send succeeded but no message id returned")
    return messages[0]["id"]


async def send_text(*, phone_number_id: str, access_token: str, to: str, body: str) -> str:
    """Send a free-form text message via the Graph API; return Meta's `wamid`.

    Only valid INSIDE the 24h customer-service window — outside it Meta rejects
    free-form text (surfacing as a `WhatsAppSendError` on the row) and only an
    approved template sends (see `send_template`).
    """
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    return await _post_message(phone_number_id, access_token, payload)


async def send_template(
    *,
    phone_number_id: str,
    access_token: str,
    to: str,
    template_name: str,
    language_code: str,
    body_params: list[str] | None = None,
) -> str:
    """Send a pre-approved message template via the Graph API; return `wamid`.

    Templates are the only message type Meta accepts outside the 24h window
    (business-initiated conversations). `body_params` fills the template's
    positional `{{1}}`, `{{2}}` … body variables in order; omit/empty for a
    template with no variables. We don't validate the name or placeholder count
    against Meta's catalog — a mismatch comes back as a `WhatsAppSendError`.
    """
    template: dict = {
        "name": template_name,
        "language": {"code": language_code},
    }
    if body_params:
        template["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in body_params],
            }
        ]
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": template,
    }
    return await _post_message(phone_number_id, access_token, payload)


# Caption is valid on these media kinds only (audio carries none); filename is
# document-only. Meta rejects the field on the wrong kind, so we gate here.
_CAPTIONABLE = {"image", "video", "document"}


async def send_media(
    *,
    phone_number_id: str,
    access_token: str,
    to: str,
    media_type: str,
    link: str | None = None,
    media_id: str | None = None,
    caption: str | None = None,
    filename: str | None = None,
) -> str:
    """Send an image/document/video/audio message via the Graph API; return
    `wamid`. Source by `link` (a public URL Meta fetches) OR `media_id` (an
    already-uploaded handle) — the caller guarantees exactly one. `caption` is
    attached only for image/video/document; `filename` only for document.
    """
    obj: dict = {}
    if link:
        obj["link"] = link
    if media_id:
        obj["id"] = media_id
    if caption and media_type in _CAPTIONABLE:
        obj["caption"] = caption
    if filename and media_type == "document":
        obj["filename"] = filename
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": media_type,
        media_type: obj,
    }
    return await _post_message(phone_number_id, access_token, payload)


async def fetch_media(media_id: str, access_token: str) -> tuple[bytes, str]:
    """Download one inbound media object from Meta. Returns ``(bytes, mime)``.

    Two hops, both bearer-authenticated: resolve the media id to a short-lived
    CDN url (`GET /{media_id}`), then GET that url for the bytes. Raises
    `WhatsAppSendError` carrying the HTTP status on any non-2xx, so the worker
    can tell a terminal 4xx (the media handle expired / was deleted) from a
    transient error worth retrying.
    """
    settings = get_settings()
    base = f"{settings.whatsapp_graph_url}/{settings.whatsapp_api_version}"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=_SEND_TIMEOUT_S) as client:
            meta = await client.get(f"{base}/{media_id}", headers=headers)
            if meta.status_code >= 300:
                raise WhatsAppSendError(
                    f"HTTP {meta.status_code}: media lookup failed",
                    status_code=meta.status_code,
                )
            info = meta.json() or {}
            url = info.get("url")
            mime = info.get("mime_type") or "application/octet-stream"
            if not url:
                raise WhatsAppSendError("media lookup returned no url")
            # Meta's CDN url ALSO requires the bearer token (it 401s anonymously).
            blob = await client.get(url, headers=headers)
            if blob.status_code >= 300:
                raise WhatsAppSendError(
                    f"HTTP {blob.status_code}: media download failed",
                    status_code=blob.status_code,
                )
            return blob.content, mime
    except httpx.HTTPError as e:
        raise WhatsAppSendError(f"transport error: {type(e).__name__}: {e}") from e

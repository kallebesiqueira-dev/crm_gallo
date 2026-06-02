"""Email delivery backends behind one `EmailProvider` protocol.

Three providers, selected by `settings.email_provider`:

  * `console`  — logs the rendered email; zero secrets, works offline.
                 The dev default and the test default.
  * `resend`   — Resend HTTP API (SaaS deploy).
  * `smtp`     — any SMTP relay (self-host / EU-sovereignty deploy).
                 Uses stdlib `smtplib` in a thread (mirrors the
                 sync-boto3-in-thread pattern in `app/storage.py`);
                 no extra async-SMTP dependency for ~handful of
                 transactional sends.

A provider's `send()` raises on hard failure so the arq `send_email`
job retries with backoff. `console` never raises.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr
from typing import Protocol

import httpx

from app.config import get_settings
from app.email.render import RenderedEmail
from app.logging_setup import get_logger

log = get_logger(__name__)

_RESEND_ENDPOINT = "https://api.resend.com/emails"
_RESEND_TIMEOUT_S = 15.0
_SMTP_TIMEOUT_S = 15.0


class EmailProvider(Protocol):
    name: str

    async def send(self, *, to: str, message: RenderedEmail) -> None: ...


def _from_header() -> str:
    s = get_settings()
    return formataddr((s.email_from_name, s.email_from))


class ConsoleProvider:
    """Logs the rendered email instead of delivering it. The dev
    default: a fresh clone "sends" email with no provider config."""

    name = "console"

    async def send(self, *, to: str, message: RenderedEmail) -> None:
        log.info(
            "email.console_delivery",
            to=to,
            subject=message.subject,
            # Text body only — HTML in a log line is noise. The operator
            # gets the link from the text part.
            text=message.text,
        )


class ResendProvider:
    """Resend HTTP API. Requires `RESEND_API_KEY`."""

    name = "resend"

    async def send(self, *, to: str, message: RenderedEmail) -> None:
        s = get_settings()
        if not s.resend_api_key:
            raise RuntimeError("RESEND_API_KEY is not set but email_provider=resend")
        async with httpx.AsyncClient(timeout=_RESEND_TIMEOUT_S) as client:
            r = await client.post(
                _RESEND_ENDPOINT,
                headers={"Authorization": f"Bearer {s.resend_api_key}"},
                json={
                    "from": _from_header(),
                    "to": [to],
                    "subject": message.subject,
                    "html": message.html,
                    "text": message.text,
                },
            )
        if r.status_code >= 300:
            # Raise so arq retries; truncate the body so a giant error
            # page doesn't bloat the worker log.
            raise RuntimeError(f"Resend send failed: HTTP {r.status_code} {r.text[:500]}")


class SmtpProvider:
    """Generic SMTP relay via stdlib smtplib in a worker thread.

    STARTTLS on submission port 587 is the default. For a local
    catch-all like MailHog set `SMTP_USE_TLS=false` and point at
    port 1025.
    """

    name = "smtp"

    async def send(self, *, to: str, message: RenderedEmail) -> None:
        s = get_settings()
        if not s.smtp_host:
            raise RuntimeError("SMTP_HOST is not set but email_provider=smtp")

        mime = MimeMessage()
        mime["From"] = _from_header()
        mime["To"] = to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        mime.add_alternative(message.html, subtype="html")

        # smtplib is blocking — run it off the event loop so a slow
        # relay doesn't stall the worker's other coroutines.
        await asyncio.to_thread(self._send_sync, s, to, mime)

    @staticmethod
    def _send_sync(s, to: str, mime: MimeMessage) -> None:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=_SMTP_TIMEOUT_S) as server:
            if s.smtp_use_tls:
                server.starttls()
            if s.smtp_username:
                server.login(s.smtp_username, s.smtp_password)
            server.send_message(mime)


_PROVIDERS: dict[str, type[EmailProvider]] = {
    "console": ConsoleProvider,
    "resend": ResendProvider,
    "smtp": SmtpProvider,
}


def get_provider() -> EmailProvider:
    """Instantiate the configured provider. Unknown value → console
    (fail-safe: a typo in EMAIL_PROVIDER degrades to logging, not a
    crash that silently drops every email)."""
    name = get_settings().email_provider.lower()
    provider_cls = _PROVIDERS.get(name)
    if provider_cls is None:
        log.warning("email.unknown_provider", configured=name, fallback="console")
        provider_cls = ConsoleProvider
    return provider_cls()

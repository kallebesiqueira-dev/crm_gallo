"""Transactional email unit tests (ADR-017).

Pure render + provider tests — no DB, no worker, no network. The
autouse `clean_db` fixture still runs (harmless) since it's session
infra; these tests don't seed anything.
"""

from __future__ import annotations

import pytest

from app.email import (
    TEMPLATE_INVITE,
    TEMPLATE_PASSWORD_RESET,
    TEMPLATE_VERIFY_EMAIL,
    get_provider,
    render,
)
from app.email.providers import ConsoleProvider, ResendProvider, SmtpProvider
from app.email.render import SUPPORTED_LOCALES

_INVITE_CTX = {
    "org_name": "Acme Inc",
    "role": "admin",
    "url": "https://app.example/invite/tok123",
    "expires_at": "2026-06-08",
}
_RESET_CTX = {"url": "https://app.example/reset-password/tok456", "expires_hours": 1}
_VERIFY_CTX = {"url": "https://app.example/verify-email/tok789", "expires_hours": 24}


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_invite_renders_all_locales(locale: str):
    msg = render(TEMPLATE_INVITE, locale, _INVITE_CTX)
    assert msg.subject  # non-empty
    assert "Acme Inc" in msg.subject or "Acme Inc" in msg.html
    # URL must appear in BOTH parts so it's clickable in HTML and
    # copy-pasteable from plaintext.
    assert _INVITE_CTX["url"] in msg.html
    assert _INVITE_CTX["url"] in msg.text
    assert msg.html.startswith("<!DOCTYPE html>")


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_password_reset_renders_all_locales(locale: str):
    msg = render(TEMPLATE_PASSWORD_RESET, locale, _RESET_CTX)
    assert msg.subject
    assert _RESET_CTX["url"] in msg.html
    assert _RESET_CTX["url"] in msg.text


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_verify_email_renders_all_locales(locale: str):
    msg = render(TEMPLATE_VERIFY_EMAIL, locale, _VERIFY_CTX)
    assert msg.subject
    assert _VERIFY_CTX["url"] in msg.html
    assert _VERIFY_CTX["url"] in msg.text
    assert msg.html.startswith("<!DOCTYPE html>")


def test_html_escapes_user_controlled_org_name():
    """An org named with markup must NOT inject raw HTML into the
    email body — autoescape is the XSS-in-the-inbox defense."""
    ctx = {**_INVITE_CTX, "org_name": "<script>alert(1)</script>"}
    msg = render(TEMPLATE_INVITE, "en", ctx)
    assert "<script>alert(1)</script>" not in msg.html
    assert "&lt;script&gt;" in msg.html


def test_unknown_locale_falls_back_to_en():
    msg = render(TEMPLATE_INVITE, "zz", _INVITE_CTX)
    en = render(TEMPLATE_INVITE, "en", _INVITE_CTX)
    assert msg.subject == en.subject


def test_locale_with_region_is_normalized():
    msg = render(TEMPLATE_INVITE, "pt-BR", _INVITE_CTX)
    pt = render(TEMPLATE_INVITE, "pt", _INVITE_CTX)
    assert msg.subject == pt.subject


def test_unknown_template_raises():
    with pytest.raises(ValueError, match="Unknown email template"):
        render("does_not_exist", "en", {})


def test_default_provider_is_console():
    assert isinstance(get_provider(), ConsoleProvider)
    assert get_provider().name == "console"


async def test_console_provider_never_raises():
    msg = render(TEMPLATE_INVITE, "en", _INVITE_CTX)
    # Should complete without error and without network.
    await ConsoleProvider().send(to="x@example.com", message=msg)


async def test_resend_provider_raises_without_key():
    """Selected but unconfigured → raises so the arq job retries
    instead of silently dropping the email."""
    msg = render(TEMPLATE_PASSWORD_RESET, "en", _RESET_CTX)
    with pytest.raises(RuntimeError, match="RESEND_API_KEY"):
        await ResendProvider().send(to="x@example.com", message=msg)


async def test_smtp_provider_raises_without_host():
    msg = render(TEMPLATE_PASSWORD_RESET, "en", _RESET_CTX)
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        await SmtpProvider().send(to="x@example.com", message=msg)

"""Transactional email — see ADR-017.

Public surface:
  * `send(...)`            — enqueue a localized email (call from handlers)
  * `render(...)`          — render to (subject, html, text) (used by the worker)
  * `get_provider()`       — the configured delivery backend
  * `TEMPLATE_*`           — template identifiers
"""

from app.email.providers import get_provider
from app.email.render import (
    TEMPLATE_INVITE,
    TEMPLATE_PASSWORD_RESET,
    TEMPLATE_VERIFY_EMAIL,
    RenderedEmail,
    render,
)
from app.email.sender import send

__all__ = [
    "TEMPLATE_INVITE",
    "TEMPLATE_PASSWORD_RESET",
    "TEMPLATE_VERIFY_EMAIL",
    "RenderedEmail",
    "get_provider",
    "render",
    "send",
]

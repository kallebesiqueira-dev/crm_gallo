"""Sentry initialisation — gated by `SENTRY_DSN`.

Empty DSN = no init = zero overhead. With a DSN set, captures
unhandled exceptions, slow-query spans (via the SQLAlchemy
integration sentry-sdk[fastapi] pulls in), and performance traces
at `sentry_traces_sample_rate`.

Scrub-sensitive defaults:
  * `send_default_pii = False` — Sentry will NOT auto-attach
    request headers like Cookie/Authorization. We can't trust
    customers' PII handling.
  * A `before_send` hook strips known sensitive headers / body
    fields as a belt-and-suspenders.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings

_SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "x-csrf-token"}
_SENSITIVE_BODY_KEYS = {
    "password",
    "current_password",
    "new_password",
    "token",
    "access_token",
    "refresh_token",
    "mfa_token",
    "secret",
    "mfa_secret",
    "code",
}


def _scrub(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    """Drop secrets from request headers + body before sending. Run on
    every event, so cheap. Sentry already runs its own PII scrubbing
    when `send_default_pii=False`; this is the project-specific layer
    on top."""
    request = event.get("request") or {}
    headers = request.get("headers")
    if isinstance(headers, dict):
        for k in list(headers.keys()):
            if k.lower() in _SENSITIVE_HEADERS:
                headers[k] = "[scrubbed]"
    data = request.get("data")
    if isinstance(data, dict):
        for k in list(data.keys()):
            if k.lower() in _SENSITIVE_BODY_KEYS:
                data[k] = "[scrubbed]"
    return event


def init_sentry() -> bool:
    """Initialise Sentry if a DSN is configured. Returns True iff
    the SDK was actually initialised (useful for the startup log)."""
    settings = get_settings()
    if not settings.sentry_dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        # `attach_stacktrace=True` adds frames to log-only events too,
        # which catches "log.error(...)" without an active exception.
        attach_stacktrace=True,
        before_send=_scrub,
    )
    return True

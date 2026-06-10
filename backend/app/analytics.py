"""Server-side product analytics (PostHog).

A no-op until `POSTHOG_API_KEY` is set, so the app behaves identically with
analytics off (a fresh clone / dev needs zero setup). Uses the SAME PostHog
project key as the frontend; EU cloud by default for GDPR, matching the rest of
the stack. `capture()` is best-effort and never raises into the request path —
the PostHog SDK batches + flushes on a background thread, so it won't block the
async event loop.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.logging_setup import get_logger

log = get_logger(__name__)

_settings = get_settings()
_client: Any = None
_tried = False


def _get_client() -> Any:
    global _client, _tried
    if _tried:
        return _client
    _tried = True
    key = _settings.posthog_api_key
    if not key:
        return None
    try:
        from posthog import Posthog

        _client = Posthog(project_api_key=key, host=_settings.posthog_host)
    except Exception:  # pragma: no cover - missing dep / bad config must not break the app
        log.warning("posthog.init_failed")
        _client = None
    return _client


def capture(distinct_id: str, event: str, properties: dict[str, Any] | None = None) -> None:
    """Record a server-side product event. Best-effort: any failure is swallowed
    so analytics can never take down a request."""
    client = _get_client()
    if client is None:
        return
    try:
        client.capture(distinct_id=distinct_id, event=event, properties=properties or {})
    except Exception:  # pragma: no cover
        log.warning("posthog.capture_failed", event=event)

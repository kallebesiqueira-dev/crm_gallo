"""Public-API versioning + deprecation policy (ADR-016).

Why a version in the path: the browser SPA and the server-to-server API
have different change cadences. The SPA ships with the backend and can
adapt to a breaking change in the same deploy; an external integrator
cannot. Pinning the external surface under ``/api/v1`` lets us evolve the
internal ``/api/*`` routes freely while promising stability on ``/v1``.

Deprecation policy (the contract we make BEFORE the first integrator, so
we never have to negotiate it under pressure):

  * A new major version (``/api/v2``) ships side-by-side with the old.
    Nothing is removed on the day v2 lands.
  * When a version is slated for removal, every response on it carries
    RFC 8594 headers: ``Deprecation: true`` and ``Sunset: <http-date>``,
    plus a ``Link: <docs>; rel="deprecation"``. ``stamp_version`` is the
    single chokepoint that emits these, so a future deprecation is a
    one-line change, not a per-endpoint sweep.
  * Minimum 6 months between announcing a Sunset and enforcing it.
  * Additive changes (new optional field, new endpoint) are NOT breaking
    and ship into the current version without a bump.

Today ``v1`` is current and not deprecated, so only ``X-API-Version`` is
stamped; the deprecation branch is dormant until a v2 exists.
"""

from __future__ import annotations

from datetime import date

from fastapi import Response

CURRENT_API_VERSION = "v1"

# Set to a `date` on the version that is being retired to switch on the
# RFC 8594 headers. None = not deprecated (the v1 state today).
_SUNSET: date | None = None
_DEPRECATION_DOCS = "https://docs.crmgallo.app/api/deprecation"


def stamp_version(response: Response) -> None:
    """Dependency: stamp every /api/v1 response with its version and,
    once a version is deprecated, the RFC 8594 Deprecation/Sunset
    headers. The single place version metadata is emitted."""
    response.headers["X-API-Version"] = CURRENT_API_VERSION
    if _SUNSET is not None:
        response.headers["Deprecation"] = "true"
        # RFC 7231 IMF-fixdate, e.g. "Wed, 11 Nov 2026 00:00:00 GMT".
        response.headers["Sunset"] = _SUNSET.strftime("%a, %d %b %Y 00:00:00 GMT")
        response.headers["Link"] = f'<{_DEPRECATION_DOCS}>; rel="deprecation"'

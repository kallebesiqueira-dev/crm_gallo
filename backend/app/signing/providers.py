"""E-signature backends behind one `SignatureProvider` protocol (ADR-016).

Mirrors the email-provider seam (`app/email/providers.py`): the call site
never touches a vendor directly, it calls `get_provider().create_envelope(...)`,
and `SIGNING_PROVIDER` config picks the implementation.

  * `manual`   — the dev / low-stakes default. Signing happens in-app via
                 an opaque `sign_token` link; no vendor, no secrets, so a
                 fresh clone has a working signing flow. A homegrown
                 click-to-accept is NOT a qualified signature (ADR-016) —
                 fine for internal demos and low-stakes consent, never for
                 a legally-binding contract.
  * `skribble` — Swiss QES/eIDAS provider (legally binding in CH/EU).
  * `scrive`   — EU e-sign provider (global fallback alongside DocuSign /
                 Dropbox Sign).

The real adapters are deliberately stubs that RAISE when their API key is
unset, rather than silently degrading — a half-configured legal-signature
path must fail loudly, not fall back to a click-to-accept. Wiring them up
needs a vendor account (deferred); the seam keeps that a config change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.config import get_settings
from app.logging_setup import get_logger

if TYPE_CHECKING:
    from app.models import SignatureRequest

log = get_logger(__name__)


@dataclass(frozen=True)
class EnvelopeHandle:
    """What a provider returns after accepting an envelope for signing.

    `external_id` is the vendor's envelope id (None for the manual provider,
    which is driven entirely by our local `sign_token`). `signing_url` is
    where the signer goes to sign — our own page for manual, the vendor's
    hosted page for real providers.
    """

    external_id: str | None
    signing_url: str | None


class SignatureProvider(Protocol):
    name: str

    async def create_envelope(self, request: SignatureRequest) -> EnvelopeHandle: ...


class ManualProvider:
    """In-app signing via the request's `sign_token`. No network call —
    `create_envelope` just hands back the local signing URL."""

    name = "manual"

    async def create_envelope(self, request: SignatureRequest) -> EnvelopeHandle:
        base = get_settings().frontend_base_url.rstrip("/")
        # The frontend signing page (deferred) reads the token from the
        # path and drives GET/POST /api/signatures/sign/{token}.
        url = f"{base}/sign/{request.sign_token}" if request.sign_token else None
        return EnvelopeHandle(external_id=None, signing_url=url)


class _UnconfiguredVendorProvider:
    """Shared base for the real QES/eIDAS adapters. Until a vendor account
    is wired, `create_envelope` raises — a legal-signature path must fail
    loudly, never silently degrade to a click-to-accept."""

    name = "vendor"
    _api_key_attr = ""

    async def create_envelope(self, request: SignatureRequest) -> EnvelopeHandle:
        key = getattr(get_settings(), self._api_key_attr, "")
        if not key:
            raise RuntimeError(
                f"{self.name} signing is selected but {self._api_key_attr.upper()} "
                "is not set. Configure the vendor account or use SIGNING_PROVIDER=manual."
            )
        # Vendor API integration is deferred (needs an account). When wired,
        # POST the document to the vendor, return their envelope id + hosted
        # signing URL, and translate their completion webhook in
        # app/api/signatures.py.
        raise NotImplementedError(f"{self.name} envelope creation is not yet implemented")


class SkribbleProvider(_UnconfiguredVendorProvider):
    name = "skribble"
    _api_key_attr = "skribble_api_key"


class ScriveProvider(_UnconfiguredVendorProvider):
    name = "scrive"
    _api_key_attr = "scrive_api_key"


_PROVIDERS: dict[str, type[SignatureProvider]] = {
    "manual": ManualProvider,
    "skribble": SkribbleProvider,
    "scrive": ScriveProvider,
}


def get_provider() -> SignatureProvider:
    """Instantiate the configured provider. Unknown value → manual
    (fail-safe to the no-secret in-app flow, same posture as the email
    provider; a typo never crashes the signing path)."""
    name = get_settings().signing_provider.lower()
    provider_cls = _PROVIDERS.get(name)
    if provider_cls is None:
        log.warning("signing.unknown_provider", configured=name, fallback="manual")
        provider_cls = ManualProvider
    return provider_cls()

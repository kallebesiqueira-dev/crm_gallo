"""E-signature — see ADR-016.

Public surface:
  * `get_provider()`              — the configured signing backend
  * `EnvelopeHandle`              — what a provider returns on create
  * `store_signature_artifact()`  — persist the signed artifact / audit trail
  * `ENTITY_SIGNATURE_REQUEST`    — FileAttachment entity_type
"""

from app.signing.providers import EnvelopeHandle, SignatureProvider, get_provider
from app.signing.service import ENTITY_SIGNATURE_REQUEST, store_signature_artifact

__all__ = [
    "ENTITY_SIGNATURE_REQUEST",
    "EnvelopeHandle",
    "SignatureProvider",
    "get_provider",
    "store_signature_artifact",
]

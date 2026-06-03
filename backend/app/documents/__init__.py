"""Merge-field document templates (ADR-016).

Allow-listed token substitution for operator-authored document bodies.
See `merge.py` for the token catalog + render.
"""

from app.documents.merge import (
    FIELD_CATALOG,
    FieldSpec,
    build_contract_context,
    render_merge,
)

__all__ = [
    "FIELD_CATALOG",
    "FieldSpec",
    "build_contract_context",
    "render_merge",
]

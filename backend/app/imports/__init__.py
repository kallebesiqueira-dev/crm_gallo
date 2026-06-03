"""Bulk import of leads / customers from CSV / XLSX (ADR-016 imports slice).

  * `parsers` — file bytes → `(headers, rows)`.
  * `spec`    — column specs, per-row Pydantic validation, header
    resolution, and the shared phone/email dedupe normalisers.

The HTTP surface (`app/api/imports.py`) uploads the file to S3 and
creates an `ImportJob`; the `process_import` worker job does the
parse → validate → dedupe → write pass.
"""

from app.imports.parsers import MAX_ROWS, ImportParseError, parse_table
from app.imports.spec import (
    IMPORT_SPECS,
    ImportSpec,
    get_spec,
    normalize_header,
    normalize_phone,
    resolve_headers,
    validate_row,
)

__all__ = [
    "IMPORT_SPECS",
    "MAX_ROWS",
    "ImportParseError",
    "ImportSpec",
    "get_spec",
    "normalize_header",
    "normalize_phone",
    "parse_table",
    "resolve_headers",
    "validate_row",
]

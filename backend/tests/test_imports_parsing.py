"""Bulk-import parsing / validation / export-escaping unit tests (ADR-016).

Pure functions — no DB, no worker, no network:
  * `parse_table` — CSV (BOM, `;` delimiter, blank-row skip, row cap,
    ragged rows) and XLSX (openpyxl, numeric coercion).
  * `spec` — header→field resolution + aliases, missing-required
    reporting, per-row validation, phone/header normalisers.
  * `csv_safe` — formula-injection neutralisation (TD-22) + type
    rendering.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.exports import csv_safe
from app.imports import (
    MAX_ROWS,
    ImportParseError,
    get_spec,
    normalize_header,
    normalize_phone,
    parse_table,
    resolve_headers,
    validate_row,
)

# ---------- CSV parsing ----------


def test_csv_basic_headers_and_rows():
    content = b"first_name,last_name,email\nMaria,Silva,maria@example.com\n"
    headers, rows = parse_table(content, "text/csv", "x.csv")
    assert headers == ["first_name", "last_name", "email"]
    assert rows == [{"first_name": "Maria", "last_name": "Silva", "email": "maria@example.com"}]


def test_csv_strips_utf8_bom_from_first_header():
    # Excel-exported CSVs carry a UTF-8 BOM; it must not corrupt the
    # first header key (otherwise "first_name" never matches the spec).
    content = "﻿first_name,last_name\nJoao,Souza\n".encode()
    headers, rows = parse_table(content, "text/csv", "x.csv")
    assert headers[0] == "first_name"
    assert rows[0]["first_name"] == "Joao"


def test_csv_sniffs_semicolon_delimiter():
    # German/Swiss Excel defaults to ';' as the CSV separator.
    content = b"first_name;last_name;company\nAnna;Meier;Acme\n"
    headers, rows = parse_table(content, "text/csv", "x.csv")
    assert headers == ["first_name", "last_name", "company"]
    assert rows[0]["company"] == "Acme"


def test_csv_skips_fully_blank_lines():
    content = b"first_name,last_name\nA,B\n\n   \nC,D\n"
    _, rows = parse_table(content, "text/csv", "x.csv")
    assert len(rows) == 2
    assert rows[1] == {"first_name": "C", "last_name": "D"}


def test_csv_ragged_short_row_pads_missing_cells():
    content = b"first_name,last_name,email\nA,B\n"
    _, rows = parse_table(content, "text/csv", "x.csv")
    assert rows[0] == {"first_name": "A", "last_name": "B", "email": ""}


def test_csv_empty_file_raises():
    with pytest.raises(ImportParseError, match="empty"):
        parse_table(b"", "text/csv", "x.csv")


def test_csv_header_only_yields_no_rows():
    headers, rows = parse_table(b"first_name,last_name\n", "text/csv", "x.csv")
    assert headers == ["first_name", "last_name"]
    assert rows == []


def test_csv_blank_header_row_raises():
    with pytest.raises(ImportParseError, match="No column headers"):
        parse_table(b",,\nA,B,C\n", "text/csv", "x.csv")


def test_csv_over_row_cap_raises():
    body = "first_name,last_name\n" + "".join(f"A{i},B{i}\n" for i in range(MAX_ROWS + 5))
    with pytest.raises(ImportParseError, match="limit"):
        parse_table(body.encode("utf-8"), "text/csv", "x.csv")


def test_csv_invalid_utf8_raises():
    with pytest.raises(ImportParseError, match="UTF-8"):
        parse_table(b"first_name,last_name\n\xff\xfe,B\n", "text/csv", "x.csv")


# ---------- XLSX parsing ----------


def _xlsx_bytes(rows: list[list[object]]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_xlsx_parses_by_extension():
    content = _xlsx_bytes([["first_name", "last_name"], ["Maria", "Silva"]])
    headers, rows = parse_table(content, "application/octet-stream", "contacts.xlsx")
    assert headers == ["first_name", "last_name"]
    assert rows[0] == {"first_name": "Maria", "last_name": "Silva"}


def test_xlsx_integer_cell_renders_without_dot_zero():
    # Excel stores every number as a float; a whole number must render
    # "42" not "42.0" so int coercion downstream is clean.
    content = _xlsx_bytes([["first_name", "last_name", "company_size"], ["A", "B", 42]])
    _, rows = parse_table(content, "", "x.xlsx")
    assert rows[0]["company_size"] == "42"


def test_xlsx_blank_rows_skipped():
    content = _xlsx_bytes([["first_name", "last_name"], ["A", "B"], [None, None], ["C", "D"]])
    _, rows = parse_table(content, "", "x.xlsx")
    assert len(rows) == 2


def test_xlsx_unreadable_bytes_raise():
    with pytest.raises(ImportParseError, match="readable .xlsx"):
        parse_table(b"not a real workbook", "", "x.xlsx")


# ---------- Header resolution + aliases ----------


def test_normalize_header_folds_case_space_underscore():
    assert normalize_header("First Name") == normalize_header("first_name")
    assert normalize_header("  FIRST  NAME ") == normalize_header("firstname")


def test_resolve_headers_maps_aliases():
    spec = get_spec("lead")
    headers = ["Given Name", "Surname", "E-Mail", "Phone Number", "Unknown Col"]
    mapping, missing = resolve_headers(spec, headers)
    assert missing == []
    assert mapping["Given Name"] == "first_name"
    assert mapping["Surname"] == "last_name"
    assert mapping["E-Mail"] == "email"
    assert mapping["Phone Number"] == "phone"
    # Unknown headers are simply ignored (absent from the map).
    assert "Unknown Col" not in mapping


def test_resolve_headers_reports_missing_required():
    spec = get_spec("lead")
    _, missing = resolve_headers(spec, ["email", "company"])
    assert set(missing) == {"first_name", "last_name"}


def test_template_headers_mark_required_with_star():
    spec = get_spec("customer")
    headers = spec.template_headers
    assert "first_name*" in headers
    assert "last_name*" in headers
    assert "email" in headers  # optional → no star


def test_get_spec_unknown_entity_raises():
    with pytest.raises(KeyError):
        get_spec("deal")


# ---------- Row validation ----------


def test_validate_row_success_coerces_types():
    spec = get_spec("lead")
    mapping = {"first_name": "first_name", "last_name": "last_name", "company_size": "company_size"}
    clean, errors = validate_row(
        spec, {"first_name": "Ana", "last_name": "Costa", "company_size": "50"}, mapping
    )
    assert errors == []
    assert clean["first_name"] == "Ana"
    assert clean["company_size"] == 50  # str → int coercion


def test_validate_row_blank_optional_becomes_none():
    spec = get_spec("lead")
    mapping = {"first_name": "first_name", "last_name": "last_name", "email": "email"}
    clean, errors = validate_row(
        spec, {"first_name": "Ana", "last_name": "Costa", "email": "   "}, mapping
    )
    assert errors == []
    # A blank email cell is "absent", not "" — must not trip EmailStr.
    assert clean["email"] is None


def test_validate_row_missing_required_is_error():
    spec = get_spec("lead")
    mapping = {"first_name": "first_name", "last_name": "last_name"}
    clean, errors = validate_row(spec, {"first_name": "Ana", "last_name": ""}, mapping)
    assert clean is None
    assert any(e["field"] == "last_name" for e in errors)


def test_validate_row_bad_email_is_error():
    spec = get_spec("lead")
    mapping = {"first_name": "first_name", "last_name": "last_name", "email": "email"}
    clean, errors = validate_row(
        spec, {"first_name": "Ana", "last_name": "Costa", "email": "not-an-email"}, mapping
    )
    assert clean is None
    assert any(e["field"] == "email" for e in errors)


# ---------- Dedupe normalisers ----------


def test_normalize_phone_collides_formatted_and_compact():
    assert normalize_phone("+41 79 123 45 67") == normalize_phone("+41791234567")


def test_normalize_phone_preserves_leading_plus():
    assert normalize_phone("+41791234567") == "+41791234567"
    assert normalize_phone("0791234567") == "0791234567"


def test_normalize_phone_blank_is_none():
    assert normalize_phone("") is None
    assert normalize_phone(None) is None
    assert normalize_phone("---") is None


# ---------- Formula-injection escaping (TD-22) ----------


@pytest.mark.parametrize("trigger", ["=", "+", "-", "@", "\t", "\r"])
def test_csv_safe_neutralises_formula_triggers(trigger):
    out = csv_safe(f"{trigger}cmd|'/c calc'!A1")
    assert out.startswith("'")
    assert out[1] == trigger


def test_csv_safe_leaves_plain_text_untouched():
    assert csv_safe("Maria Silva") == "Maria Silva"
    assert csv_safe("a=b") == "a=b"  # trigger only matters at position 0


def test_csv_safe_renders_none_as_empty():
    assert csv_safe(None) == ""


def test_csv_safe_renders_decimal_and_uuid_and_datetime():
    assert csv_safe(Decimal("1500.00")) == "1500.00"
    u = uuid.uuid4()
    assert csv_safe(u) == str(u)
    dt = datetime(2026, 6, 3, 10, 0, tzinfo=UTC)
    assert csv_safe(dt) == dt.isoformat()


def test_csv_safe_renders_enum_value():
    from app.models import LeadStage

    assert csv_safe(LeadStage.qualified) == "qualified"

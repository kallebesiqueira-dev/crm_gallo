"""PDF document rendering (ADR-016).

`render_html` is tested without touching WeasyPrint (markup-level
assertions: field presence, the money filter, autoescaping). One test
drives the full `render_pdf` path to prove the native WeasyPrint stack
is wired and produces a valid PDF.
"""

from __future__ import annotations

from app.pdf import TEMPLATE_DEAL_SUMMARY, render_html, render_pdf

_CTX = {
    "org_name": "Acme Vinhos",
    "deal_title": "Q3 bulk order",
    "value": 12500.5,
    "currency": "EUR",
    "stage": "negotiation",
    "customer_name": "Maria Silva (Acme)",
    "owner_name": "Joao Souza",
    "expected_close_date": "2026-09-30",
    "created_at": "2026-06-02",
    "description": "Annual contract renewal.",
    "generated_at": "2026-06-02 10:00 UTC",
}


def test_deal_summary_html_contains_fields():
    html = render_html(TEMPLATE_DEAL_SUMMARY, _CTX)
    assert "Q3 bulk order" in html
    assert "Acme Vinhos" in html
    assert "Maria Silva (Acme)" in html
    assert "negotiation" in html


def test_money_filter_formats_amount():
    html = render_html(TEMPLATE_DEAL_SUMMARY, _CTX)
    assert "12,500.50 EUR" in html


def test_money_filter_handles_missing_value():
    html = render_html(TEMPLATE_DEAL_SUMMARY, {**_CTX, "value": None})
    assert "&#8212; EUR" in html or "— EUR" in html


def test_optional_fields_omitted_when_absent():
    ctx = {**_CTX, "customer_name": None, "owner_name": None, "expected_close_date": None}
    html = render_html(TEMPLATE_DEAL_SUMMARY, ctx)
    assert "Customer" not in html
    assert "Owner" not in html
    assert "Expected close" not in html


def test_html_escapes_hostile_input():
    """A deal title carrying markup must render as text in the PDF,
    never as live HTML/CSS (XSS-in-document defense)."""
    html = render_html(TEMPLATE_DEAL_SUMMARY, {**_CTX, "deal_title": "<script>alert(1)</script>"})
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_pdf_produces_valid_pdf_bytes():
    pdf = render_pdf(TEMPLATE_DEAL_SUMMARY, _CTX)
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000

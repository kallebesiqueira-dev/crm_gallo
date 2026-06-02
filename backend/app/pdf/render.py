"""HTML -> PDF rendering for generated documents (ADR-016).

Documents (deal summaries today; quotes / contracts later) are produced
by rendering a Jinja2 HTML template and converting it to PDF with
WeasyPrint. Rendering runs in the worker (the `generate_deal_pdf` job)
so a slow render never blocks the request path.

Autoescaping is ON. Template context is tenant data — customer names,
deal titles, free-text notes — so a hostile value must render as text in
the PDF, not inject markup/CSS. Same XSS-in-output reasoning as the email
HTML env (ADR-017).

WeasyPrint is imported lazily inside `render_pdf` so merely importing
this module (for the template constants, say) doesn't pull in the native
Pango stack — only the worker that actually renders pays that cost.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Template registry. Add a constant per document type so call sites
# never pass a raw filename string around.
TEMPLATE_DEAL_SUMMARY = "deal_summary.html"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _format_money(value: object, currency: str = "EUR") -> str:
    """Render an amount as `1.234,56 EUR`-ish text. Deliberately simple
    (no locale lib) — the PDF is a document, not a live UI, and the
    currency code is explicit so there's no ambiguity."""
    try:
        amount = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return f"— {currency}"
    return f"{amount:,.2f} {currency}"


_env.filters["money"] = _format_money


def render_html(template_name: str, context: dict[str, Any]) -> str:
    """Render a template to an HTML string (no PDF conversion).

    Split out from `render_pdf` so tests can assert on the markup
    (escaping, field presence) without needing the native WeasyPrint
    stack installed.
    """
    return _env.get_template(template_name).render(**context)


def render_pdf(template_name: str, context: dict[str, Any]) -> bytes:
    """Render a template straight to PDF bytes.

    `base_url` is the templates dir so any future relative asset (a
    logo `<img src="logo.png">`) resolves against the package, not the
    process CWD.
    """
    from weasyprint import HTML  # lazy: native Pango deps only in the worker

    html = render_html(template_name, context)
    return HTML(string=html, base_url=str(_TEMPLATES_DIR)).write_pdf()

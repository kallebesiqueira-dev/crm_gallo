"""PDF document generation (ADR-016).

`render` turns a Jinja2 HTML template into PDF bytes (WeasyPrint);
`store_pdf_attachment` persists those bytes as a `FileAttachment` so
generated documents reuse the existing attachment list/download surface.
Generation runs in the worker (`generate_deal_pdf` job).
"""

from app.pdf.render import (
    TEMPLATE_DEAL_SUMMARY,
    TEMPLATE_QUOTE,
    render_html,
    render_pdf,
)
from app.pdf.store import store_pdf_attachment

__all__ = [
    "TEMPLATE_DEAL_SUMMARY",
    "TEMPLATE_QUOTE",
    "render_html",
    "render_pdf",
    "store_pdf_attachment",
]

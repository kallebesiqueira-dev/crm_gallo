"""Merge-field render engine for document templates (ADR-016).

Templates are operator-authored bodies sprinkled with `{{ token }}`
placeholders. Applying a template resolves each token against a context
map and substitutes it in. The output is materialised once into
`Contract.body` (frozen text), NOT late-bound.

Design — deliberately NOT a template language:
  * The catalog (`FIELD_CATALOG`) is a fixed allow-list of tokens. There
    is no expression evaluation, no attribute walking, no filters — the
    body is legal text an operator typed, so SSTI is out of scope by
    construction (cf. the WeasyPrint Jinja env, which renders *our* HTML,
    not user input).
  * `render_merge` is a plain regex pass over a `{token: str}` map.
    Unknown tokens are left verbatim (`{{ foo }}` stays `{{ foo }}`) so a
    typo surfaces visibly in the draft instead of vanishing.
  * `{{ line_items }}` is the one "computed" token: the context builder
    rolls the source quote's lines into a newline-delimited block (it
    survives both the PDF `white-space: pre-line` and the detail page's
    `pre-wrap`; a space-aligned table would not).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Contract, Customer, Organization, QuoteLineItem, User
from app.money import q2

# `{{ token }}` — whitespace-tolerant, dotted names only. Captures the
# bare token (e.g. `customer.name`). Anything else is left untouched.
_TOKEN_RE = re.compile(r"\{\{\s*([a-z_][a-z0-9_.]*)\s*\}\}")


@dataclass(frozen=True)
class FieldSpec:
    """One entry in the merge-field catalog (surfaced to the UI picker)."""

    token: str
    label: str
    description: str
    example: str


# The allow-list. Order = display order in the field picker. `doc_type`
# is implicitly `contract` today — when a second document type is added
# this becomes a per-type catalog.
FIELD_CATALOG: list[FieldSpec] = [
    FieldSpec("today", "Today's date", "The date the template is applied.", "2026-06-03"),
    FieldSpec(
        "organization.name", "Your organisation", "Your organisation's name.", "Acme GmbH"
    ),
    FieldSpec("contract.number", "Contract number", "The contract's stable number.", "C-000007"),
    FieldSpec("contract.title", "Contract title", "The contract's title.", "Annual Support"),
    FieldSpec(
        "contract.value", "Contract value", "The agreed amount, with currency.", "EUR 1200.00"
    ),
    FieldSpec("contract.currency", "Currency", "The contract's currency code.", "EUR"),
    FieldSpec(
        "contract.effective_date", "Effective date", "Start of the term (or blank).", "2026-07-01"
    ),
    FieldSpec("contract.end_date", "End date", "End of the term (or blank).", "2027-06-30"),
    FieldSpec("customer.name", "Customer name", "The customer's full name.", "Jane Doe"),
    FieldSpec("customer.company", "Customer company", "The customer's company.", "Doe Ltd"),
    FieldSpec("customer.email", "Customer email", "The customer's email.", "jane@doe.example"),
    FieldSpec("customer.address", "Customer address", "The customer's address.", "1 Main St"),
    FieldSpec("owner.name", "Account owner", "The internal owner of the contract.", "Sam Sales"),
    FieldSpec(
        "line_items",
        "Line items",
        "A rolled-up list of the source quote's lines + totals.",
        "- Widget — 2 × EUR 10.00 = EUR 20.00\n…",
    ),
]

# Fast membership set for validation / passthrough decisions.
CATALOG_TOKENS: frozenset[str] = frozenset(f.token for f in FIELD_CATALOG)


def render_merge(body: str, context: dict[str, str]) -> str:
    """Substitute allow-listed `{{ token }}`s in `body` from `context`.

    Tokens present in `context` are replaced with their (string) value;
    any other `{{ … }}` is left verbatim so typos stay visible. Purely
    textual — no evaluation.
    """

    def _sub(m: re.Match[str]) -> str:
        token = m.group(1)
        if token in context:
            return context[token]
        return m.group(0)

    return _TOKEN_RE.sub(_sub, body)


def _money(amount, currency: str) -> str:
    return f"{currency} {q2(amount):.2f}"


def _format_line_items(items: list[QuoteLineItem], currency: str) -> str:
    """Roll quote lines into a newline-delimited block (pre-line safe)."""
    if not items:
        return "—"
    lines = [
        f"- {li.description} — {li.quantity.normalize():f} × {_money(li.unit_price, currency)}"
        f" = {_money(li.line_total, currency)}"
        for li in items
    ]
    return "\n".join(lines)


async def build_contract_context(db: AsyncSession, contract: Contract) -> dict[str, str]:
    """Resolve the catalog tokens for `contract` into a string map.

    Reads the related organisation / customer / owner names and, if the
    contract was generated from a quote, that quote's line items for the
    `{{ line_items }}` roll-up. Missing optional data resolves to an empty
    string (the placeholder simply renders blank).
    """
    org_name = (
        await db.execute(
            select(Organization.name).where(Organization.id == contract.organization_id)
        )
    ).scalar_one_or_none() or ""

    customer_name = customer_company = customer_email = customer_address = ""
    if contract.customer_id is not None:
        cust = (
            await db.execute(
                select(
                    Customer.first_name,
                    Customer.last_name,
                    Customer.company,
                    Customer.email,
                    Customer.address,
                ).where(Customer.id == contract.customer_id)
            )
        ).first()
        if cust is not None:
            customer_name = f"{cust.first_name} {cust.last_name}".strip()
            customer_company = cust.company or ""
            customer_email = cust.email or ""
            customer_address = cust.address or ""

    owner_name = ""
    if contract.owner_id is not None:
        owner_name = (
            await db.execute(select(User.full_name).where(User.id == contract.owner_id))
        ).scalar_one_or_none() or ""

    currency = contract.currency.value
    line_items_block = "—"
    if contract.quote_id is not None:
        items = (
            await db.execute(
                select(QuoteLineItem)
                .where(QuoteLineItem.quote_id == contract.quote_id)
                .order_by(QuoteLineItem.sort_index)
            )
        ).scalars().all()
        line_items_block = _format_line_items(list(items), currency)

    return {
        "today": date.today().isoformat(),
        "organization.name": org_name,
        "contract.number": contract.number,
        "contract.title": contract.title,
        "contract.value": _money(contract.value, currency),
        "contract.currency": currency,
        "contract.effective_date": (
            contract.effective_date.isoformat() if contract.effective_date else ""
        ),
        "contract.end_date": contract.end_date.isoformat() if contract.end_date else "",
        "customer.name": customer_name,
        "customer.company": customer_company,
        "customer.email": customer_email,
        "customer.address": customer_address,
        "owner.name": owner_name,
        "line_items": line_items_block,
    }

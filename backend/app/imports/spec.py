"""Column specs + per-row validation for bulk imports.

One `ImportSpec` per importable entity drives three things from a single
source of truth:
  * **Validation** — `validate_row` maps the raw `{header: value}` record
    onto model fields (via canonical header + aliases, case/space
    insensitive) and runs it through a Pydantic row model.
  * **Template** — `template_headers` lists the canonical headers (with a
    `*` suffix on required ones) for the downloadable CSV stub.
  * **Dedupe** — `normalize_phone` is the shared key-normaliser the
    worker uses for the phone match (email match is plain `lower()`).

Row models intentionally mirror `LeadBase`/`CustomerBase` constraints
but add an empties→None coercion (a blank CSV cell is "absent", not the
string ""), so an empty optional column never trips `EmailStr` etc.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


@dataclass(frozen=True)
class ImportColumn:
    """One importable column: a model field + the headers that map to it."""

    field: str
    header: str  # canonical header shown in the template
    required: bool = False
    aliases: tuple[str, ...] = ()


def normalize_header(raw: str) -> str:
    """Fold a header to a match key: lowercase, collapse spaces/underscores.

    So `"First Name"`, `"first_name"`, `"firstname"` and `"  FIRST  NAME "`
    all map to the same field.
    """
    return re.sub(r"[\s_]+", "", (raw or "").strip().lower())


def normalize_phone(raw: str | None) -> str | None:
    """Reduce a phone to digits (keeping a leading +) for dedupe matching.

    Not a libphonenumber-grade normaliser — just enough that
    `"+41 79 123 45 67"` and `"+41791234567"` collide. Returns None when
    there's nothing dialable left.
    """
    if not raw:
        return None
    raw = raw.strip()
    plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    return ("+" if plus else "") + digits


class _ImportRowBase(BaseModel):
    # Trim every string cell; XLSX/CSV both arrive as strings.
    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def _empties_to_none(cls, data):
        # A blank cell means "no value", not the empty string — otherwise
        # an empty `email` column would fail EmailStr on every row.
        if isinstance(data, dict):
            return {
                k: (None if isinstance(v, str) and v.strip() == "" else v) for k, v in data.items()
            }
        return data


class LeadImportRow(_ImportRowBase):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=2)
    company_size: int | None = Field(default=None, ge=0)
    budget: Decimal | None = Field(default=None, ge=0)
    source: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class CustomerImportRow(_ImportRowBase):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    company: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=2)
    address: str | None = None
    website: str | None = Field(default=None, max_length=255)
    notes: str | None = None


@dataclass(frozen=True)
class ImportSpec:
    entity_type: str
    columns: list[ImportColumn]
    row_model: type[BaseModel]
    # Lookup built once: every accepted header (normalised) → field name.
    _header_index: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        index: dict[str, str] = {}
        for col in self.columns:
            index[normalize_header(col.header)] = col.field
            for alias in col.aliases:
                index[normalize_header(alias)] = col.field
        # frozen dataclass — set via object.__setattr__
        object.__setattr__(self, "_header_index", index)

    def field_for_header(self, header: str) -> str | None:
        return self._header_index.get(normalize_header(header))

    @property
    def template_headers(self) -> list[str]:
        return [(f"{c.header}*" if c.required else c.header) for c in self.columns]


_NAME_COLUMNS = (
    ImportColumn(
        "first_name", "first_name", required=True, aliases=("first", "firstname", "given name")
    ),
    ImportColumn(
        "last_name",
        "last_name",
        required=True,
        aliases=("last", "lastname", "surname", "family name"),
    ),
)

_LEAD_COLUMNS = [
    *_NAME_COLUMNS,
    ImportColumn("email", "email", aliases=("e-mail", "email address")),
    ImportColumn("phone", "phone", aliases=("phone number", "tel", "telephone", "mobile")),
    ImportColumn("company", "company", aliases=("organisation", "organization", "account")),
    ImportColumn("industry", "industry", aliases=("sector",)),
    ImportColumn("country", "country", aliases=("country code",)),
    ImportColumn("company_size", "company_size", aliases=("employees", "headcount", "size")),
    ImportColumn("budget", "budget", aliases=("deal value", "amount")),
    ImportColumn("source", "source", aliases=("lead source", "channel")),
    ImportColumn("notes", "notes", aliases=("note", "comments", "description")),
]

_CUSTOMER_COLUMNS = [
    *_NAME_COLUMNS,
    ImportColumn("email", "email", aliases=("e-mail", "email address")),
    ImportColumn("phone", "phone", aliases=("phone number", "tel", "telephone", "mobile")),
    ImportColumn("company", "company", aliases=("organisation", "organization", "account")),
    ImportColumn("industry", "industry", aliases=("sector",)),
    ImportColumn("country", "country", aliases=("country code",)),
    ImportColumn("address", "address", aliases=("street", "postal address")),
    ImportColumn("website", "website", aliases=("url", "site")),
    ImportColumn("notes", "notes", aliases=("note", "comments", "description")),
]

IMPORT_SPECS: dict[str, ImportSpec] = {
    "lead": ImportSpec("lead", _LEAD_COLUMNS, LeadImportRow),
    "customer": ImportSpec("customer", _CUSTOMER_COLUMNS, CustomerImportRow),
}


def get_spec(entity_type: str) -> ImportSpec:
    spec = IMPORT_SPECS.get(entity_type)
    if spec is None:
        raise KeyError(f"No import spec for entity_type={entity_type!r}")
    return spec


def resolve_headers(spec: ImportSpec, headers: list[str]) -> tuple[dict[str, str], list[str]]:
    """Map raw file headers → model fields and report missing required ones.

    Returns `(header_to_field, missing_required_headers)`. Unknown headers
    are simply absent from the map (ignored on import); the missing list
    carries the *canonical* header names so the error message is helpful.
    """
    header_to_field: dict[str, str] = {}
    for h in headers:
        f = spec.field_for_header(h)
        if f is not None:
            header_to_field[h] = f
    mapped_fields = set(header_to_field.values())
    missing = [c.header for c in spec.columns if c.required and c.field not in mapped_fields]
    return header_to_field, missing


def validate_row(
    spec: ImportSpec, raw_record: dict[str, str], header_to_field: dict[str, str]
) -> tuple[dict | None, list[dict]]:
    """Validate one raw `{header: value}` record against the row model.

    On success returns `(clean_dict, [])` where `clean_dict` is the
    model-field → coerced-value mapping ready to construct the ORM row.
    On failure returns `(None, errors)` with each error shaped
    `{field, message}` for the job's `error_report`.
    """
    field_values = {header_to_field[h]: v for h, v in raw_record.items() if h in header_to_field}
    try:
        model = spec.row_model(**field_values)
    except Exception as exc:  # pydantic ValidationError (+ any coercion error)
        return None, _format_errors(exc)
    return model.model_dump(), []


def _format_errors(exc: Exception) -> list[dict]:
    errors = getattr(exc, "errors", None)
    if callable(errors):
        out = []
        for e in exc.errors():  # type: ignore[attr-defined]
            loc = e.get("loc") or ()
            field_name = str(loc[0]) if loc else None
            out.append({"field": field_name, "message": e.get("msg", "invalid value")})
        return out
    return [{"field": None, "message": str(exc)}]

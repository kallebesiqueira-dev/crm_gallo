import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import (
    BillingCycle,
    ContractStatus,
    Currency,
    DealStage,
    DocumentType,
    ImportEntityType,
    ImportMode,
    ImportStatus,
    LeadStage,
    Plan,
    QuoteStatus,
    SignatureStatus,
    TaskPriority,
    TaskStatus,
    UserRole,
)


# ---------- Auth ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str
    exp: int
    role: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]
    full_name: Annotated[str, Field(min_length=1, max_length=255)]
    locale: str = "en"


# ---------- Users ----------
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    locale: str
    is_active: bool
    # The org the user is currently working in. Frontend reads this to
    # highlight the active workspace in the org switcher and to know
    # which workspace it's pulling data from.
    last_active_org_id: uuid.UUID | None = None
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserOut
    token: Token


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    locale: str | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: Annotated[str, Field(min_length=8, max_length=128)]


class PasswordResetRequest(BaseModel):
    """Body of POST /api/auth/password-reset/request."""

    email: EmailStr


class NotificationOut(BaseModel):
    """One in-app notification rendered in the header bell.
    `actor_name` is denormalized from the User JOIN."""

    id: uuid.UUID
    type: str
    title: str
    body: str | None = None
    link_url: str | None = None
    metadata_json: str | None = None
    actor_user_id: uuid.UUID | None = None
    actor_name: str | None = None
    read_at: datetime | None = None
    created_at: datetime


class NotificationCounts(BaseModel):
    """Lightweight payload for the header poll. Cheaper than
    fetching the full list when all the bell needs is the badge
    count."""

    unread: int


class PipelineStageOut(BaseModel):
    """One column of a pipeline kanban."""

    id: uuid.UUID
    name: str
    slug: str
    position: int
    probability: int
    is_won: bool
    is_lost: bool


class PipelineStageWrite(BaseModel):
    """Replace-the-whole-stage-list body. The PATCH /pipelines/{id}
    endpoint accepts a list of these and the backend reconciles
    creates/updates/deletes against the existing rows by `id` —
    missing ids are deletes, present ids are updates, null ids are
    creates. Simpler from the UI's perspective than three separate
    endpoints."""

    id: uuid.UUID | None = None
    name: Annotated[str, Field(min_length=1, max_length=120)]
    slug: Annotated[str | None, Field(default=None, max_length=120)] = None
    position: Annotated[int, Field(ge=0)]
    probability: Annotated[int, Field(ge=0, le=100)] = 10
    is_won: bool = False
    is_lost: bool = False


class PipelineOut(BaseModel):
    id: uuid.UUID
    kind: str
    name: str
    slug: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
    stages: list[PipelineStageOut] = []


class PipelineCreate(BaseModel):
    """POST /api/pipelines body. The new pipeline starts empty —
    stages are added via the PATCH endpoint or by cloning the
    default pipeline (clone helper is a follow-up)."""

    kind: Annotated[str, Field(pattern=r"^(lead|deal)$")]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    slug: Annotated[str | None, Field(default=None, max_length=120)] = None


class PipelineUpdate(BaseModel):
    """PATCH /api/pipelines/{id} body. Stages are an optional full
    replacement — if `stages` is None, only the metadata fields
    are updated."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=120)
    is_default: bool | None = None
    stages: list[PipelineStageWrite] | None = None


class TeamCreate(BaseModel):
    """POST /api/teams body. Slug is auto-derived from name if
    omitted; clients can supply one explicitly to control the URL
    segment (future /teams/{slug} routing)."""

    name: Annotated[str, Field(min_length=1, max_length=120)]
    slug: Annotated[str | None, Field(default=None, max_length=120)] = None


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=120)


class TeamMemberOut(BaseModel):
    """One team member surfaced on TeamOut.members."""

    user_id: uuid.UUID
    full_name: str
    email: str
    role: UserRole


class TeamOut(BaseModel):
    """A team plus its current member list. Counts are surfaced so
    the UI can render "Inbound EU · 4 members" without a second
    round-trip; the members array itself is included for the
    expanded settings view."""

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime
    member_count: int
    members: list[TeamMemberOut] = []


class TeamMemberAssign(BaseModel):
    """POST /api/teams/{id}/members body."""

    user_id: uuid.UUID


class FileAttachmentOut(BaseModel):
    """Metadata row for one attachment. Blob lives in S3 — the
    download URL is fetched on demand via `/api/attachments/{id}/download`
    so listing doesn't leak presigned URLs into the SPA's HTML."""

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    uploader_user_id: uuid.UUID | None = None
    uploader_name: str | None = None
    uploader_email: str | None = None
    created_at: datetime


class FileAttachmentDownloadOut(BaseModel):
    """Short-lived presigned download URL the SPA hands to the
    browser (typically via `window.location = url`)."""

    url: str
    expires_in: int


class ImportJobOut(BaseModel):
    """One bulk-import job — created `pending`, polled by the SPA until
    `status` is terminal (`completed` / `failed`). The counters and
    `error_report` are zero/empty until the worker finishes."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: ImportEntityType
    mode: ImportMode
    status: ImportStatus
    filename: str
    total_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    # List[{row:int, field:str|None, message:str}] — capped in the worker.
    error_report: list[dict] | None = None
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class ImportTemplateOut(BaseModel):
    """Canonical column headers for an entity's import template (a `*`
    suffix marks required columns), so the SPA can offer a starter file."""

    entity_type: ImportEntityType
    headers: list[str]


class NoteCreate(BaseModel):
    """POST /api/notes body. `organization_id` is NEVER read from
    the client; resolved server-side from `get_current_org_id`."""

    entity_type: Annotated[str, Field(min_length=1, max_length=40)]
    entity_id: uuid.UUID
    body: Annotated[str, Field(min_length=1, max_length=16000)]


class NoteUpdate(BaseModel):
    body: Annotated[str, Field(min_length=1, max_length=16000)]


class NoteOut(BaseModel):
    """One note row. `author_name` / `author_email` denormalized off
    the User JOIN so the UI doesn't N+1."""

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    body: str
    author_user_id: uuid.UUID | None = None
    author_name: str | None = None
    author_email: str | None = None
    created_at: datetime
    updated_at: datetime


class ActivityOut(BaseModel):
    """One entry on a lead/customer/deal timeline. `actor_name` and
    `actor_email` are denormalized off the User JOIN so the UI
    doesn't N+1; `type` is the short slug — frontend maps to a
    translated label + icon."""

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    type: str
    content: str | None = None
    metadata_json: str | None = None
    actor_user_id: uuid.UUID | None = None
    actor_name: str | None = None
    actor_email: str | None = None
    created_at: datetime


class AuditLogOut(BaseModel):
    """One row of the audit ledger, surfaced via the admin audit UI.
    `actor_email` and `actor_name` are denormalized from the User
    JOIN so the page renders without N+1 lookups."""

    id: uuid.UUID
    organization_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    actor_email: str | None = None
    actor_name: str | None = None
    action: str
    entity_type: str
    entity_id: str | None = None
    metadata_json: str | None = None
    created_at: datetime


class WebhookEndpointCreate(BaseModel):
    """Admin creates an outgoing webhook for the current org.

    `enabled_events` is a list of `EventType` slugs (e.g.
    "lead.created") or `["*"]` for "every event". An empty list
    is rejected (would be a silent no-op subscription).
    """

    url: str
    description: str | None = None
    enabled_events: list[str] = ["*"]


class WebhookEndpointUpdate(BaseModel):
    """PATCH endpoint — only mutable fields. `secret` rotation lives
    on a dedicated POST .../rotate-secret route (not here) so it's
    intentional, not buried in a generic patch."""

    description: str | None = None
    enabled_events: list[str] | None = None
    # `paused` is the user-controlled lever; `paused_at` is the
    # server-side timestamp. Frontend sends true/false; server flips
    # paused_at to now() or null.
    paused: bool | None = None


class WebhookEndpointOut(BaseModel):
    """Public view of a webhook endpoint. Secret is NOT included —
    it's shown ONCE on create via WebhookEndpointCreated and never
    again. Mirrors Stripe / GitHub UX."""

    id: uuid.UUID
    organization_id: uuid.UUID
    url: str
    description: str | None = None
    enabled_events: list[str]
    paused_at: datetime | None = None
    consecutive_failures: int
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    created_at: datetime


class WebhookEndpointCreated(WebhookEndpointOut):
    """One-time response on POST /api/webhooks that includes the
    plaintext `secret` so the admin can copy it into their receiver.
    Future GETs return WebhookEndpointOut only."""

    secret: str


class WebhookDeliveryOut(BaseModel):
    """One delivery attempt — surfaces in the admin "recent deliveries"
    table on the webhook detail page."""

    id: uuid.UUID
    endpoint_id: uuid.UUID
    event_id: uuid.UUID
    event_type: str
    attempt: int
    status: str
    response_code: int | None = None
    response_body_excerpt: str | None = None
    error: str | None = None
    latency_ms: int | None = None
    scheduled_for: datetime
    finished_at: datetime | None = None


class OutboxEventOut(BaseModel):
    """One outbox row, surfaced via the admin /api/outbox endpoint.
    `payload` ships as the raw JSON string (already serialised by
    the producer) — the UI parses + pretty-prints on display."""

    id: uuid.UUID
    organization_id: uuid.UUID | None
    event_type: str
    payload: str | None = None
    occurred_at: datetime
    processed_at: datetime | None = None
    attempt_count: int
    last_error: str | None = None


class SessionOut(BaseModel):
    """One active session for the authenticated user. `id` is the
    opaque session_id (SHA-256-derived); the underlying refresh token
    is never exposed. `current=True` for the session calling
    /sessions — used by the SPA to disable the "revoke" button on
    the user's own row."""

    id: str
    created_at: str | None = None
    last_seen_at: str | None = None
    user_agent: str = ""
    ip_address: str = ""
    current: bool = False


class SessionsRevokeOthersOut(BaseModel):
    revoked: int


class MfaSetupOut(BaseModel):
    """Returned by POST /api/auth/mfa/setup. The `secret` is shown to
    the user (manual-entry fallback if QR scanning fails); the
    `provisioning_uri` is what the QR code encodes."""

    secret: str
    provisioning_uri: str


class MfaEnableRequest(BaseModel):
    """User echoes the first 6-digit code from their authenticator app
    to prove the secret made it across correctly."""

    code: Annotated[str, Field(min_length=6, max_length=8)]


class MfaEnableOut(BaseModel):
    """Returned ONCE after /mfa/enable — backup codes in plaintext.
    They are never returned again from any endpoint."""

    backup_codes: list[str]


class MfaDisableRequest(BaseModel):
    """Disabling MFA requires the current password (prevents
    drive-by-removal if access cookie is stolen) plus a current TOTP
    or backup code (proves the user controls the second factor too)."""

    password: str
    code: Annotated[str, Field(min_length=6, max_length=16)]


class MfaStatusOut(BaseModel):
    enabled: bool
    enrolled_at: datetime | None = None
    backup_codes_remaining: int


class MfaVerifyRequest(BaseModel):
    """Second-step of login. `mfa_token` is the short-lived JWT issued
    by /login when MFA is required; `code` is either a TOTP or a
    backup code (decided by length)."""

    mfa_token: str
    code: Annotated[str, Field(min_length=6, max_length=16)]


class MfaLoginChallenge(BaseModel):
    """Returned from /login when MFA is enabled. The `mfa_token` is
    used to call /mfa/verify; no session cookie is set yet."""

    mfa_required: bool = True
    mfa_token: str


class PasswordResetConfirm(BaseModel):
    """Body of POST /api/auth/password-reset/confirm. The `token` is the
    URL-safe credential delivered out-of-band; `new_password` replaces
    the user's current hash unconditionally on success."""

    token: Annotated[str, Field(min_length=20, max_length=80)]
    new_password: Annotated[str, Field(min_length=8, max_length=128)]


# ---------- Leads ----------
class LeadBase(BaseModel):
    first_name: Annotated[str, Field(min_length=1, max_length=120)]
    last_name: Annotated[str, Field(min_length=1, max_length=120)]
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    industry: str | None = None
    country: str | None = Field(default=None, max_length=2)
    company_size: int | None = Field(default=None, ge=0)
    # Money in → Decimal (Pydantic routes the JSON number through str, so
    # no float tail). LeadOut re-declares it as float for clean JSON out.
    budget: Decimal | None = Field(default=None, ge=0)
    source: str | None = None
    notes: str | None = None
    stage: LeadStage = LeadStage.new


class LeadCreate(LeadBase):
    owner_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None


class LeadUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    industry: str | None = None
    country: str | None = None
    company_size: int | None = None
    budget: Decimal | None = None
    source: str | None = None
    notes: str | None = None
    stage: LeadStage | None = None
    owner_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None


class LeadOut(LeadBase):
    model_config = ConfigDict(from_attributes=True)
    # Float purely as JSON transport of the already-exact Numeric value.
    budget: float | None = None
    id: uuid.UUID
    owner_id: uuid.UUID | None
    team_id: uuid.UUID | None = None
    ai_score: int | None
    ai_priority: str | None
    ai_next_action: str | None
    ai_conversion_probability: float | None
    ai_risk_analysis: str | None
    ai_scored_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LeadScoreOut(BaseModel):
    score: int
    priority: str
    next_action: str
    conversion_probability: float
    risk_analysis: str


# ---------- Customers ----------
class CustomerBase(BaseModel):
    first_name: Annotated[str, Field(min_length=1, max_length=120)]
    last_name: Annotated[str, Field(min_length=1, max_length=120)]
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    industry: str | None = None
    country: str | None = Field(default=None, max_length=2)
    address: str | None = None
    website: str | None = None
    notes: str | None = None


class CustomerCreate(CustomerBase):
    owner_id: uuid.UUID | None = None


class CustomerUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    company: str | None = None
    industry: str | None = None
    country: str | None = None
    address: str | None = None
    website: str | None = None
    notes: str | None = None
    owner_id: uuid.UUID | None = None


class CustomerOut(CustomerBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    owner_id: uuid.UUID | None
    ai_summary: str | None
    ai_summary_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------- Deals ----------
class DealBase(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=255)]
    # Money in → Decimal; DealOut re-declares as float for JSON out.
    value: Decimal = Field(default=Decimal("0"), ge=0)
    currency: Currency = Currency.EUR
    stage: DealStage = DealStage.new
    probability: Annotated[int, Field(ge=0, le=100)] = 10
    expected_close_date: date | None = None
    notes: str | None = None
    customer_id: uuid.UUID | None = None


class DealCreate(DealBase):
    owner_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None


class DealUpdate(BaseModel):
    title: str | None = None
    value: Decimal | None = Field(default=None, ge=0)
    currency: Currency | None = None
    stage: DealStage | None = None
    probability: int | None = Field(default=None, ge=0, le=100)
    expected_close_date: date | None = None
    notes: str | None = None
    customer_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    sort_index: int | None = None


class DealOut(DealBase):
    model_config = ConfigDict(from_attributes=True)
    # Float purely as JSON transport of the already-exact Numeric value.
    value: float = 0.0
    id: uuid.UUID
    owner_id: uuid.UUID | None
    team_id: uuid.UUID | None = None
    sort_index: int
    # Optimistic locking marker (TD-12). Frontend echoes this back as
    # `If-Match: <version>` on the next PATCH / move. Server bumps
    # on every successful mutation.
    version: int = 0
    created_at: datetime
    updated_at: datetime


class DealStageMove(BaseModel):
    stage: DealStage
    sort_index: int = 0


# ---------- Quotes ----------
# Totals (line_total / subtotal / tax_amount / total) are NEVER accepted
# from the client — the server recomputes them from the line items on
# every create/update (see app/services/quotes.recompute_totals). The
# `*Out` schemas expose them; the `*In`/`Create`/`Update` schemas do not.
class QuoteLineItemIn(BaseModel):
    description: Annotated[str, Field(min_length=1, max_length=500)]
    # Money/quantity in → Decimal so server-side line math is exact.
    quantity: Decimal = Field(default=Decimal("1"), ge=0)
    unit_price: Decimal = Field(default=Decimal("0"), ge=0)
    sort_index: int = 0


class QuoteLineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    description: str
    quantity: float
    unit_price: float
    line_total: float
    sort_index: int


class QuoteCreate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=255)]
    currency: Currency = Currency.EUR
    tax_rate: Annotated[Decimal, Field(ge=0, le=100)] = Decimal("0")
    valid_until: date | None = None
    notes: str | None = None
    deal_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    line_items: list[QuoteLineItemIn] = Field(default_factory=list)


class QuoteUpdate(BaseModel):
    """Draft-only edits. The route rejects edits to a non-draft quote
    (a sent/accepted revision is immutable — resend creates a new
    version instead). All fields optional; `line_items`, when provided,
    fully replaces the existing set."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    currency: Currency | None = None
    tax_rate: Decimal | None = Field(default=None, ge=0, le=100)
    valid_until: date | None = None
    notes: str | None = None
    deal_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    line_items: list[QuoteLineItemIn] | None = None


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    number: str
    version: int
    status: QuoteStatus
    title: str
    currency: Currency
    valid_until: date | None
    notes: str | None
    deal_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    subtotal: float
    tax_rate: float
    tax_amount: float
    total: float
    superseded_by: uuid.UUID | None
    sent_at: datetime | None
    accepted_at: datetime | None
    declined_at: datetime | None
    line_items: list[QuoteLineItemOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ---------- E-signature (ADR-016) ----------
class SignatureRequestCreate(BaseModel):
    """Raise a signing envelope against a quote OR a contract. Provide
    exactly one of `quote_id` / `contract_id`; the document must be `sent`
    (you sign a delivered proposal/agreement, not a draft). The provider is
    taken from server config, never the client."""

    quote_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    signer_name: Annotated[str, Field(min_length=1, max_length=255)]
    signer_email: EmailStr
    message: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _exactly_one_document(self) -> "SignatureRequestCreate":
        if (self.quote_id is None) == (self.contract_id is None):
            raise ValueError("Provide exactly one of quote_id or contract_id.")
        return self


class SignatureSignIn(BaseModel):
    """Payload the manual in-app signer submits. The typed full name is the
    consent record; IP / user-agent are captured server-side from the
    request, never trusted from the body."""

    typed_name: Annotated[str, Field(min_length=1, max_length=255)]


class SignatureDeclineIn(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class SignatureRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    quote_id: uuid.UUID | None
    contract_id: uuid.UUID | None
    provider: str
    status: SignatureStatus
    signer_name: str
    signer_email: str
    message: str | None
    external_id: str | None
    document_attachment_id: uuid.UUID | None
    signed_document_key: str | None
    owner_id: uuid.UUID | None
    sent_at: datetime | None
    viewed_at: datetime | None
    signed_at: datetime | None
    declined_at: datetime | None
    decline_reason: str | None
    created_at: datetime
    updated_at: datetime
    # Where the signer goes to sign. Only meaningful for the manual
    # provider (built from `sign_token`); real providers return their own
    # hosted URL. Not an ORM column — set by the handler, so it defaults to
    # None when absent and never trips `from_attributes`.
    signing_url: str | None = None


class SignatureSignContext(BaseModel):
    """The minimal, unauthenticated view the signer sees on the signing
    page — no internal ids, owners, or org plumbing. Works for both quote
    and contract envelopes via the generic `document_*` fields. Marks the
    request `viewed` as a side effect of being fetched."""

    status: SignatureStatus
    signer_name: str
    document_type: Literal["quote", "contract"]
    document_number: str
    document_title: str
    document_total: float
    document_currency: Currency
    organization_name: str


# ---------- Contracts (ADR-016) ----------
class ContractCreate(BaseModel):
    """A new draft contract. Unlike a quote there are no line items — a
    contract carries a single agreed `value`; itemisation (if any) lives
    on the linked source quote. `quote_id` is optional so a contract can
    be drafted free-standing, but when present the route can later copy
    over title/value defaults."""

    title: Annotated[str, Field(min_length=1, max_length=255)]
    currency: Currency = Currency.EUR
    value: Annotated[Decimal, Field(ge=0)] = Decimal("0")
    effective_date: date | None = None
    end_date: date | None = None
    auto_renew: bool = False
    renewal_term_months: Annotated[int, Field(ge=1, le=120)] | None = None
    body: str | None = None
    notes: str | None = None
    quote_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None


class ContractUpdate(BaseModel):
    """Draft-only edits. The route rejects edits to a non-draft contract
    (a sent/signed revision is immutable — resend creates a new version
    instead). All fields optional."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    currency: Currency | None = None
    value: Decimal | None = Field(default=None, ge=0)
    effective_date: date | None = None
    end_date: date | None = None
    auto_renew: bool | None = None
    renewal_term_months: int | None = Field(default=None, ge=1, le=120)
    body: str | None = None
    notes: str | None = None
    quote_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    number: str
    version: int
    status: ContractStatus
    title: str
    currency: Currency
    value: float
    effective_date: date | None
    end_date: date | None
    auto_renew: bool
    renewal_term_months: int | None
    body: str | None
    notes: str | None
    quote_id: uuid.UUID | None
    deal_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    applied_template_id: uuid.UUID | None
    superseded_by: uuid.UUID | None
    sent_at: datetime | None
    signed_at: datetime | None
    activated_at: datetime | None
    terminated_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------- Document templates (merge fields — ADR-016) ----------
class DocumentTemplateCreate(BaseModel):
    """A new reusable template body with `{{ token }}` merge fields. The
    body is operator-authored text — tokens are substituted (allow-list),
    never evaluated. `doc_type` defaults to `contract` (the only target
    wired today)."""

    name: Annotated[str, Field(min_length=1, max_length=120)]
    body: str = ""
    doc_type: DocumentType = DocumentType.contract
    is_default: bool = False


class DocumentTemplateUpdate(BaseModel):
    """Partial edit of a template. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    body: str | None = None
    is_default: bool | None = None


class DocumentTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    doc_type: DocumentType
    name: str
    body: str
    is_default: bool
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class MergeFieldOut(BaseModel):
    """One entry in the merge-field catalog, for the UI field picker."""

    token: str
    label: str
    description: str
    example: str


# ---------- Tasks ----------
class TaskBase(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=255)]
    description: str | None = None
    status: TaskStatus = TaskStatus.todo
    priority: TaskPriority = TaskPriority.medium
    due_date: date | None = None
    assignee_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: date | None = None
    assignee_id: uuid.UUID | None = None


class TaskOut(TaskBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------- Billing ----------
class PlanOut(BaseModel):
    id: Plan
    name: str
    tagline: str
    monthly_eur: float
    yearly_eur_per_user: float
    yearly_total_eur: float
    seat_limit: int | None
    features: list[str]
    highlighted: bool
    requires_payment: bool = False
    trial_days: int = 0


class BillingMe(BaseModel):
    plan: Plan
    billing_cycle: BillingCycle
    seat_limit: int | None
    seats_used: int
    seats_remaining: int | None
    plan_started_at: datetime | None
    plan_renewed_at: datetime | None
    plan_canceled_at: datetime | None = None
    trial_ends_at: datetime | None = None
    stripe_configured: bool = False


class UpgradeRequest(BaseModel):
    plan: Plan
    billing_cycle: BillingCycle = BillingCycle.monthly


# ---------- Organizations ----------
class OrgOut(BaseModel):
    """Public-ish view of an Organization (the user must be a member)."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    plan: Plan
    created_at: datetime


class MembershipOut(BaseModel):
    """User's membership in an org — what the switcher renders."""

    organization: OrgOut
    role: UserRole
    created_at: datetime


class SwitchOrgRequest(BaseModel):
    organization_id: uuid.UUID


class OrgCreate(BaseModel):
    name: str
    # Slug is optional; when omitted the backend slugifies `name`. Keeps
    # the form short for the common case ("Acme Corp" → "acme-corp").
    slug: str | None = None


# ---------- Org invites ----------
class InviteCreate(BaseModel):
    """Admin → invite a new member by email + the role they get on join."""

    email: EmailStr
    role: UserRole = UserRole.sales_agent


class InviteOut(BaseModel):
    """What the admin sees back when listing or creating invites.

    `invite_url` is populated only on the CREATE response — listing
    endpoints don't re-expose it because the admin already has the link
    from the create response (and re-sending it would be a job for a
    "resend invite" endpoint, not a list).
    """

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    email: EmailStr
    role: UserRole
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime
    invite_url: str | None = None


class InvitePreview(BaseModel):
    """Public view of an invite — what /api/invites/{token} returns to a
    not-yet-registered visitor. Carries just enough context (org name,
    email it was sent to, role they'll get) so the registration page
    can render a "You're joining Acme Corp as Sales Agent" header."""

    organization_id: uuid.UUID
    organization_name: str
    email: EmailStr
    role: UserRole
    expires_at: datetime


class InviteAcceptRequest(BaseModel):
    """Body for POST /api/auth/register-with-invite — same shape as the
    plain register payload except `email` is fixed by the invite."""

    token: str
    full_name: str
    password: str
    locale: str = "en"


# ---------- Dashboard ----------
class DashboardStats(BaseModel):
    total_leads: int
    leads_by_stage: dict[str, int]
    won_count: int
    lost_count: int
    conversion_rate: float
    avg_ai_score: float | None
    total_customers: int = 0
    total_deals: int = 0
    pipeline_value_eur: float = 0.0
    open_tasks: int = 0

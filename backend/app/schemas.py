import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, model_validator

from app.models import (
    ApiKeyScope,
    AutomationAction,
    AutomationTrigger,
    BillingCycle,
    ContractStatus,
    ConversationChannel,
    ConversationStatus,
    Currency,
    CustomFieldType,
    DealStage,
    DocumentType,
    GoalMetric,
    GoalPeriod,
    ImportEntityType,
    ImportMode,
    ImportStatus,
    LeadStage,
    MessageDirection,
    MessageStatus,
    MessageType,
    NextActionType,
    Plan,
    ProductType,
    QuoteStatus,
    SignatureStatus,
    TaskPriority,
    TaskStatus,
    UserRole,
    WhatsAppAccountStatus,
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
    # Cloudflare Turnstile token — required only when CAPTCHA is enabled server-side.
    turnstile_token: str | None = None


# ---------- Users ----------
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    locale: str
    is_active: bool
    # Whether the user has confirmed their email. False for fresh
    # self-signups until they click the verification link; true for the
    # first user, invited users, and everyone grandfathered by the
    # migration.
    email_verified: bool = True
    # The org the user is currently working in. Frontend reads this to
    # highlight the active workspace in the org switcher and to know
    # which workspace it's pulling data from.
    last_active_org_id: uuid.UUID | None = None
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserOut
    token: Token


class RegisterResponse(BaseModel):
    """Body of POST /api/auth/register.

    Two outcomes share this shape so the frontend can branch on a single
    field:

      - `verification_required=True` (the common self-signup case): the
        user must confirm their email before logging in. No session is
        started, so `token` is null. The frontend shows a "check your
        email" screen.
      - `verification_required=False` (the very first user / install
        founder, auto-verified): a full session was started and `token`
        carries the access token, so the frontend logs them straight in.

    `user` is always present so the frontend can read the resolved locale
    for the post-signup redirect.
    """

    verification_required: bool
    email: EmailStr
    user: UserOut
    token: Token | None = None


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


class ApiKeyCreate(BaseModel):
    """Admin mints a Public-API key for the current org.

    `scopes` is coarse for v1: `read` (GET) and/or `write` (mutations).
    Defaults to read-only — the least-privilege default, so a key that's
    only meant to pull data can't accidentally be granted write. An empty
    list is rejected (a scopeless key could do nothing). `expires_at` is
    optional; omit for a non-expiring key.
    """

    name: str = Field(min_length=1, max_length=120)
    scopes: list[ApiKeyScope] = Field(default_factory=lambda: [ApiKeyScope.read])
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _non_empty_scopes(self) -> "ApiKeyCreate":
        if not self.scopes:
            raise ValueError("scopes must be non-empty")
        return self


class ApiKeyOut(BaseModel):
    """Public view of an API key — the secret token is NEVER here. The
    plaintext is shown ONCE on create (ApiKeyCreated) and is otherwise
    unrecoverable. `display_prefix` is the non-secret label for the list."""

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    display_prefix: str
    scopes: list[ApiKeyScope]
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    """One-time response on POST /api/api-keys carrying the plaintext
    `token`. Copy it now — it is hashed at rest and can't be shown again."""

    token: str


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


class MfaSetupRequired(BaseModel):
    """Returned from /login when the user holds a privileged role but
    hasn't enrolled in MFA and the `mfa_required_for_privileged` policy
    is on. Unlike the challenge, a FULL session is started (cookies set)
    so the client can reach /mfa/setup + /mfa/enable — every tenant-data
    endpoint stays blocked (403 `mfa_enrollment_required`) until they
    finish. The `token` mirrors AuthResponse for the cookie-less callers.
    """

    mfa_setup_required: bool = True
    user: UserOut
    token: Token


class PasswordResetConfirm(BaseModel):
    """Body of POST /api/auth/password-reset/confirm. The `token` is the
    URL-safe credential delivered out-of-band; `new_password` replaces
    the user's current hash unconditionally on success."""

    token: Annotated[str, Field(min_length=20, max_length=80)]
    new_password: Annotated[str, Field(min_length=8, max_length=128)]


class EmailVerifyConfirm(BaseModel):
    """Body of POST /api/auth/verify-email/confirm. The `token` is the
    URL-safe credential from the verification email; confirming it marks
    the bound user's email verified and starts a session."""

    token: Annotated[str, Field(min_length=20, max_length=80)]


class EmailVerifyResend(BaseModel):
    """Body of POST /api/auth/verify-email/resend. Always responds 204 (no
    enumeration); a fresh link is only minted when the email maps to an
    active, not-yet-verified user."""

    email: EmailStr


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
    company_id: uuid.UUID | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class LeadCreate(LeadBase):
    owner_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    contact_consent_at: datetime | None = None
    consent_source: str | None = None


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
    company_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    custom_fields: dict[str, Any] | None = None
    contact_consent_at: datetime | None = None
    consent_source: str | None = None


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
    version: int = 0
    created_at: datetime
    updated_at: datetime
    contact_consent_at: datetime | None = None
    consent_source: str | None = None


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
    company_id: uuid.UUID | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CustomerCreate(CustomerBase):
    owner_id: uuid.UUID | None = None
    contact_consent_at: datetime | None = None
    consent_source: str | None = None


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
    company_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    custom_fields: dict[str, Any] | None = None
    contact_consent_at: datetime | None = None
    consent_source: str | None = None


class CustomerOut(CustomerBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    owner_id: uuid.UUID | None
    ai_summary: str | None
    ai_summary_updated_at: datetime | None
    # Optimistic locking marker (TD-12) — echo back as `If-Match` on PATCH.
    version: int = 0
    created_at: datetime
    updated_at: datetime
    contact_consent_at: datetime | None = None
    consent_source: str | None = None


class CompanyBase(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    industry: str | None = None
    website: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    country: str | None = Field(default=None, max_length=2)
    address: str | None = None
    size: int | None = Field(default=None, ge=0)
    notes: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CompanyCreate(CompanyBase):
    owner_id: uuid.UUID | None = None


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    industry: str | None = None
    website: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    country: str | None = None
    address: str | None = None
    size: int | None = Field(default=None, ge=0)
    notes: str | None = None
    owner_id: uuid.UUID | None = None
    custom_fields: dict[str, Any] | None = None


class CompanyOut(CompanyBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    owner_id: uuid.UUID | None
    # Optimistic locking marker — echo back as `If-Match` on PATCH.
    version: int = 0
    created_at: datetime
    updated_at: datetime


# ---------- Products / Services (catalog) ----------
class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sku: str | None = Field(default=None, max_length=64)
    type: ProductType = ProductType.product
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    unit: str | None = Field(default=None, max_length=32)
    active: bool = True


class ProductCreate(ProductBase):
    owner_id: uuid.UUID | None = None


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    sku: str | None = Field(default=None, max_length=64)
    type: ProductType | None = None
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    unit: str | None = Field(default=None, max_length=32)
    active: bool | None = None
    owner_id: uuid.UUID | None = None


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    owner_id: uuid.UUID | None
    version: int = 0
    created_at: datetime
    updated_at: datetime


# ---------- Custom field definitions (per-org schema extension) ----------
CustomFieldEntity = Literal["lead", "customer", "deal", "company"]

# Slug: lowercase letters, digits, underscore; must start with a letter.
_KEY_PATTERN = r"^[a-z][a-z0-9_]*$"


class CustomFieldDefinitionBase(BaseModel):
    entity_type: CustomFieldEntity
    key: Annotated[str, Field(min_length=1, max_length=60, pattern=_KEY_PATTERN)]
    label: Annotated[str, Field(min_length=1, max_length=120)]
    field_type: CustomFieldType
    options: list[str] | None = None
    required: bool = False
    position: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _options_required_for_select(self) -> "CustomFieldDefinitionBase":
        if self.field_type in (CustomFieldType.select, CustomFieldType.multiselect):
            if not self.options:
                raise ValueError("select / multiselect fields require a non-empty options list")
        else:
            # Options are meaningless for other types — drop to keep rows clean.
            self.options = None
        return self


class CustomFieldDefinitionCreate(CustomFieldDefinitionBase):
    pass


class CustomFieldDefinitionUpdate(BaseModel):
    # `entity_type` and `key` are immutable (stored values key off them);
    # only presentation/validation attributes can change.
    label: str | None = Field(default=None, min_length=1, max_length=120)
    field_type: CustomFieldType | None = None
    options: list[str] | None = None
    required: bool | None = None
    position: int | None = Field(default=None, ge=0)


class CustomFieldDefinitionOut(CustomFieldDefinitionBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ---------- Tags & saved segments ----------
# The set of entities that can be tagged / segmented mirrors the custom-
# field entity set exactly.
TaggableEntity = CustomFieldEntity

# 6-digit hex colour, e.g. "#64748b".
_HEX_COLOR = r"^#[0-9a-fA-F]{6}$"


class TagBase(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=60)]
    color: Annotated[str, Field(pattern=_HEX_COLOR)] = "#64748b"


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    color: str | None = Field(default=None, pattern=_HEX_COLOR)


class TagOut(TagBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class TagAssign(BaseModel):
    tag_id: uuid.UUID
    entity_type: TaggableEntity
    entity_id: uuid.UUID


class TagBulk(BaseModel):
    """Add/remove a set of tags across a set of entities of one type."""

    tag_ids: Annotated[list[uuid.UUID], Field(min_length=1)]
    entity_type: TaggableEntity
    entity_ids: Annotated[list[uuid.UUID], Field(min_length=1)]
    action: Literal["add", "remove"]


class EntityTagsOut(BaseModel):
    """The tags attached to one entity — used to render chips on list rows."""

    entity_id: uuid.UUID
    tags: list[TagOut]


class SegmentBase(BaseModel):
    entity_type: TaggableEntity
    name: Annotated[str, Field(min_length=1, max_length=120)]
    # Opaque filter blob written + interpreted by the frontend.
    filters: dict[str, Any] = Field(default_factory=dict)


class SegmentCreate(SegmentBase):
    pass


class SegmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    filters: dict[str, Any] | None = None


class SegmentOut(SegmentBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# ---------- Duplicate detection & merge ----------
# Only the contact-shaped + account entities carry a natural identity
# (email / phone / name) worth deduping. Deals/tasks have no such key.
DuplicateEntity = Literal["lead", "customer", "company"]


class DuplicateRecord(BaseModel):
    """One candidate row in a duplicate group — a compact summary for the
    merge picker (never the full entity)."""

    id: uuid.UUID
    label: str
    email: str | None = None
    phone: str | None = None
    created_at: datetime


class DuplicateGroup(BaseModel):
    """A set of 2+ records that collide on one signal."""

    match_type: Literal["email", "phone", "name"]
    # The normalised value the members share (e.g. "john@x.com").
    key: str
    records: list[DuplicateRecord]


class DuplicateGroupsOut(BaseModel):
    entity_type: DuplicateEntity
    groups: list[DuplicateGroup]


class MergeRequest(BaseModel):
    """Fold `loser_ids` into `survivor_id`: children re-parent to the
    survivor, the losers are soft-deleted. Survivor's own fields are
    left untouched (field-level merge is a UI concern, out of scope)."""

    entity_type: DuplicateEntity
    survivor_id: uuid.UUID
    loser_ids: Annotated[list[uuid.UUID], Field(min_length=1)]


class MergeResult(BaseModel):
    survivor_id: uuid.UUID
    merged_count: int
    # Per-relation count of rows re-parented to the survivor.
    reparented: dict[str, int]


# ---------- Web-to-Lead public capture forms ----------
class WebFormBase(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    # Stamped onto Leads this form creates (defaults to "Web Form" if unset).
    default_source: Annotated[str | None, Field(default=None, max_length=120)]
    # Browser redirect after a successful HTML-form post.
    redirect_url: Annotated[str | None, Field(default=None, max_length=500)]
    active: bool = True


class WebFormCreate(WebFormBase):
    pass


class WebFormUpdate(BaseModel):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=120)]
    default_source: Annotated[str | None, Field(default=None, max_length=120)]
    redirect_url: Annotated[str | None, Field(default=None, max_length=500)]
    active: bool | None = None


class WebFormOut(WebFormBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    # The public `crmf_…` identifier for the embed snippet. Not a secret.
    token: str
    submission_count: int
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
    company_id: uuid.UUID | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    next_action_type: NextActionType | None = None
    next_action_at: datetime | None = None


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
    company_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    sort_index: int | None = None
    custom_fields: dict[str, Any] | None = None
    next_action_type: NextActionType | None = None
    next_action_at: datetime | None = None


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


class NextActionPayload(BaseModel):
    next_action_type: NextActionType | None = None
    next_action_at: datetime | None = None


class DealTodayItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    value: float
    currency: str
    stage: DealStage
    next_action_type: NextActionType | None
    next_action_at: datetime | None
    customer_name: str | None
    owner_id: uuid.UUID | None
    version: int


class TaskTodayItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    due_date: date | None
    priority: TaskPriority
    customer_name: str | None = None
    version: int


class HojeResponse(BaseModel):
    overdue_deals: list[DealTodayItem]
    today_deals: list[DealTodayItem]
    no_action_deals: list[DealTodayItem]
    stale_deals: list[DealTodayItem]
    today_tasks: list[TaskTodayItem]
    overdue_tasks: list[TaskTodayItem]


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
    # Optimistic locking marker (TD-12) — echo back as `If-Match` on PATCH.
    version: int = 0
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


class InviteTokenRequest(BaseModel):
    """Body for POST /api/auth/accept-invite (logged-in user accepts)."""

    token: str


# ---------- Dashboard ----------
class FunnelStageStat(BaseModel):
    stage: str
    count: int
    value_eur: float = 0.0


class MonthValue(BaseModel):
    month: str  # "YYYY-MM"
    value_eur: float = 0.0


class QuotesSummary(BaseModel):
    total_eur: float = 0.0
    outstanding_eur: float = 0.0  # draft + sent
    accepted_eur: float = 0.0
    rejected_eur: float = 0.0  # declined + expired
    open_eur: float = 0.0  # sent, not past valid_until
    overdue_eur: float = 0.0  # sent, past valid_until


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
    # Raw open-pipeline sums per ISO currency (plan.md §6) — display-
    # only, NO conversion; the _eur field above stays the rough
    # FX-approximated headline.
    pipeline_value_by_currency: dict[str, float] = Field(default_factory=dict)
    open_tasks: int = 0
    pipeline_funnel: list[FunnelStageStat] = Field(default_factory=list)
    monthly_revenue: list[MonthValue] = Field(default_factory=list)
    revenue_total_eur: float = 0.0
    quotes: QuotesSummary = Field(default_factory=QuotesSummary)


# ---------- Performance / KPI ----------
class SalesGoalBase(BaseModel):
    # Exactly one scope is implied: owner_id set = per-rep, team_id set =
    # per-team, both null = org-wide. The API does not forbid both being
    # set, but treats owner_id as the more specific scope.
    owner_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    period: GoalPeriod = GoalPeriod.month
    period_start: date
    metric: GoalMetric = GoalMetric.revenue
    # EUR for revenue, whole deals for deal_count. Decimal in.
    target: Decimal = Field(ge=0)


class SalesGoalCreate(SalesGoalBase):
    pass


class SalesGoalUpdate(BaseModel):
    owner_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    period: GoalPeriod | None = None
    period_start: date | None = None
    metric: GoalMetric | None = None
    target: Decimal | None = Field(default=None, ge=0)


class SalesGoalOut(SalesGoalBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    # Float as JSON transport of the exact Numeric target.
    target: float = 0.0
    # Computed at read time against closed-won deals in the goal window.
    attainment: float = 0.0  # EUR or deal count achieved so far
    attainment_pct: float = 0.0  # achieved / target, 0..(>1), 0 if no target
    created_at: datetime
    updated_at: datetime


class LeaderboardRow(BaseModel):
    owner_id: uuid.UUID | None
    owner_name: str
    won_value_eur: float
    won_count: int


class FunnelStage(BaseModel):
    stage: str
    count: int


class PerformanceSummary(BaseModel):
    period: GoalPeriod
    period_start: date
    period_end: date
    # Closed-won revenue (EUR) and count in the window.
    won_value_eur: float
    won_count: int
    lost_count: int
    # won / (won + lost) over deals closed in the window, 0..1.
    win_rate: float
    # Lead funnel: lead counts by stage (all-time, org-wide).
    lead_funnel: list[FunnelStage]
    # Leads won / total leads, 0..1.
    lead_conversion_rate: float
    leads_lost: int
    # Days from deal creation to close (won), over the window.
    avg_days_to_close: float | None
    median_days_to_close: float | None
    leaderboard: list[LeaderboardRow]


# ---------- Automations ----------
class AutomationRuleBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool = True
    trigger: AutomationTrigger
    action: AutomationAction
    # Free-form per-action parameters (see AutomationRule.action_config).
    # Stored as JSON text on the model; exchanged as an object on the wire.
    action_config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_action_config(self) -> "AutomationRuleBase":
        cfg = self.action_config or {}
        if self.action == AutomationAction.change_stage:
            stage = cfg.get("to_stage")
            valid = {s.value for s in DealStage}
            if stage not in valid:
                raise ValueError("change_stage requires action_config.to_stage to be a deal stage")
            # change_stage only makes sense for a deal-bearing trigger.
            deal_triggers = {
                AutomationTrigger.deal_created,
                AutomationTrigger.deal_won,
                AutomationTrigger.deal_lost,
                AutomationTrigger.deal_stage_changed,
            }
            if self.trigger not in deal_triggers:
                raise ValueError("change_stage requires a deal trigger")
        if self.action == AutomationAction.send_notification and not (cfg.get("title")):
            # Fall back to the rule name at execution time, but require *some*
            # title source so the bell is never blank.
            if not self.name:
                raise ValueError("send_notification needs a title")
        return self


class AutomationRuleCreate(AutomationRuleBase):
    pass


class AutomationRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    trigger: AutomationTrigger | None = None
    action: AutomationAction | None = None
    action_config: dict[str, Any] | None = None


class AutomationRuleOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    enabled: bool
    trigger: AutomationTrigger
    action: AutomationAction
    action_config: dict[str, Any]
    run_count: int
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AutomationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_id: uuid.UUID
    status: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    detail: str | None
    created_at: datetime


# ---------- WhatsApp Business Cloud API (omnichannel inbox) ----------
class WhatsAppAccountConnect(BaseModel):
    """Connect a tenant's WhatsApp number. `access_token` is the permanent
    (system-user) token — write-only: accepted here, never echoed back."""

    phone_number_id: Annotated[str, Field(min_length=1, max_length=64)]
    access_token: Annotated[str, Field(min_length=1, max_length=1024)]
    waba_id: Annotated[str | None, Field(default=None, max_length=64)]
    display_phone_number: Annotated[str | None, Field(default=None, max_length=32)]
    verified_name: Annotated[str | None, Field(default=None, max_length=255)]


class WhatsAppAccountUpdate(BaseModel):
    access_token: Annotated[str | None, Field(default=None, min_length=1, max_length=1024)]
    display_phone_number: Annotated[str | None, Field(default=None, max_length=32)]
    verified_name: Annotated[str | None, Field(default=None, max_length=255)]
    status: WhatsAppAccountStatus | None = None


class WhatsAppAccountOut(BaseModel):
    """Account view for the settings UI. NEVER includes `access_token`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone_number_id: str
    waba_id: str | None
    display_phone_number: str | None
    verified_name: str | None
    status: WhatsAppAccountStatus
    created_at: datetime
    updated_at: datetime


class WhatsAppTemplateOut(BaseModel):
    """One approved (or pending/rejected) message template, flattened for the UI."""

    name: str
    language: str
    status: str
    category: str
    body_text: str
    variable_count: int


class WhatsAppBusinessProfileOut(BaseModel):
    """The public business profile customers see (the "about" card). All fields
    are optional — a freshly-connected number may have none set yet.
    ``profile_picture_url`` is read-only (uploaded out-of-band)."""

    about: str | None = None
    address: str | None = None
    description: str | None = None
    email: str | None = None
    vertical: str | None = None
    websites: list[str] = Field(default_factory=list)
    profile_picture_url: str | None = None


class WhatsAppBusinessProfileUpdate(BaseModel):
    """Patch editable business-profile fields. Omit a field to leave it
    untouched — only fields explicitly set are sent on to Meta."""

    about: str | None = None
    address: str | None = None
    description: str | None = None
    email: str | None = None
    vertical: str | None = None
    websites: list[str] | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    channel: ConversationChannel
    contact_wa_id: str
    contact_name: str | None
    lead_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    status: ConversationStatus
    last_message_at: datetime | None
    last_message_preview: str | None
    last_inbound_at: datetime | None
    assignee_id: uuid.UUID | None
    unread_count: int
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def service_window_expires_at(self) -> datetime | None:
        """When the 24h free-form window closes (None if never opened). The UI
        uses this to warn the agent before a free-form send gets rejected."""
        from app.whatsapp import service_window_expires_at

        return service_window_expires_at(self.last_inbound_at)

    @computed_field
    @property
    def service_window_open(self) -> bool:
        """Whether free-form (non-template) sends are currently allowed."""
        from app.whatsapp import service_window_open

        return service_window_open(self.last_inbound_at)


class ConversationLink(BaseModel):
    """Attach (or detach) a conversation from a CRM record.

    Omit a field to leave it untouched; send it as ``null`` to clear the link.
    The route reads ``model_fields_set`` to distinguish the two cases."""

    lead_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None


class ConversationStatusUpdate(BaseModel):
    """Move a thread through its lifecycle: ``open`` ⇄ ``closed`` ⇄ ``archived``.
    A ``closed`` thread auto-reopens on the next inbound message; ``archived``
    stays put until reopened by hand."""

    status: ConversationStatus


class ConversationAssign(BaseModel):
    """Assign a thread to an agent — or release it back to the shared queue.

    ``assignee_id`` is the target agent (must belong to the caller's org); send
    ``null`` to unassign. The field is required so the intent is always explicit
    (unlike ``ConversationLink``, there is no "leave untouched" case here)."""

    assignee_id: uuid.UUID | None


class ConversationConvert(BaseModel):
    """Spin up a CRM record from a WhatsApp thread, then link the thread to it.

    ``target`` picks Lead vs Customer. The new record's name defaults from the
    contact's WhatsApp profile name (first token → ``first_name``, the rest →
    ``last_name``); pass ``first_name``/``last_name`` to override. The contact's
    ``wa_id`` always seeds the phone in E.164 (``+<digits>``)."""

    target: Literal["lead", "customer"]
    first_name: Annotated[str | None, Field(default=None, max_length=120)] = None
    last_name: Annotated[str | None, Field(default=None, max_length=120)] = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    wa_message_id: str | None
    direction: MessageDirection
    type: MessageType
    body: str | None
    media_id: str | None
    media_url: str | None
    context_wa_message_id: str | None
    status: MessageStatus
    error: str | None
    sender_user_id: uuid.UUID | None
    timestamp: datetime
    created_at: datetime


class SendMessageRequest(BaseModel):
    """Agent-composed outbound text. Capped at WhatsApp's ~4096-char body.

    `reply_to_message_id` (one of our Message UUIDs in the same conversation)
    sends this as a quoted reply threaded under that message."""

    body: Annotated[str, Field(min_length=1, max_length=4096)]
    reply_to_message_id: uuid.UUID | None = None


class SendTemplateRequest(BaseModel):
    """Send a pre-approved WhatsApp message template — the ONLY way to message a
    contact outside the 24h customer-service window (a free-form text there is
    rejected by Meta).

    ``template_name`` + ``language_code`` identify an approved template in the
    WABA. ``body_params`` fills the template's positional ``{{1}}``, ``{{2}}`` …
    body placeholders in order; leave it empty for a template with no variables.
    We don't fetch the template catalog, so an unknown name / wrong placeholder
    count surfaces as a Meta send error on the message row."""

    template_name: Annotated[str, Field(min_length=1, max_length=512)]
    language_code: Annotated[str, Field(default="en_US", min_length=2, max_length=15)] = "en_US"
    body_params: Annotated[list[str], Field(default_factory=list, max_length=30)] = []


class SendMediaRequest(BaseModel):
    """Send an outbound media message (image / document / video / audio).

    Source the media EITHER by ``link`` (a public https URL Meta fetches) OR by
    ``media_id`` (a handle from an earlier upload to Meta) — exactly one. We do
    NOT proxy bytes through our backend; the link route is the common case (e.g.
    a hosted/presigned file URL). ``caption`` is honoured for image/video/
    document only; ``filename`` for document only (both ignored otherwise so a
    stray field is forgiving, not a 422)."""

    media_type: Literal["image", "document", "video", "audio"]
    link: Annotated[str | None, Field(default=None, max_length=2048)] = None
    media_id: Annotated[str | None, Field(default=None, max_length=128)] = None
    caption: Annotated[str | None, Field(default=None, max_length=1024)] = None
    filename: Annotated[str | None, Field(default=None, max_length=255)] = None
    reply_to_message_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "SendMediaRequest":
        if bool(self.link) == bool(self.media_id):
            raise ValueError("provide exactly one of `link` or `media_id`")
        if self.link and not self.link.startswith(("https://", "http://")):
            raise ValueError("`link` must be an http(s) URL")
        return self


class MediaDownloadOut(BaseModel):
    """Short-lived presigned URL for an inbound message's mirrored media —
    the SPA redirects the browser there to stream it straight from S3."""

    url: str
    expires_in: int


class InteractiveButton(BaseModel):
    """One reply button. `id` comes back verbatim in the inbound button_reply,
    so it's the stable handle automations key off; `title` is the visible label
    (Meta caps it at 20 chars)."""

    id: Annotated[str, Field(min_length=1, max_length=256)]
    title: Annotated[str, Field(min_length=1, max_length=20)]


class InteractiveRow(BaseModel):
    """One selectable row in a list section."""

    id: Annotated[str, Field(min_length=1, max_length=200)]
    title: Annotated[str, Field(min_length=1, max_length=24)]
    description: Annotated[str | None, Field(default=None, max_length=72)] = None


class InteractiveSection(BaseModel):
    """A titled group of list rows."""

    title: Annotated[str | None, Field(default=None, max_length=24)] = None
    rows: Annotated[list[InteractiveRow], Field(min_length=1, max_length=10)]


class SendInteractiveRequest(BaseModel):
    """Send an interactive message: reply buttons (`interactive_type="button"`,
    1-3 buttons) or a list menu (`"list"`, up to 10 rows total across sections).

    Both are session messages — only deliverable INSIDE the 24h window, same as
    free-form text. The Meta size caps live on the nested models; this validator
    enforces that the fields present match the chosen type and that the reply
    ids are unique (a duplicate id makes the inbound reply ambiguous)."""

    interactive_type: Literal["button", "list"]
    body_text: Annotated[str, Field(min_length=1, max_length=1024)]
    header_text: Annotated[str | None, Field(default=None, max_length=60)] = None
    footer_text: Annotated[str | None, Field(default=None, max_length=60)] = None
    buttons: Annotated[list[InteractiveButton] | None, Field(default=None, max_length=3)] = None
    button_text: Annotated[str | None, Field(default=None, max_length=20)] = None
    sections: Annotated[list[InteractiveSection] | None, Field(default=None, max_length=10)] = None
    reply_to_message_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _shape(self) -> "SendInteractiveRequest":
        if self.interactive_type == "button":
            if not self.buttons:
                raise ValueError("`buttons` is required for interactive_type=button (1-3)")
            if self.sections or self.button_text:
                raise ValueError("`sections`/`button_text` are list-only fields")
            ids = [b.id for b in self.buttons]
        else:
            if not self.sections:
                raise ValueError("`sections` is required for interactive_type=list")
            if not self.button_text:
                raise ValueError("`button_text` is required for interactive_type=list")
            if self.buttons:
                raise ValueError("`buttons` is a button-only field")
            if sum(len(s.rows) for s in self.sections) > 10:
                raise ValueError("a list may carry at most 10 rows total")
            ids = [r.id for s in self.sections for r in s.rows]
        if len(ids) != len(set(ids)):
            raise ValueError("interactive reply ids must be unique")
        return self


class SendReactionRequest(BaseModel):
    """React to a message with a single emoji. The target message is named by
    the URL (`/messages/{message_id}/reaction`), so only the emoji is in the
    body. An empty string removes a previously sent reaction (Meta's
    convention); any non-empty value must be a single emoji grapheme — we don't
    validate the unicode here, Meta rejects a non-emoji with a send error."""

    emoji: Annotated[str, Field(default="", max_length=8)] = ""

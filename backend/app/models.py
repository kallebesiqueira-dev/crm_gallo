import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    sales_agent = "sales_agent"
    support_agent = "support_agent"
    client = "client"


class LeadStage(str, enum.Enum):
    new = "new"
    contacted = "contacted"
    qualified = "qualified"
    proposal_sent = "proposal_sent"
    negotiation = "negotiation"
    won = "won"
    lost = "lost"


class DealStage(str, enum.Enum):
    new = "new"
    qualified = "qualified"
    proposal_sent = "proposal_sent"
    negotiation = "negotiation"
    won = "won"
    lost = "lost"


class Currency(str, enum.Enum):
    EUR = "EUR"
    CHF = "CHF"
    USD = "USD"
    GBP = "GBP"


class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class QuoteStatus(str, enum.Enum):
    """Lifecycle of a quote/proposal (ADR-016).

    State machine (enforced in `app/api/quotes.py`):
        draft ──send──▶ sent ──accept──▶ accepted
                          │  └─decline──▶ declined
                          └────expire──▶ expired
    `draft` is the only editable state. Once sent the document is
    immutable — a "resend with changes" clones it into a new version
    (the old row keeps its terminal state and points at the new one
    via `superseded_by`).
    """

    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"


class ContractStatus(str, enum.Enum):
    """Lifecycle of a contract / agreement (ADR-016).

    State machine (enforced in `app/api/contracts.py`):
        draft ──send──▶ sent ──sign──▶ signed ──activate──▶ active
                                          │                    │
                                          └───terminate────────┴──▶ terminated
        active ──(time)──▶ expired   (set by a future cron, no endpoint)

    `draft` is the only editable state. Once sent the agreement is
    immutable — a "re-issue with changes" clones it into a new version
    (the old row keeps its terminal state and points at the new one via
    `superseded_by`), exactly like Quote. `terminate` is the early-exit
    path from a signed or active contract; `expired` is the natural
    end-of-term state (reached by a scheduled sweep, mirroring how a
    quote expires — there is no manual transition for it).
    """

    draft = "draft"
    sent = "sent"
    signed = "signed"
    active = "active"
    terminated = "terminated"
    expired = "expired"


class DocumentType(str, enum.Enum):
    """The kind of document a merge-field template targets (ADR-016).

    Only `contract` is wired today (templates seed `Contract.body`);
    the enum exists so quote / invoice templates can be added later
    without a schema change to the discriminator.
    """

    contract = "contract"


class ImportEntityType(str, enum.Enum):
    """Which CRM entity a bulk import targets (ADR-016 imports slice).

    Only the two contact-shaped entities are importable today — they
    carry the email/phone keys the dedupe logic matches on. Deals/tasks
    would need a customer-linkage resolution step, deferred.
    """

    lead = "lead"
    customer = "customer"


class ImportMode(str, enum.Enum):
    """How a row that matches an existing record is handled.

    `create`  — matched rows are skipped (insert-only; safest default).
    `upsert`  — matched rows have their non-empty columns updated.
    Match key is `(org, lower(email))` first, then normalised phone.
    """

    create = "create"
    upsert = "upsert"


class ImportStatus(str, enum.Enum):
    """Lifecycle of an import job (driven by the `process_import` worker).

        pending ──▶ processing ──▶ completed
                                └▶ failed   (fatal parse/read error)

    A `completed` job may still carry per-row errors in `error_report` —
    `failed` is reserved for a whole-file failure (unreadable, unknown
    columns, empty), where nothing was imported.
    """

    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class SignatureStatus(str, enum.Enum):
    """Lifecycle of an e-signature request / envelope (ADR-016).

    State machine (enforced in `app/api/signatures.py`):
        drafted ──send──▶ sent ──view──▶ viewed ──sign──▶ signed (terminal)
                            │               │
                            └────decline────┴──▶ declined (terminal)
        (drafted|sent|viewed) ──cancel──▶ cancelled (terminal)

    `signed` is the completion state — all required parties have signed.
    A separate `countersigned` is reserved for a future counter-signature
    step (org signs after the customer) and is not yet reachable, mirroring
    how `QuoteStatus.expired` is declared ahead of its transition.
    """

    drafted = "drafted"
    sent = "sent"
    viewed = "viewed"
    signed = "signed"
    countersigned = "countersigned"
    declined = "declined"
    cancelled = "cancelled"


class Plan(str, enum.Enum):
    free = "free"
    standard = "standard"
    business = "business"
    premium = "premium"


class BillingCycle(str, enum.Enum):
    monthly = "monthly"
    yearly = "yearly"


class ApiKeyScope(str, enum.Enum):
    """Coarse-grained permission a Public-API key carries.

    `read`  — GET only (idempotent, safe verbs).
    `write` — everything `read` can do, plus create/update/delete.
    A key stores a SET of scopes (`["read"]` or `["read","write"]`);
    the bearer dependency maps the request's HTTP method to the scope
    it requires. Intentionally coarse for v1 — per-resource scopes
    (`leads:read`) can be added later without a schema change since
    scopes live in a JSON column, not a Postgres enum.
    """

    read = "read"
    write = "write"


# SoftDeleteMixin moved to `app.mixins` to break a circular import
# (database.py needs the mixin class to wire its global filter event;
# models.py needs Base from database.py). Re-exported here so any
# existing `from app.models import SoftDeleteMixin` keeps working.
from app.mixins import SoftDeleteMixin  # noqa: E402


class Organization(Base):
    """A tenant. Owns billing, subscriptions, and every domain entity
    (leads, customers, deals, tasks). Created on first sign-up and via
    the invite/onboarding flows. Stripe sees one Customer per Organization
    — seats are users within the org, not separate Stripe customers.
    """

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # URL-friendly identifier — used in future org-scoped routes and as
    # a stable handle in logs. Unique across the install.
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    # Billing — these will MOVE here from User once every endpoint that
    # reads user.plan is refactored. For now both Organization and User
    # carry the columns; the org is the source of truth for new code.
    plan: Mapped[Plan] = mapped_column(
        Enum(Plan), default=Plan.free, server_default=Plan.free.value, nullable=False
    )
    billing_cycle: Mapped[BillingCycle] = mapped_column(
        Enum(BillingCycle),
        default=BillingCycle.monthly,
        server_default=BillingCycle.monthly.value,
        nullable=False,
    )
    plan_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan_renewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan_canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    memberships: Mapped[list["OrgMembership"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class OrgInvite(Base):
    """A pending invitation for an email to join an Organization.

    Generated by an org admin, carries the role the invitee will get on
    accept. The `token` is the URL-safe handle delivered out-of-band
    (email today is just a stdout log; real SMTP comes in P1 auth
    hardening). `accepted_at` is the single-use marker — once set the
    token is dead. `expires_at` defaults to +7 days at insert time.
    """

    __tablename__ = "org_invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    # URL-safe token, ~43 chars from secrets.token_urlsafe(32). Unique
    # globally so an exposed token can be looked up directly without
    # needing the org slug in the URL.
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship()


class PasswordResetToken(Base):
    """Single-use, time-bounded credential for the forgot-password flow.

    The token (URL-safe, ~43 chars from `secrets.token_urlsafe(32)`) is
    delivered to the user out-of-band — today via the dev log line
    `password_reset.dispatched url=…`, eventually via SMTP. Possession
    of a valid (not-expired, not-used) token authorises one password
    change for the bound user.

    Burning: `used_at` is set on successful reset; any further attempt
    with the same token returns 410 Gone.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailVerificationToken(Base):
    """Single-use, time-bounded credential for the email-verification flow.

    Mirrors `PasswordResetToken` exactly. Minted on self-registration for
    every user that is NOT auto-verified (i.e. not the first user, not an
    invitee). The token (URL-safe, ~43 chars from `secrets.token_urlsafe(32)`)
    is delivered out-of-band — today via the dev log line
    `email_verification.dispatched url=…`, eventually via SMTP. Possession
    of a valid (not-expired, not-used) token marks the bound user's email
    verified, which is the precondition for logging in.

    Burning: `used_at` is set once the email is confirmed; any further
    attempt with the same token returns 410 Gone.
    """

    __tablename__ = "email_verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MfaBackupCode(Base):
    """Single-use one-time recovery code for the TOTP MFA flow.

    Ten codes are generated when MFA is enabled. They cover the
    "authenticator app is lost / phone died" path: a user submits a
    code to /mfa/verify instead of a TOTP, and it's burned on use.
    The plaintext code is shown to the user ONCE at enable time and
    never persisted — we store only a bcrypt hash, same model as
    passwords. Listing codes after enable returns just the count of
    remaining (unused) codes, never the codes themselves.
    """

    __tablename__ = "mfa_backup_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrgMembership(Base):
    """Many-to-many junction between User and Organization. Each row holds
    the user's role inside that org — so the same user can be admin in
    one org and sales_agent in another. The composite PK guarantees one
    membership row per (user, org) pair.
    """

    __tablename__ = "org_memberships"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # `role` is the LEGACY single-tenant role — kept while we migrate every
    # callsite to OrgMembership.role. Will be dropped in a follow-up.
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.sales_agent, nullable=False
    )
    locale: Mapped[str] = mapped_column(String(5), default="en", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Email verification (anti-abuse on the Free tier). Self-signups land
    # with `email_verified=False` and must click the link in their
    # verification email before they can log in. The very first user (the
    # install founder) and invited users — who already proved control of
    # their inbox via the invite link — are created verified. Existing
    # rows are grandfathered verified by the migration's server_default
    # (true), which is then cleared so new rows fall back to this model
    # default (False).
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # TOTP MFA. `mfa_secret` is the base32 shared secret bound to the
    # user's authenticator app — plaintext in v1 (env-level encryption
    # is a follow-up; today the DB itself is the trust boundary).
    # Populated when /setup runs; only honoured when `mfa_enabled` is
    # True. `mfa_enrolled_at` records the moment the user finished
    # /enable so audit traces have a timestamp.
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64))
    mfa_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Which org the user is currently working in. Set on login from the
    # first membership; the user can switch via PATCH /me. Null when the
    # user has zero memberships (shouldn't happen post-migration, but
    # SET NULL avoids a circular FK problem at cascade-delete time).
    last_active_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
    )

    # Billing fields used to live here in the single-tenant era; they now
    # live on `Organization` (see ADR-013). The migration that dropped
    # them is `<revision>_drop_user_billing_columns`.

    # Optional team membership. A user can belong to at most one team
    # in v1 (a many-to-many junction is a follow-up if real customers
    # need cross-team users). `SET NULL` on team delete so wiping a
    # team doesn't orphan its members.
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    leads: Mapped[list["Lead"]] = relationship(back_populates="owner")
    deals: Mapped[list["Deal"]] = relationship(back_populates="owner")
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="assignee", foreign_keys="Task.assignee_id"
    )
    memberships: Mapped[list[OrgMembership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Lead(SoftDeleteMixin, Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Tenant scope — NOT NULL after backfill. Every query MUST filter by
    # this column; RLS will enforce defense-in-depth in a later iteration.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    company: Mapped[str | None] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(2))
    company_size: Mapped[int | None] = mapped_column(Integer)
    budget: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    source: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)

    stage: Mapped[LeadStage] = mapped_column(Enum(LeadStage), default=LeadStage.new, nullable=False)
    # Optional team scope — when set, the lead shows up under that
    # team's filtered list view. `SET NULL` on team delete so the
    # lead doesn't disappear when a team is wound down.
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        index=True,
    )

    ai_score: Mapped[int | None] = mapped_column(Integer)
    ai_priority: Mapped[str | None] = mapped_column(String(20))
    ai_next_action: Mapped[str | None] = mapped_column(Text)
    ai_conversion_probability: Mapped[float | None] = mapped_column(Float)
    ai_risk_analysis: Mapped[str | None] = mapped_column(Text)
    ai_scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    owner: Mapped[User | None] = relationship(back_populates="leads")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Customer(SoftDeleteMixin, Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    company: Mapped[str | None] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(2))
    address: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_summary_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    deals: Mapped[list["Deal"]] = relationship(back_populates="customer")

    # Optimistic locking — see Deal.version. Bumped on every PATCH;
    # clients echo it as `If-Match`. Header optional in v1.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Deal(SoftDeleteMixin, Base):
    __tablename__ = "deals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    currency: Mapped[Currency] = mapped_column(Enum(Currency), default=Currency.EUR, nullable=False)
    stage: Mapped[DealStage] = mapped_column(Enum(DealStage), default=DealStage.new, nullable=False)
    probability: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    # Optional team scope (see Lead.team_id for the rationale).
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        index=True,
    )

    # Soft ordering inside a stage column for kanban drag-drop.
    sort_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Optimistic locking — bumped on every mutation. Clients send the
    # current value as `If-Match: <version>` on PATCH/move; mismatch
    # returns 409. Mitigates the silent-overwrite class of bugs when
    # two sales reps edit the same deal during a meeting. v1 ships
    # with the header OPTIONAL (logs a warning if missing) so a
    # frontend rollout doesn't have to land in lockstep.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL")
    )
    customer: Mapped[Customer | None] = relationship(back_populates="deals")

    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    owner: Mapped[User | None] = relationship(back_populates="deals")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Quote(SoftDeleteMixin, Base):
    """A versioned quote / proposal (ADR-016).

    Polymorphic-ish links: a quote optionally hangs off a Deal and/or a
    Customer (both nullable FK, SET NULL on delete) so it can be raised
    from a pipeline deal or directly for a customer. Totals are computed
    server-side from the line items (never trusted from the client).

    Versioning: `number` is the human-facing identifier (e.g. `Q-000007`),
    stable across revisions; `version` increments each time the quote is
    re-issued. Re-issuing a `sent` quote clones it into `version + 1` as a
    fresh `draft`; the prior row keeps its terminal status and sets
    `superseded_by` to the new row. `(organization_id, number, version)`
    is unique — never two live revisions with the same pair.

    `draft` is the only mutable status; the state machine lives in
    `app/api/quotes.py`. Soft-deletable like every tenant entity.
    """

    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id", ondelete="SET NULL"), index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )

    number: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[QuoteStatus] = mapped_column(
        Enum(QuoteStatus), default=QuoteStatus.draft, nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[Currency] = mapped_column(Enum(Currency), default=Currency.EUR, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    # Money columns are server-computed (recompute_totals in
    # app/services/quotes.py). Stored as Numeric/Decimal — never float —
    # so per-line rounding + summation are exact (ADR-015 / TD-30).
    # `tax_rate` is a percentage (e.g. 22.000 for the standard Italian IVA);
    # tax_amount = q2(subtotal * tax_rate / 100).
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=Decimal("0"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)

    # Revision chain: the prior version points forward to its replacement.
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="SET NULL")
    )

    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    # Lifecycle timestamps — set as the quote transitions.
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    line_items: Mapped[list["QuoteLineItem"]] = relationship(
        back_populates="quote",
        cascade="all, delete-orphan",
        order_by="QuoteLineItem.sort_index",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class QuoteLineItem(Base):
    """A single line on a quote. Belongs to exactly one quote version —
    cloning a quote into a new version deep-copies its line items.

    Carries `organization_id` (denormalised from the parent quote) so it
    can be RLS-scoped directly, keeping the "every tenant table enforces
    org isolation at the row level" invariant rather than relying on the
    join to `quotes` (avoids a TD-42-style gap). Not soft-deletable: a
    line is part of an immutable sent document, or freely
    editable/removable while the parent is still a draft.
    """

    __tablename__ = "quote_line_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    # quantity allows fractional units (e.g. 2.5 hours); the money
    # columns are Numeric/Decimal so quantity * unit_price is exact.
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("1"), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    # line_total = q2(quantity * unit_price); recomputed server-side.
    line_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    sort_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    quote: Mapped[Quote] = relationship(back_populates="line_items")


class Contract(SoftDeleteMixin, Base):
    """A versioned contract / agreement (ADR-016).

    The formal agreement that follows an accepted quote. Distinct from
    Quote on purpose — it is NOT a re-itemised quote clone:

      * It carries a **term** (`effective_date` / `end_date`), optional
        **auto-renewal** (`auto_renew` + `renewal_term_months`), and a
        free-text **terms body** — the things a quote does not have.
      * It stores a single `value` (the agreed amount) rather than line
        items; the itemisation lives on the source quote (`quote_id`).
        The merge-field template engine (admin-editable terms with line
        roll-up) is a separate backlog item.

    Links: optional `quote_id` (the quote it was generated from),
    `customer_id`, and `deal_id` — all nullable FK SET NULL.

    Versioning + lifecycle mirror Quote: `number` (e.g. `C-000007`) is
    stable across revisions, `version` increments on re-issue, and
    `(organization_id, number, version)` is unique. `draft` is the only
    mutable status; the state machine lives in `app/api/contracts.py`.
    Soft-deletable + RLS like every tenant entity.
    """

    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="SET NULL"), index=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id", ondelete="SET NULL"), index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )

    number: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[ContractStatus] = mapped_column(
        Enum(ContractStatus), default=ContractStatus.draft, nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[Currency] = mapped_column(Enum(Currency), default=Currency.EUR, nullable=False)
    # The agreed contract value. Decimal/Numeric — never float (ADR-015).
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)

    # The term + renewal — what makes a contract a contract.
    effective_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    renewal_term_months: Mapped[int | None] = mapped_column(Integer)

    body: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    # Provenance: the template (if any) whose rendered output seeded
    # `body`. The render is materialised at apply-time — `body` is frozen
    # text, NOT late-bound — so this is for traceability only and survives
    # the template being later edited or deleted (SET NULL).
    applied_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_templates.id", ondelete="SET NULL")
    )

    # Revision chain: the prior version points forward to its replacement.
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="SET NULL")
    )

    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    # Lifecycle timestamps — set as the contract transitions.
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentTemplate(SoftDeleteMixin, Base):
    """A reusable, admin-authored document body with merge fields (ADR-016).

    The `body` is free text containing allow-listed `{{ token }}`
    placeholders (e.g. `{{ customer.name }}`, `{{ contract.value }}`,
    `{{ line_items }}`). Applying a template to a draft contract
    resolves those tokens against the contract's context and writes the
    rendered string into `Contract.body` — a one-shot materialisation,
    not a live binding. The token catalog + render live in
    `app/documents/merge.py`; substitution is plain regex against a
    resolved string map (NO expression eval — the body is operator-
    authored legal text, so SSTI is out of scope by construction).

    Org-scoped + RLS + soft-deletable like every tenant entity. One
    template may be flagged `is_default` per (org, doc_type) — enforced
    in the API, not the schema, since toggling is a mutate.
    """

    __tablename__ = "document_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    doc_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType), default=DocumentType.contract, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ImportJob(Base):
    """One bulk-import run of a CSV/XLSX file into leads or customers.

    The HTTP layer uploads the file to S3 and creates this row in
    `pending`; the `process_import` worker job downloads it, parses +
    validates row-by-row, dedupes against existing records, and writes
    back the outcome counters + a capped per-row `error_report`. The SPA
    polls `GET /api/imports/{id}` until `status` is terminal.

    Org-scoped + RLS like every tenant table. NOT soft-deletable — an
    import job is an operational record (think: a receipt), not a CRM
    entity a user trashes/restores; a retention prune is the eventual
    cleanup path, not the trash bin.

    `error_report` is a JSONB list of `{row, field, message}` objects,
    capped (see the worker) so a 50k-row file that's wrong on every line
    can't bloat the row to megabytes.
    """

    __tablename__ = "import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    entity_type: Mapped[ImportEntityType] = mapped_column(Enum(ImportEntityType), nullable=False)
    mode: Mapped[ImportMode] = mapped_column(
        Enum(ImportMode), default=ImportMode.create, nullable=False
    )
    status: Mapped[ImportStatus] = mapped_column(
        Enum(ImportStatus), default=ImportStatus.pending, nullable=False
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)

    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # List[{row:int, field:str|None, message:str}] — capped in the worker.
    error_report: Mapped[list | None] = mapped_column(JSONB)
    # Set only on a whole-file failure (unreadable / unknown columns).
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SignatureRequest(SoftDeleteMixin, Base):
    """An e-signature envelope raised against a Quote or a Contract (ADR-016).

    A request asks one external signer (the customer) to sign a document —
    a sent quote or a sent contract. Signing is delegated to a
    `SignatureProvider` (`app/signing/providers.py`): the dev/low-stakes
    `manual` provider signs in-app via an opaque `sign_token` link; the
    `skribble`/`scrive` adapters delegate to a QES/eIDAS vendor and report
    completion back through the inbound webhook receiver. A homegrown
    click-to-accept is NOT a qualified signature — the provider seam is what
    keeps the upgrade to QES a config change, not a rewrite.

    The signed document is referenced by exactly ONE of `quote_id` /
    `contract_id` — both nullable FKs with `ON DELETE CASCADE`, guarded by a
    DB CHECK so a request always points at precisely one document. Typed FKs
    (rather than a polymorphic `entity_type`/`entity_id`) preserve referential
    integrity for the legal-signature record and let the completion side
    effect stay typed.

    Tenant-scoped with RLS + a denormalised `organization_id` (same invariant
    as `quote_line_items` — every tenant table isolates at the row level
    rather than via a join). Soft-deletable so it lands in the trash bin like
    every other tenant entity.

    Completion side effect (see `app/api/signatures.py`): signing a request
    whose quote is still `sent` transitions that quote to `accepted` (a signed
    quote IS an acceptance); signing a request whose contract is still `sent`
    transitions that contract to `signed`.
    """

    __tablename__ = "signature_requests"
    __table_args__ = (
        # Exactly one document link is set — a request signs a quote XOR a
        # contract, never both, never neither.
        CheckConstraint(
            "(quote_id IS NOT NULL) <> (contract_id IS NOT NULL)",
            name="ck_signature_requests_one_document",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        index=True,
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        index=True,
    )

    # Which backend owns this envelope. Captured at create time from
    # settings.signing_provider so a later config switch doesn't strand
    # in-flight envelopes on the wrong provider.
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    status: Mapped[SignatureStatus] = mapped_column(
        Enum(SignatureStatus), default=SignatureStatus.drafted, nullable=False
    )

    signer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    signer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Optional cover note shown to the signer.
    message: Mapped[str | None] = mapped_column(Text)

    # Provider-side envelope id (Skribble/Scrive). NULL for the manual
    # provider, which is driven entirely by `sign_token`.
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    # Opaque bearer token for the manual signing link — the token IS the
    # credential (like an org-invite token), so the signer reaches the sign
    # endpoint without an account. Unique; minted on send.
    sign_token: Mapped[str | None] = mapped_column(String(64))

    # The source document presented for signing (the quote PDF). SET NULL on
    # attachment delete — the request stays as an audit record.
    document_attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file_attachments.id", ondelete="SET NULL")
    )
    # S3 key of the signed artifact + provider audit trail, set on completion
    # (ADR-016: store the signed PDF / audit trail in S3).
    signed_document_key: Mapped[str | None] = mapped_column(String(500))

    # Signing-event audit trail (the legal record for the manual provider).
    signed_ip: Mapped[str | None] = mapped_column(String(64))
    signed_user_agent: Mapped[str | None] = mapped_column(String(400))
    decline_reason: Mapped[str | None] = mapped_column(Text)

    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Task(SoftDeleteMixin, Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.todo, nullable=False
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority), default=TaskPriority.medium, nullable=False
    )
    due_date: Mapped[date | None] = mapped_column(Date)

    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    assignee: Mapped[User | None] = relationship(back_populates="tasks", foreign_keys=[assignee_id])

    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL")
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("deals.id", ondelete="SET NULL"))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"))

    # Optimistic locking — see Deal.version. Bumped on every PATCH;
    # clients echo it as `If-Match`. Header optional in v1.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Notification(Base):
    """In-app notification for a single user.

    Distinct from `Activity` (entity timeline, visible to anyone in
    the org) and `AuditLog` (admin compliance ledger): a notification
    is something one specific person is supposed to ACT on — a task
    they were just assigned, a deal that moved in their pipeline.
    Renders in the header bell + unread counter.

    `type` is a curated slug (see `app.notifications.NotificationType`)
    so the UI can map to an icon + i18n label without parsing
    free-form text. `link_url` is the in-app target the bell links
    to ("go to the task that was just assigned"). `read_at` is null
    until the user opens / dismisses the entry.

    Not soft-deletable — notifications are an ephemeral inbox, not
    a record. A future retention cron prunes anything > 90 days
    (P3 follow-up).
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Optional actor — the user whose action triggered this
    # notification. Lets the UI render "Alice assigned you a task"
    # instead of an anonymous "task assigned".
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    # Relative path (e.g. `/leads/<uuid>`) the bell can link to. Not
    # absolute so locale prefix is added client-side.
    link_url: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PipelineKind(str, enum.Enum):
    """A pipeline is either a LEAD pipeline (qualification funnel) or a
    DEAL pipeline (sales funnel). They have different semantics + render
    in different views; keeping them as separate kinds lets one org
    have multiple of each (Inbound vs Outbound leads, Enterprise vs
    SMB deals)."""

    lead = "lead"
    deal = "deal"


class Pipeline(SoftDeleteMixin, Base):
    """Customer-defined funnel. Replaces the hardcoded LeadStage /
    DealStage enums (which are kept as a denormalised cache during
    the multi-phase migration — see ADR / skills.md).

    `is_default` exists so each org has exactly one default pipeline
    per kind — that's where `Lead.create` lands by default, where the
    kanban opens on first visit, etc. Enforced application-side
    (one-of-N within the same kind via the endpoint that toggles it);
    the DB-level guarantee would need a partial unique index that
    Phase 2 will add once we trust the data shape.
    """

    __tablename__ = "pipelines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[PipelineKind] = mapped_column(Enum(PipelineKind), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    stages: Mapped[list["PipelineStage"]] = relationship(
        back_populates="pipeline",
        cascade="all, delete-orphan",
        order_by="PipelineStage.position",
    )


class PipelineStage(SoftDeleteMixin, Base):
    """One column on a Pipeline's kanban. `position` is the sort
    order (small int = leftmost). `probability` is the % chance a
    deal at this stage closes won — used by the forecast widget.

    `is_won` / `is_lost` flag the terminal stages: when a deal lands
    in an `is_won` stage we treat it as realised revenue; in
    `is_lost` we treat it as discarded. Multiple won/lost stages
    per pipeline are allowed (some teams want "Won — direct" vs
    "Won — referral" for attribution).
    """

    __tablename__ = "pipeline_stages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipelines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    probability: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_won: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    pipeline: Mapped[Pipeline] = relationship(back_populates="stages")


class Team(SoftDeleteMixin, Base):
    """A group of users inside an Organization — e.g. "Inbound EU",
    "Enterprise NA", "Renewals". Optional grouping (orgs work fine
    without any teams); when set, enables team-scoped list filters
    on Lead/Deal and the future round-robin assignment helper.

    Per-org slug unique (partial unique index in migration so soft-
    deleted teams free the slug). Soft-deletable so re-creating a
    team with the same name doesn't lose the historical reference
    from leads/deals that pointed at it (`team_id` on those rows
    is `SET NULL` on hard-delete via the FK; soft-delete keeps the
    relationship visible in audit-style reads).
    """

    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # URL-safe slug for future /teams/{slug} routing; unique per org
    # via the partial index in the migration (NOT a column UNIQUE
    # because we want soft-deleted rows to free the slug).
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FileAttachment(SoftDeleteMixin, Base):
    """File attached to a Lead / Customer / Deal — uploaded contract,
    deck, scanned form, etc. The blob lives in S3 (or any S3-compatible
    store; MinIO in dev); this row is the metadata index.

    Polymorphic by `(entity_type, entity_id)` like Activity and Note.
    Soft-delete on the row; the S3 object is HARD-deleted on user
    delete to free storage immediately (restoring a soft-deleted
    attachment would require re-uploading the file — accepted
    trade-off vs. paying for orphaned blob storage indefinitely).

    Hashing: `sha256` lets us detect duplicates (same file uploaded
    twice → same hash) and verify integrity on download. Optional
    in v1 (computed at upload time; never re-verified yet).
    """

    __tablename__ = "file_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # `uploader_user_id` SET NULL on user delete — the audit trail
    # is the source of truth for "who did what"; the attachment
    # itself stays attached to the entity even if the uploader leaves.
    uploader_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Original filename as the user uploaded it — preserved verbatim
    # so the download Content-Disposition can re-use it.
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # S3 object key — see `app.storage.object_key` for the layout.
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Note(SoftDeleteMixin, Base):
    """Free-form markdown note attached to a Lead / Customer / Deal.

    Distinct from the `notes` text field on Lead/Customer — that was
    a single shared scratchpad; this is a per-user, multi-entry log
    where every team member can drop observations. Renders in the
    detail page's NotesPanel; creating one also emits a
    `note_added` Activity so the timeline reflects it.

    Polymorphic by (entity_type, entity_id) so a future Quote /
    Contract / Project can take notes too without a schema change.
    Soft-deletable (inherits `SoftDeleteMixin`) so the trash bin
    covers them like every other tenant entity.
    """

    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # `author_user_id` is the user who wrote the note. Nullable in
    # principle (CASCADE SET NULL on user delete) but we never insert
    # NULL — the endpoint always sets it from `get_current_user`.
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Markdown source — rendering is the frontend's job. Length cap
    # is generous; CRM notes occasionally include longer meeting
    # transcripts. 16kB matches what most modern textareas handle
    # before they start visibly lagging.
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Activity(Base):
    """User-facing event timeline: "what happened to THIS lead /
    customer / deal, in human terms".

    Distinct from `AuditLog`:
      * `AuditLog` is the SECURITY ledger (compliance, forensics,
        admin-only). It records every mutation including system
        events with no user-friendly mapping.
      * `Activity` is the USER-FACING ledger rendered on the entity
        detail page. Curated: only the events a sales rep cares
        about (created, stage_change, score, note_added, …) and
        always tagged with a user-friendly `type` from the enum
        below.

    Polymorphic by `entity_type + entity_id` (Lead | Customer | Deal)
    so a future Quote / Contract entity can join the timeline
    without a schema change. Append-only — never updated, never
    soft-deleted; if the underlying entity is purged, CASCADE on
    the lead/customer/deal FKs handles cleanup via the indirect
    path (we store entity_id as plain UUID, no DB-level FK because
    polymorphic, so we rely on the `purge_orphans` follow-up).
    """

    __tablename__ = "activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # `actor_user_id` is nullable: system-emitted activities (an
    # incoming-email auto-import, a scheduled re-score) have no user.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Free-form type slug — the enum lives in the API layer
    # (`app.activities.ActivityType`) so adding a new type doesn't
    # need a DB migration. UI maps the slug → translated label.
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    # Optional human-readable summary ("Stage moved from new →
    # qualified"). Localised on render — see frontend.
    content: Mapped[str | None] = mapped_column(Text)
    # Structured payload for type-specific fields (old/new stage,
    # AI score number, etc). JSON serialised to keep schema flexible.
    metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Nullable: platform-level events (a user logging in before they've
    # picked an org, webhook idempotency reconciliation) have no org
    # context. Tenant-scoped audits MUST set this.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(80))
    metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StripeEvent(Base):
    """Idempotency log for Stripe webhook events.

    Stripe re-delivers events on retry. We must dedupe by event id to avoid
    crediting a subscription twice or rolling back a cancellation.
    """

    __tablename__ = "stripe_events"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)  # Stripe event id
    type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class WebhookEndpoint(Base):
    """One subscriber's HTTP receiver for outbox events. Per-org.

    Each endpoint subscribes to a (curated) list of `EventType` slugs
    via `enabled_events` (or the wildcard `["*"]` meaning "every
    event"). The outbox dispatcher's webhook handler looks up the
    matching endpoints for an event's org + event_type, then enqueues
    one `deliver_webhook` arq job per (endpoint, event) pair. Per-
    delivery retry is then arq's job, isolated from the outbox drain
    so a slow receiver can't back-pressure the foundation.

    `secret` is hex 64 (32 bytes random), shown ONCE on create and
    never round-tripped on subsequent reads (mirrors how Stripe /
    GitHub render webhook signing secrets). Used by `app.webhook_sign`
    to compute the `X-CRM-Signature: t=<ts>,v1=<hex>` header.

    `consecutive_failures` auto-increments per failed delivery and
    resets on success. When it crosses `WEBHOOK_AUTO_PAUSE_THRESHOLD`
    (10), `paused_at` is set automatically — admin has to manually
    unpause via PATCH so a broken endpoint doesn't keep burning
    retries forever. `last_success_at` / `last_failure_at` surface
    in the admin UI for triage.

    Not soft-deletable: deleting an endpoint is a permanent op the
    admin chose intentionally. The CASCADE on org delete keeps things
    tidy when a tenant goes away.
    """

    __tablename__ = "webhook_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    # JSON-encoded array of event_type strings. `["*"]` = subscribe
    # to every event. Kept as text not Postgres ARRAY so the schema
    # stays portable (sqlite for unit tests, etc).
    enabled_events: Mapped[str] = mapped_column(Text, nullable=False, default='["*"]')
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookDelivery(Base):
    """One attempt to deliver one event to one endpoint.

    Cardinality: N (events) x M (matching endpoints) x P (retries).
    Useful for: "did my webhook fire for that lead?" triage in the
    admin UI, audit of what we tried to send, p95 latency tracking
    of receivers.

    `response_body_excerpt` is capped at 2 KB — the receiver's body
    might be huge (HTML error pages) and we don't want to balloon
    the DB. `latency_ms` is the wall time of the HTTP round trip,
    NOT including retry waits.

    Not RLS'd (same reasoning as outbox_events — the worker drains
    cross-org); admin endpoint filters by `organization_id` of the
    parent WebhookEndpoint via JOIN.
    """

    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Soft pointer (no FK): outbox rows can be pruned before their
    # deliveries; we still want the delivery row to survive for
    # historical triage.
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    # "pending" while the arq job is queued, "success" / "failed" once it ran.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    response_code: Mapped[int | None] = mapped_column(Integer)
    response_body_excerpt: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboxEvent(Base):
    """Transactional outbox (ADR-007). Domain mutations append a row
    here in the same DB transaction as the mutation. A periodic
    worker job (`drain_outbox`) claims unprocessed rows with
    `FOR UPDATE SKIP LOCKED`, invokes the in-process subscriber
    registry, and marks them processed. Guarantees at-least-once
    delivery without distributed-transaction pain.

    Not RLS'd on purpose: the worker (`crm_app` role,
    NOSUPERUSER/NOBYPASSRLS) needs to drain across all tenants in
    one pass; admin-facing reads filter by `organization_id`
    explicitly in the endpoint. `organization_id` is nullable so
    platform-level events (auth, billing webhook fan-out) can use
    the same channel.
    """

    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class ApiKey(Base):
    """A server-to-server credential for the Public API (/api/v1).

    The browser auth model (cookie + CSRF) can't serve a backend
    integrator — there's no browser to hold the cookie and no origin to
    scope CSRF to. An API key is the bearer credential for that path:
    issued by an org admin, presented as `Authorization: Bearer <token>`.

    **At-rest:** only the sha256 of the full token is stored
    (`hashed_key`, unique). The plaintext is shown exactly ONCE on
    create and never round-tripped on reads — mirrors how Stripe/GitHub
    render secrets, and how `WebhookEndpoint.secret` already behaves.
    `display_prefix` (e.g. `crmk_a1b2…wxyz`) is the non-secret label the
    UI lists so an admin can tell keys apart and pick which to revoke.

    **Token shape:** `crmk_{org_hex}_{secret}`. The org id is embedded
    (it is NOT a secret) so the bearer path can recover the tenant,
    set the `app.current_org_id` GUC, and *then* look the key up under
    RLS — the same trick the e-signature `sign_token` uses to read an
    RLS'd row before any session exists.

    **Scopes:** a JSON array of `ApiKeyScope` values (`["read"]` /
    `["read","write"]`). The bearer dependency maps the request verb to
    the scope it needs (GET→read, mutating→write).

    **Revocation is soft** (`revoked_at` timestamp, not a row delete) so
    the audit trail of which key did what survives the revoke. `expires_at`
    is an optional hard cutoff. A key is only usable while
    `revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now())`
    AND its creator user is still active (deactivating a user kills their
    keys — a deliberate v1 coupling so there's no orphaned credential
    outliving the human who owns it).

    Org-scoped + RLS like every tenant table. NOT soft-deletable in the
    trash sense — `revoked_at` is the lifecycle end-state.
    """

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # sha256 hex of the full `crmk_…` token. Unique so a lookup by hash
    # resolves at most one key.
    hashed_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Non-secret label for the UI list, e.g. `crmk_a1b2…wxyz`.
    display_prefix: Mapped[str] = mapped_column(String(40), nullable=False)
    # JSON-encoded array of ApiKeyScope values. Text (not PG ARRAY/enum)
    # so per-resource scopes can be added later without a migration.
    scopes: Mapped[str] = mapped_column(Text, nullable=False, default='["read"]')
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

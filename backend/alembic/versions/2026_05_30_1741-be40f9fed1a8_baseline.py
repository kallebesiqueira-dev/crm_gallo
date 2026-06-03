"""baseline

The original schema was first created directly from the SQLAlchemy
models (``Base.metadata.create_all``) and then *stamped* at this
revision, so for a long time this migration was an empty placeholder.
That worked on the persistent dev volume — the schema predated the
migration chain — but it meant ``alembic upgrade head`` could never
rebuild the database from zero: the very next migration
(``bcac4a2cdbfa``) references the ``plan`` / ``billingcycle`` /
``userrole`` enums and the ``users`` / ``leads`` / ``customers`` /
``deals`` / ``tasks`` / ``audit_logs`` tables, none of which an empty
baseline creates. CI (fresh Postgres) hit ``type "plan" does not
exist`` here.

This migration now materialises that pre-baseline schema as raw DDL,
reconstructed by downgrading a clone of the live database back to this
revision and dumping the result — so it is byte-for-byte the schema the
rest of the chain expects. Statements are issued one per ``op.execute``
because asyncpg's extended-query protocol rejects multi-statement
strings.

Revision ID: be40f9fed1a8
Revises:
Create Date: 2026-05-30 17:41:35.754799+00:00

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "be40f9fed1a8"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Enums ──────────────────────────────────────────────────────────────
_ENUMS = (
    "CREATE TYPE public.billingcycle AS ENUM ('monthly', 'yearly')",
    "CREATE TYPE public.currency AS ENUM ('EUR', 'CHF', 'USD', 'GBP')",
    "CREATE TYPE public.dealstage AS ENUM "
    "('new', 'qualified', 'proposal_sent', 'negotiation', 'won', 'lost')",
    "CREATE TYPE public.leadstage AS ENUM "
    "('new', 'contacted', 'qualified', 'proposal_sent', 'negotiation', 'won', 'lost')",
    "CREATE TYPE public.plan AS ENUM ('free', 'standard', 'premium')",
    "CREATE TYPE public.taskpriority AS ENUM ('low', 'medium', 'high')",
    "CREATE TYPE public.taskstatus AS ENUM ('todo', 'in_progress', 'done')",
    "CREATE TYPE public.userrole AS ENUM "
    "('admin', 'manager', 'sales_agent', 'support_agent', 'client')",
)

# ── Tables ─────────────────────────────────────────────────────────────
_TABLES = (
    """
    CREATE TABLE public.users (
        id uuid NOT NULL,
        email character varying(255) NOT NULL,
        full_name character varying(255) NOT NULL,
        hashed_password character varying(255) NOT NULL,
        role public.userrole NOT NULL,
        locale character varying(5) NOT NULL,
        is_active boolean NOT NULL,
        mfa_enabled boolean NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        plan public.plan DEFAULT 'free'::public.plan NOT NULL,
        billing_cycle public.billingcycle DEFAULT 'monthly'::public.billingcycle NOT NULL,
        plan_started_at timestamp with time zone,
        plan_renewed_at timestamp with time zone,
        plan_canceled_at timestamp with time zone,
        trial_ends_at timestamp with time zone,
        stripe_customer_id character varying(255),
        stripe_subscription_id character varying(255),
        CONSTRAINT users_pkey PRIMARY KEY (id)
    )
    """,
    """
    CREATE TABLE public.customers (
        id uuid NOT NULL,
        first_name character varying(120) NOT NULL,
        last_name character varying(120) NOT NULL,
        email character varying(255),
        phone character varying(50),
        company character varying(255),
        industry character varying(120),
        country character varying(2),
        address text,
        website character varying(255),
        notes text,
        ai_summary text,
        ai_summary_updated_at timestamp with time zone,
        owner_id uuid,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        deleted_at timestamp with time zone,
        CONSTRAINT customers_pkey PRIMARY KEY (id),
        CONSTRAINT customers_owner_id_fkey FOREIGN KEY (owner_id)
            REFERENCES public.users(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE public.leads (
        id uuid NOT NULL,
        first_name character varying(120) NOT NULL,
        last_name character varying(120) NOT NULL,
        email character varying(255),
        phone character varying(50),
        company character varying(255),
        industry character varying(120),
        country character varying(2),
        company_size integer,
        budget double precision,
        source character varying(120),
        notes text,
        stage public.leadstage NOT NULL,
        ai_score integer,
        ai_priority character varying(20),
        ai_next_action text,
        ai_conversion_probability double precision,
        ai_risk_analysis text,
        ai_scored_at timestamp with time zone,
        owner_id uuid,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        deleted_at timestamp with time zone,
        CONSTRAINT leads_pkey PRIMARY KEY (id),
        CONSTRAINT leads_owner_id_fkey FOREIGN KEY (owner_id)
            REFERENCES public.users(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE public.deals (
        id uuid NOT NULL,
        title character varying(255) NOT NULL,
        value double precision NOT NULL,
        currency public.currency NOT NULL,
        stage public.dealstage NOT NULL,
        probability integer NOT NULL,
        expected_close_date date,
        notes text,
        sort_index integer NOT NULL,
        customer_id uuid,
        owner_id uuid,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        deleted_at timestamp with time zone,
        CONSTRAINT deals_pkey PRIMARY KEY (id),
        CONSTRAINT deals_customer_id_fkey FOREIGN KEY (customer_id)
            REFERENCES public.customers(id) ON DELETE SET NULL,
        CONSTRAINT deals_owner_id_fkey FOREIGN KEY (owner_id)
            REFERENCES public.users(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE public.tasks (
        id uuid NOT NULL,
        title character varying(255) NOT NULL,
        description text,
        status public.taskstatus NOT NULL,
        priority public.taskpriority NOT NULL,
        due_date date,
        assignee_id uuid,
        customer_id uuid,
        deal_id uuid,
        lead_id uuid,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        deleted_at timestamp with time zone,
        CONSTRAINT tasks_pkey PRIMARY KEY (id),
        CONSTRAINT tasks_assignee_id_fkey FOREIGN KEY (assignee_id)
            REFERENCES public.users(id) ON DELETE SET NULL,
        CONSTRAINT tasks_customer_id_fkey FOREIGN KEY (customer_id)
            REFERENCES public.customers(id) ON DELETE SET NULL,
        CONSTRAINT tasks_deal_id_fkey FOREIGN KEY (deal_id)
            REFERENCES public.deals(id) ON DELETE SET NULL,
        CONSTRAINT tasks_lead_id_fkey FOREIGN KEY (lead_id)
            REFERENCES public.leads(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE public.audit_logs (
        id uuid NOT NULL,
        actor_id uuid,
        action character varying(120) NOT NULL,
        entity_type character varying(80) NOT NULL,
        entity_id character varying(80),
        metadata_json text,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT audit_logs_pkey PRIMARY KEY (id),
        CONSTRAINT audit_logs_actor_id_fkey FOREIGN KEY (actor_id)
            REFERENCES public.users(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE public.stripe_events (
        id character varying(255) NOT NULL,
        type character varying(120) NOT NULL,
        received_at timestamp with time zone DEFAULT now() NOT NULL,
        processed_at timestamp with time zone,
        payload text NOT NULL,
        CONSTRAINT stripe_events_pkey PRIMARY KEY (id)
    )
    """,
)

# ── Indexes ────────────────────────────────────────────────────────────
_INDEXES = (
    "CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email)",
    "CREATE INDEX ix_users_stripe_customer_id ON public.users USING btree (stripe_customer_id)",
    "CREATE INDEX ix_users_stripe_subscription_id ON public.users USING btree (stripe_subscription_id)",
    "CREATE INDEX ix_customers_email ON public.customers USING btree (email)",
    "CREATE INDEX ix_customers_deleted_at ON public.customers USING btree (deleted_at)",
    "CREATE INDEX ix_leads_email ON public.leads USING btree (email)",
    "CREATE INDEX ix_leads_deleted_at ON public.leads USING btree (deleted_at)",
    "CREATE INDEX ix_deals_deleted_at ON public.deals USING btree (deleted_at)",
    "CREATE INDEX ix_tasks_deleted_at ON public.tasks USING btree (deleted_at)",
    "CREATE INDEX ix_stripe_events_type ON public.stripe_events USING btree (type)",
)

# Tables in dependency order for a clean CASCADE-free drop on downgrade.
_DROP_TABLES = (
    "stripe_events",
    "audit_logs",
    "tasks",
    "deals",
    "leads",
    "customers",
    "users",
)

_DROP_ENUMS = (
    "userrole",
    "taskstatus",
    "taskpriority",
    "plan",
    "leadstage",
    "dealstage",
    "currency",
    "billingcycle",
)


def upgrade() -> None:
    for stmt in _ENUMS:
        op.execute(stmt)
    for stmt in _TABLES:
        op.execute(stmt)
    for stmt in _INDEXES:
        op.execute(stmt)


def downgrade() -> None:
    for table in _DROP_TABLES:
        op.execute(f"DROP TABLE IF EXISTS public.{table} CASCADE")
    for enum in _DROP_ENUMS:
        op.execute(f"DROP TYPE IF EXISTS public.{enum}")

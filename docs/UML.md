# CRM Gallo — UML (complete)

> **Source of truth:** generated from `backend/app/models.py`, `docker-compose.yml`,
> the API routers and the worker, on 2026-06-01. Keep it in sync when the schema changes.
>
> **How to view:** these are [Mermaid](https://mermaid.js.org) diagrams — they render
> natively on GitHub and in VS Code (install the *Markdown Preview Mermaid Support*
> extension, then open the preview). To export a PNG/SVG (like the ones in `../../uml_crm/`):
> `npx -y @mermaid-js/mermaid-cli -i docs/UML.md -o docs/uml.png`.

## Contents
1. [Domain class diagram — Identity, Tenancy & Auth](#1-class--identity-tenancy--auth)
2. [Domain class diagram — CRM Core](#2-class--crm-core)
3. [Domain class diagram — Collaboration & Timeline](#3-class--collaboration--timeline)
4. [Domain class diagram — Eventing, Integration & Audit](#4-class--eventing-integration--audit)
5. [Enumerations](#5-enumerations)
6. [Entity-Relationship map (all tables)](#6-entity-relationship-map-all-tables)
7. [Component / architecture diagram](#7-component--architecture-diagram)
8. [Deployment diagram (docker-compose)](#8-deployment-diagram-docker-compose)
9. [Use-case diagram (actors & roles)](#9-use-case-diagram-actors--roles)
10. [Sequence — Authentication + refresh rotation](#10-sequence--authentication--refresh-rotation)
11. [Sequence — Async AI lead scoring](#11-sequence--async-ai-lead-scoring)
12. [Sequence — Outbox → outgoing webhook](#12-sequence--outbox--outgoing-webhook)
13. [Sequence — Stripe billing](#13-sequence--stripe-billing)
14. [State — Deal pipeline & Webhook endpoint](#14-state--deal-pipeline--webhook-endpoint)
15. [Domain class diagram — Quotes, Contracts, Products & Documents](#15-class--quotes-contracts-products--documents)
16. [Domain class diagram — Omnichannel, Public API & Automation](#16-class--omnichannel-public-api--automation)
17. [Domain class diagram — Segmentation, Custom Fields, Imports, FX & Usage](#17-class--segmentation-custom-fields-imports-fx--usage)

---

## 1. Class — Identity, Tenancy & Auth

```mermaid
classDiagram
    class Organization {
        +UUID id
        +str name
        +str slug
        +Plan plan
        +BillingCycle billing_cycle
        +datetime plan_started_at
        +datetime plan_renewed_at
        +datetime plan_canceled_at
        +datetime trial_ends_at
        +str stripe_customer_id
        +str stripe_subscription_id
        +datetime created_at
        +datetime updated_at
    }
    class User {
        +UUID id
        +str email
        +str full_name
        +str hashed_password
        +UserRole role  «legacy»
        +str locale
        +bool is_active
        +bool mfa_enabled
        +str mfa_secret
        +datetime mfa_enrolled_at
        +UUID last_active_org_id  «FK»
        +UUID team_id  «FK»
        +datetime created_at
        +datetime updated_at
    }
    class OrgMembership {
        +UUID user_id  «PK,FK»
        +UUID organization_id  «PK,FK»
        +UserRole role
        +datetime created_at
    }
    class OrgInvite {
        +UUID id
        +UUID organization_id  «FK»
        +str email
        +UserRole role
        +str token  «unique»
        +datetime expires_at
        +UUID created_by_user_id  «FK»
        +datetime accepted_at
        +datetime created_at
    }
    class PasswordResetToken {
        +UUID id
        +UUID user_id  «FK»
        +str token  «unique»
        +datetime expires_at
        +datetime used_at
        +datetime created_at
    }
    class MfaBackupCode {
        +UUID id
        +UUID user_id  «FK»
        +str code_hash
        +datetime used_at
        +datetime created_at
    }
    class Team {
        +UUID id
        +UUID organization_id  «FK»
        +str name
        +str slug
        +datetime deleted_at
        +datetime created_at
        +datetime updated_at
    }

    Organization "1" *-- "0..*" OrgMembership : has
    User "1" *-- "0..*" OrgMembership : has
    Organization "1" --> "0..*" OrgInvite : invites
    User "0..1" --> "0..*" OrgInvite : created
    User "1" --> "0..*" PasswordResetToken : requests
    User "1" --> "0..*" MfaBackupCode : owns
    Organization "1" --> "0..*" Team : groups
    Team "0..1" --> "0..*" User : members
    Organization "0..1" <-- "0..*" User : last_active_org
```

> `OrgMembership` is the M:N junction (composite PK `user_id + organization_id`) — the same
> person can be `admin` in one org and `sales_agent` in another. `User.role` is the legacy
> single-tenant column kept until every call-site reads `OrgMembership.role` (ADR-013).

---

## 2. Class — CRM Core

```mermaid
classDiagram
    class SoftDeleteMixin {
        <<mixin>>
        +datetime deleted_at
    }
    class Lead {
        +UUID id
        +UUID organization_id  «FK»
        +str first_name
        +str last_name
        +str email
        +str phone
        +str company
        +str industry
        +str country
        +int company_size
        +float budget
        +str source
        +str notes
        +LeadStage stage
        +UUID team_id  «FK»
        +int ai_score
        +str ai_priority
        +str ai_next_action
        +float ai_conversion_probability
        +str ai_risk_analysis
        +datetime ai_scored_at
        +UUID owner_id  «FK»
        +datetime created_at
        +datetime updated_at
    }
    class Customer {
        +UUID id
        +UUID organization_id  «FK»
        +str first_name
        +str last_name
        +str email
        +str phone
        +str company
        +str industry
        +str country
        +str address
        +str website
        +str notes
        +str ai_summary
        +datetime ai_summary_updated_at
        +UUID owner_id  «FK»
        +datetime created_at
        +datetime updated_at
    }
    class Deal {
        +UUID id
        +UUID organization_id  «FK»
        +str title
        +float value
        +Currency currency
        +DealStage stage
        +int probability
        +date expected_close_date
        +str notes
        +UUID team_id  «FK»
        +int sort_index
        +int version  «optimistic lock»
        +UUID customer_id  «FK»
        +UUID owner_id  «FK»
        +datetime created_at
        +datetime updated_at
    }
    class Task {
        +UUID id
        +UUID organization_id  «FK»
        +str title
        +str description
        +TaskStatus status
        +TaskPriority priority
        +date due_date
        +UUID assignee_id  «FK»
        +UUID customer_id  «FK»
        +UUID deal_id  «FK»
        +UUID lead_id  «FK»
        +datetime created_at
        +datetime updated_at
    }
    class Pipeline {
        +UUID id
        +UUID organization_id  «FK»
        +PipelineKind kind
        +str name
        +str slug
        +bool is_default
        +datetime created_at
        +datetime updated_at
    }
    class PipelineStage {
        +UUID id
        +UUID pipeline_id  «FK»
        +str name
        +str slug
        +int position
        +int probability
        +bool is_won
        +bool is_lost
        +datetime created_at
        +datetime updated_at
    }

    SoftDeleteMixin <|-- Lead
    SoftDeleteMixin <|-- Customer
    SoftDeleteMixin <|-- Deal
    SoftDeleteMixin <|-- Task
    SoftDeleteMixin <|-- Pipeline
    SoftDeleteMixin <|-- PipelineStage

    Customer "0..1" --> "0..*" Deal : has
    Pipeline "1" *-- "1..*" PipelineStage : columns
    Customer "0..1" --> "0..*" Task : about
    Deal "0..1" --> "0..*" Task : about
    Lead "0..1" --> "0..*" Task : about
```

> All six are tenant-scoped via `organization_id` and soft-deletable (trash bin).
> `Pipeline`/`PipelineStage` are the customer-defined funnels that will eventually replace
> the hardcoded `LeadStage`/`DealStage` enums (kept as a denormalised cache during migration).

---

## 3. Class — Collaboration & Timeline

```mermaid
classDiagram
    class SoftDeleteMixin {
        <<mixin>>
        +datetime deleted_at
    }
    class Note {
        +UUID id
        +UUID organization_id  «FK»
        +UUID author_user_id  «FK»
        +str entity_type  «poly»
        +UUID entity_id  «poly»
        +str body  «markdown»
        +datetime created_at
        +datetime updated_at
    }
    class Activity {
        +UUID id
        +UUID organization_id  «FK»
        +UUID actor_user_id  «FK»
        +str entity_type  «poly»
        +UUID entity_id  «poly»
        +str type
        +str content
        +str metadata_json
        +datetime created_at
    }
    class FileAttachment {
        +UUID id
        +UUID organization_id  «FK»
        +UUID uploader_user_id  «FK»
        +str entity_type  «poly»
        +UUID entity_id  «poly»
        +str filename
        +str content_type
        +int size_bytes
        +str sha256
        +str storage_key  «S3»
        +datetime created_at
    }
    class Notification {
        +UUID id
        +UUID organization_id  «FK»
        +UUID user_id  «FK recipient»
        +UUID actor_user_id  «FK»
        +str type
        +str title
        +str body
        +str link_url
        +str metadata_json
        +datetime read_at
        +datetime created_at
    }

    SoftDeleteMixin <|-- Note
    SoftDeleteMixin <|-- FileAttachment
```

> `Note`, `Activity` and `FileAttachment` are **polymorphic** by `(entity_type, entity_id)` —
> they attach to a `Lead`, `Customer` or `Deal` (and any future `Quote`/`Contract`) with **no
> DB-level FK**, so adding a new host entity needs no migration. `Activity` is append-only
> (user-facing timeline); `Notification` is a per-user inbox (not soft-deletable).

---

## 4. Class — Eventing, Integration & Audit

```mermaid
classDiagram
    class AuditLog {
        +UUID id
        +UUID organization_id  «FK, nullable»
        +UUID actor_id  «FK»
        +str action
        +str entity_type
        +str entity_id
        +str metadata_json
        +datetime created_at
    }
    class OutboxEvent {
        +UUID id
        +UUID organization_id  «FK, nullable»
        +str event_type
        +str payload  «json»
        +datetime occurred_at
        +datetime processed_at
        +int attempt_count
        +str last_error
    }
    class WebhookEndpoint {
        +UUID id
        +UUID organization_id  «FK»
        +str url
        +str secret  «shown once»
        +str description
        +str enabled_events  «json, default star»
        +datetime paused_at
        +int consecutive_failures
        +datetime last_success_at
        +datetime last_failure_at
        +UUID created_by_user_id  «FK»
        +datetime created_at
    }
    class WebhookDelivery {
        +UUID id
        +UUID endpoint_id  «FK»
        +UUID event_id  «soft ptr»
        +str event_type
        +int attempt
        +str status
        +int response_code
        +str response_body_excerpt
        +str error
        +int latency_ms
        +datetime scheduled_for
        +datetime finished_at
    }
    class StripeEvent {
        +str id  «PK, stripe evt»
        +str type
        +datetime received_at
        +datetime processed_at
        +str payload
    }

    WebhookEndpoint "1" *-- "0..*" WebhookDelivery : attempts
```

> `OutboxEvent`, `WebhookEndpoint/Delivery` are **not** RLS'd — the worker drains across all
> tenants in one pass; admin reads filter by `organization_id` explicitly. `StripeEvent` is the
> idempotency log so a re-delivered Stripe webhook never double-applies (ADR-011).

---

## 5. Enumerations

```mermaid
classDiagram
    class UserRole {
        <<enumeration>>
        admin
        manager
        sales_agent
        support_agent
        client
    }
    class LeadStage {
        <<enumeration>>
        new
        contacted
        qualified
        proposal_sent
        negotiation
        won
        lost
    }
    class DealStage {
        <<enumeration>>
        new
        qualified
        proposal_sent
        negotiation
        won
        lost
    }
    class Currency {
        <<enumeration>>
        EUR
        CHF
        USD
        GBP
    }
    class TaskStatus {
        <<enumeration>>
        todo
        in_progress
        done
    }
    class TaskPriority {
        <<enumeration>>
        low
        medium
        high
    }
    class Plan {
        <<enumeration>>
        free
        standard
        premium
    }
    class BillingCycle {
        <<enumeration>>
        monthly
        yearly
    }
    class PipelineKind {
        <<enumeration>>
        lead
        deal
    }
    class EventType {
        <<enumeration>>
        lead.created
        lead.stage_changed
        deal.created
        deal.stage_changed
        deal.won
        deal.lost
    }
```

> `Activity.type` and `Notification.type` are string slugs whose vocabularies live in the API
> layer (`app.activities.ActivityType`, `app.notifications.NotificationType`) so adding a new
> kind needs no migration. `EventType` is the outbox vocabulary (`app.events`).

---

## 6. Entity-Relationship map (all tables)

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ ORG_MEMBERSHIPS : ""
    USERS ||--o{ ORG_MEMBERSHIPS : ""
    ORGANIZATIONS ||--o{ ORG_INVITES : invites
    USERS |o--o{ ORG_INVITES : created
    USERS ||--o{ PASSWORD_RESET_TOKENS : requests
    USERS ||--o{ MFA_BACKUP_CODES : owns
    ORGANIZATIONS ||--o{ TEAMS : groups
    TEAMS |o--o{ USERS : members
    ORGANIZATIONS |o--o{ USERS : last_active

    ORGANIZATIONS ||--o{ LEADS : scopes
    ORGANIZATIONS ||--o{ CUSTOMERS : scopes
    ORGANIZATIONS ||--o{ DEALS : scopes
    ORGANIZATIONS ||--o{ TASKS : scopes
    ORGANIZATIONS ||--o{ PIPELINES : scopes
    PIPELINES ||--o{ PIPELINE_STAGES : columns
    USERS |o--o{ LEADS : owns
    USERS |o--o{ DEALS : owns
    USERS |o--o{ CUSTOMERS : owns
    USERS |o--o{ TASKS : assigned
    TEAMS |o--o{ LEADS : scopes
    TEAMS |o--o{ DEALS : scopes
    CUSTOMERS |o--o{ DEALS : has
    CUSTOMERS |o--o{ TASKS : about
    DEALS |o--o{ TASKS : about
    LEADS |o--o{ TASKS : about

    ORGANIZATIONS ||--o{ NOTES : scopes
    ORGANIZATIONS ||--o{ ACTIVITIES : scopes
    ORGANIZATIONS ||--o{ FILE_ATTACHMENTS : scopes
    ORGANIZATIONS ||--o{ NOTIFICATIONS : scopes
    USERS |o--o{ NOTIFICATIONS : receives
    USERS |o--o{ ACTIVITIES : acts
    USERS |o--o{ NOTES : authors

    ORGANIZATIONS |o--o{ AUDIT_LOGS : "may scope"
    USERS |o--o{ AUDIT_LOGS : acts
    ORGANIZATIONS |o--o{ OUTBOX_EVENTS : "may scope"
    ORGANIZATIONS ||--o{ WEBHOOK_ENDPOINTS : owns
    WEBHOOK_ENDPOINTS ||--o{ WEBHOOK_DELIVERIES : attempts

    NOTES }o..|| LEADS : "poly entity"
    ACTIVITIES }o..|| LEADS : "poly entity"
    FILE_ATTACHMENTS }o..|| LEADS : "poly entity"

    ORGANIZATIONS ||--o{ COMPANIES : scopes
    COMPANIES |o--o{ LEADS : links
    COMPANIES |o--o{ CUSTOMERS : links
    ORGANIZATIONS ||--o{ PRODUCTS : scopes
    ORGANIZATIONS ||--o{ DOCUMENT_TEMPLATES : owns
    ORGANIZATIONS ||--o{ CUSTOM_FIELD_DEFINITIONS : defines
    ORGANIZATIONS ||--o{ TAGS : owns
    TAGS ||--o{ ENTITY_TAGS : applied
    ORGANIZATIONS ||--o{ SAVED_SEGMENTS : owns
    ORGANIZATIONS ||--o{ WEB_FORMS : owns
    ORGANIZATIONS ||--o{ IMPORT_JOBS : runs

    ORGANIZATIONS ||--o{ QUOTES : scopes
    QUOTES ||--o{ QUOTE_LINE_ITEMS : "line items"
    DEALS |o--o{ QUOTES : has
    CUSTOMERS |o--o{ QUOTES : for
    ORGANIZATIONS ||--o{ CONTRACTS : scopes
    QUOTES |o--o{ CONTRACTS : "converted to"
    CONTRACTS |o--o{ DOCUMENT_TEMPLATES : "rendered from"
    ORGANIZATIONS ||--o{ SIGNATURE_REQUESTS : scopes
    QUOTES |o--o{ SIGNATURE_REQUESTS : "e-sign"
    CONTRACTS |o--o{ SIGNATURE_REQUESTS : "e-sign"

    ORGANIZATIONS ||--o{ WHATSAPP_ACCOUNTS : owns
    WHATSAPP_ACCOUNTS ||--o{ CONVERSATIONS : threads
    CONVERSATIONS ||--o{ MESSAGES : contains
    LEADS |o--o{ CONVERSATIONS : "linked to"
    CUSTOMERS |o--o{ CONVERSATIONS : "linked to"
    USERS |o--o{ CONVERSATIONS : assignee

    ORGANIZATIONS ||--o{ API_KEYS : owns
    ORGANIZATIONS ||--o{ AUTOMATION_RULES : owns
    AUTOMATION_RULES ||--o{ AUTOMATION_RUNS : logs
    ORGANIZATIONS ||--o{ SALES_GOALS : scopes
    USERS |o--o{ SALES_GOALS : "owner/team"

    ORGANIZATIONS ||--o{ LLM_USAGE : scopes
    USERS |o--o{ LLM_USAGE : "by (nullable)"
    ORGANIZATIONS ||--o{ STRIPE_EVENTS : "billing log"
    USERS ||--o{ EMAIL_VERIFICATION_TOKENS : verifies
    FX_RATES }o..o{ ORGANIZATIONS : "global ref (no FK)"
```

> The 44 tenant + reference tables: `organizations · org_memberships · org_invites · users · teams ·
> password_reset_tokens · email_verification_tokens · mfa_backup_codes · leads · customers · companies ·
> deals · tasks · pipelines · pipeline_stages · products · quotes · quote_line_items · contracts ·
> signature_requests · document_templates · custom_field_definitions · tags · entity_tags · saved_segments ·
> web_forms · import_jobs · notes · activities · file_attachments · notifications · audit_logs ·
> outbox_events · webhook_endpoints · webhook_deliveries · api_keys · automation_rules · automation_runs ·
> sales_goals · whatsapp_accounts · conversations · messages · stripe_events · fx_rates · llm_usage`.
> `fx_rates` is **global reference data** (no `organization_id`, no RLS); everything else is tenant-scoped.

> Cardinality legend: `||` = exactly one, `|o` = zero-or-one (nullable FK / `SET NULL`),
> `o{` = zero-or-many. Polymorphic links (`}o..||`) are shown against `LEADS` for illustration —
> the same `(entity_type, entity_id)` pair also targets `CUSTOMERS` and `DEALS` with no real FK.

---

## 7. Component / architecture diagram

```mermaid
flowchart LR
    Browser["Browser / SPA"]

    subgraph FE["Next.js 15 frontend :3030"]
        Next["App Router + i18n middleware<br/>(7 locales) + cookie/CSRF client"]
    end

    subgraph BE["FastAPI backend :8001"]
        API["API routers /api/*"]
        Deps["deps: auth + RLS GUC + role guards"]
        Svc["services: llm · ai_scoring · ai_assistant · stripe"]
        Prod["events: record_event (outbox producer)"]
    end

    subgraph WK["Arq worker"]
        Jobs["score_lead · drain_outbox (5s) · deliver_webhook"]
    end

    subgraph DATA["Data stores"]
        PG[("PostgreSQL 16 + pgvector<br/>RLS · outbox_events")]
        REDIS[("Redis 7<br/>rate-limit · sessions · refresh · arq queue")]
        MINIO[("MinIO / S3<br/>file attachments")]
    end

    subgraph EXT["External services"]
        LLM["Anthropic Claude / Ollama"]
        STRIPE["Stripe"]
        HOOKS["Customer webhook receivers"]
    end

    Browser --> Next -->|"cookie + X-CSRF-Token"| API
    API --> Deps --> PG
    API --> Svc
    Svc --> LLM
    Svc --> STRIPE
    API --> REDIS
    API --> MINIO
    API -->|"enqueue"| REDIS
    Prod -->|"outbox row (same tx)"| PG
    REDIS -->|"dequeue"| Jobs
    Jobs --> PG
    Jobs --> LLM
    Jobs -->|"POST signed (HMAC)"| HOOKS
    STRIPE -->|"webhook (signed)"| API
```

---

## 8. Deployment diagram (docker-compose)

```mermaid
flowchart TB
    subgraph host["Docker Compose host"]
        fe["frontend<br/>npm run dev<br/>:3030 → 3000"]
        be["backend<br/>alembic upgrade head && uvicorn<br/>:8001 → 8000"]
        wk["worker<br/>arq app.worker.settings.WorkerSettings"]
        db[("db — pgvector/pgvector:pg16<br/>:5433 → 5432")]
        rd[("redis:7-alpine<br/>:6380 → 6379")]
        mn[("minio<br/>:9000 API · :9001 console")]
        ol["ollama<br/>:11434"]
    end

    fe -->|"depends_on"| be
    be -->|"healthcheck"| db
    be --> rd
    be --> mn
    be --> ol
    wk --> db
    wk --> rd
    wk --> mn
    wk --> ol
```

> Single-replica note: the backend runs `alembic upgrade head` on every start. For multi-replica
> deploys, move migrations into a one-shot release job so replicas don't race (ADR-012).

---

## 9. Use-case diagram (actors & roles)

```mermaid
flowchart LR
    visitor(("Visitor"))
    agent(("Sales / Support Agent"))
    manager(("Manager"))
    admin(("Org Admin"))
    stripe(("Stripe"))
    receiver(("Webhook receiver"))

    visitor --> UC_register["Register / Login / MFA / Reset password"]
    visitor --> UC_pricing["View public pricing"]

    agent --> UC_crud["Manage leads / customers / deals / tasks"]
    agent --> UC_kanban["Pipeline kanban (drag-drop)"]
    agent --> UC_ai["AI lead scoring + assistant chat"]
    agent --> UC_notes["Notes · attachments · activity timeline"]
    agent --> UC_notif["Notifications inbox"]

    manager --> UC_crud
    manager --> UC_reports["Reports & dashboard"]
    manager --> UC_audit["View audit log"]
    manager --> UC_pipelines["Configure pipelines & teams"]

    admin --> UC_org["Manage org · invites · seats"]
    admin --> UC_billing["Billing & plan (Stripe portal)"]
    admin --> UC_webhooks["Manage webhook endpoints"]
    admin --> UC_trash["Empty trash / hard delete"]

    UC_billing -.-> stripe
    UC_webhooks -.-> receiver
```

> Roles are hierarchical in practice: `manager` ⊇ `sales_agent` abilities, `admin` ⊇ `manager`.
> Destructive ops (hard delete, empty trash) and webhook/billing management are admin/manager-gated.

---

## 10. Sequence — Authentication + refresh rotation

```mermaid
sequenceDiagram
    actor U as User
    participant FE as Frontend
    participant API as FastAPI
    participant R as Redis
    participant DB as Postgres

    U->>FE: email + password (+ TOTP if MFA on)
    FE->>API: POST /api/auth/login
    API->>DB: verify_password (constant-time, even on unknown email)
    API->>R: create session + store refresh token
    API-->>FE: Set-Cookie access(15m) + refresh(30d) + csrf
    Note over FE,API: subsequent calls send cookie + X-CSRF-Token

    FE->>API: GET /api/leads
    API->>DB: SET app.current_org_id (RLS GUC); SELECT scoped
    API-->>FE: 200 leads (own org only)

    Note over FE: access token expires
    FE->>API: POST /api/auth/refresh (refresh cookie)
    API->>R: validate + ROTATE refresh token
    alt reused (already-rotated) token
        API->>R: revoke ALL user sessions (steal signal)
        API-->>FE: 401 reuse_detected
    else valid
        API-->>FE: Set-Cookie new access + rotated refresh
    end
```

---

## 11. Sequence — Async AI lead scoring

```mermaid
sequenceDiagram
    actor U as User
    participant API as FastAPI
    participant R as Redis (arq queue)
    participant W as Worker
    participant LLM as Claude / Ollama
    participant DB as Postgres

    U->>API: POST /api/leads/{id}/score-async
    API->>R: enqueue score_lead(lead_id, org_id)
    API-->>U: 202 Accepted (job id)
    R->>W: dispatch score_lead
    W->>DB: SET app.current_org_id; load lead
    W->>LLM: score lead (heuristic fallback if down)
    W->>DB: UPDATE ai_* + Activity(ai_scored) + AuditLog; commit
    W-->>R: JobResult (status, score)
    U->>API: poll job status
    API->>R: read JobResult
    API-->>U: scored (score, priority, next action)
```

---

## 12. Sequence — Outbox → outgoing webhook

```mermaid
sequenceDiagram
    participant API as FastAPI
    participant DB as Postgres
    participant W as Worker (cron 5s)
    participant R as Redis (arq)
    participant EP as Webhook receiver

    API->>DB: domain mutation + INSERT outbox_events (same tx)
    loop every 5 seconds
        W->>DB: claim rows FOR UPDATE SKIP LOCKED (backoff 2^attempt)
        W->>W: dispatch_event → in-process subscribers + fanout
        W->>R: enqueue deliver_webhook per matching endpoint
        W->>DB: mark processed_at (or attempt_count++, last_error)
    end
    R->>W: dispatch deliver_webhook
    W->>EP: POST body + X-CRM-Signature (HMAC-SHA256)
    alt 2xx
        W->>DB: WebhookDelivery status=success; consecutive_failures=0
    else non-2xx / timeout
        W->>DB: WebhookDelivery status=failed; consecutive_failures++
        W->>R: arq Retry(defer=2^attempt) up to 8 tries
        Note over W,DB: consecutive_failures ≥ 10 → auto-pause endpoint
    end
```

---

## 13. Sequence — Stripe billing

```mermaid
sequenceDiagram
    actor U as Admin
    participant FE as Frontend
    participant API as FastAPI
    participant S as Stripe
    participant DB as Postgres

    U->>FE: pick Standard / Premium plan
    FE->>API: POST /api/billing/checkout
    API->>S: create Checkout Session (metadata: organization_id)
    API-->>FE: redirect to Stripe Checkout
    U->>S: enter payment details
    S->>API: webhook checkout.session.completed (signed)
    API->>DB: INSERT stripe_events (dedupe by event id)
    alt already processed
        API-->>S: 200 (no-op)
    else first time
        API->>DB: Organization.plan / stripe_* updated + AuditLog
        API-->>S: 200
    end
    Note over U,S: later — Customer Portal handles cancel / card update,<br/>subscription.deleted webhook downgrades the org
```

---

## 14. State — Deal pipeline & Webhook endpoint

**Deal stage lifecycle** (`DealStage`; a deal can be marked `lost` from any open stage):

```mermaid
stateDiagram-v2
    [*] --> new
    new --> qualified
    qualified --> proposal_sent
    proposal_sent --> negotiation
    negotiation --> won
    new --> lost
    qualified --> lost
    proposal_sent --> lost
    negotiation --> lost
    won --> [*]
    lost --> [*]
```

**Webhook endpoint health** (auto-pause after repeated failures):

```mermaid
stateDiagram-v2
    [*] --> active
    active --> active : delivery 2xx (reset failures)
    active --> paused : consecutive_failures ≥ 10
    paused --> active : admin PATCH unpause (resets counter)
    active --> [*] : deleted
    paused --> [*] : deleted
```

---

## 15. Class — Quotes, Contracts, Products & Documents

```mermaid
classDiagram
    class Product {
        +UUID id
        +UUID organization_id  «FK»
        +str name
        +str sku
        +ProductType type
        +Decimal price
        +str currency
        +str unit
        +bool active
        +UUID owner_id  «FK»
        +int version
    }
    class Quote {
        +UUID id
        +UUID organization_id  «FK»
        +UUID deal_id  «FK»
        +UUID customer_id  «FK»
        +str number
        +int version
        +QuoteStatus status
        +str title
        +Currency currency
        +date valid_until
        +Decimal subtotal
        +Decimal tax_rate
        +Decimal tax_amount
        +Decimal total
        +UUID superseded_by  «FK»
        +datetime sent_at
        +datetime accepted_at
        +datetime declined_at
    }
    class QuoteLineItem {
        +UUID id
        +UUID organization_id  «FK»
        +UUID quote_id  «FK»
        +str description
        +Decimal quantity
        +Decimal unit_price
        +Decimal line_total
        +int sort_index
    }
    class Contract {
        +UUID id
        +UUID organization_id  «FK»
        +UUID quote_id  «FK»
        +UUID deal_id  «FK»
        +UUID customer_id  «FK»
        +str number
        +int version
        +ContractStatus status
        +str title
        +Currency currency
        +Decimal value
        +date effective_date
        +date end_date
        +bool auto_renew
        +int renewal_term_months
        +str body
        +UUID applied_template_id  «FK»
        +datetime signed_at
        +datetime activated_at
        +datetime terminated_at
    }
    class SignatureRequest {
        +UUID id
        +UUID organization_id  «FK»
        +UUID quote_id  «FK»
        +UUID contract_id  «FK»
        +str provider
        +SignatureStatus status
        +str signer_name
        +str signer_email
        +str sign_token
        +UUID document_attachment_id  «FK»
        +str signed_document_key
        +datetime signed_at
        +datetime declined_at
    }
    class DocumentTemplate {
        +UUID id
        +UUID organization_id  «FK»
        +DocumentType doc_type
        +str name
        +str body
        +bool is_default
        +UUID created_by_user_id  «FK»
    }
    Quote "1" --> "*" QuoteLineItem : line_items
    Quote ..> Contract : "converted to"
    DocumentTemplate ..> Contract : renders
    Quote ..> SignatureRequest
    Contract ..> SignatureRequest
    Product ..> QuoteLineItem : "pre-fills"
```

---

## 16. Class — Omnichannel, Public API & Automation

```mermaid
classDiagram
    class WhatsAppAccount {
        +UUID id
        +UUID organization_id  «FK»
        +str phone_number_id
        +str waba_id
        +str display_phone_number
        +str access_token  «encrypted»
        +WhatsAppAccountStatus status
    }
    class Conversation {
        +UUID id
        +UUID organization_id  «FK»
        +UUID account_id  «FK»
        +ConversationChannel channel
        +str contact_wa_id
        +str contact_name
        +UUID lead_id  «FK»
        +UUID customer_id  «FK»
        +ConversationStatus status
        +datetime last_message_at
        +int unread_count
        +UUID assignee_id  «FK»
    }
    class Message {
        +UUID id
        +UUID organization_id  «FK»
        +UUID conversation_id  «FK»
        +str wa_message_id
        +MessageDirection direction
        +MessageType type
        +str body
        +str media_storage_key
        +MessageStatus status
        +UUID sender_user_id  «FK»
        +datetime timestamp
    }
    class ApiKey {
        +UUID id
        +UUID organization_id  «FK»
        +str name
        +str hashed_key  «sha256»
        +str display_prefix
        +str scopes
        +datetime last_used_at
        +datetime expires_at
        +datetime revoked_at
    }
    class WebForm {
        +UUID id
        +UUID organization_id  «FK»
        +str name
        +str token
        +str default_source
        +str redirect_url
        +bool active
        +int submission_count
    }
    class AutomationRule {
        +UUID id
        +UUID organization_id  «FK»
        +str name
        +bool enabled
        +AutomationTrigger trigger
        +AutomationAction action
        +str action_config  «JSON»
        +int run_count
        +datetime last_run_at
    }
    class AutomationRun {
        +UUID id
        +UUID rule_id  «FK»
        +UUID organization_id  «FK»
        +str idempotency_key
        +str status
        +str entity_type
        +UUID entity_id
        +str detail
    }
    WhatsAppAccount "1" --> "*" Conversation
    Conversation "1" --> "*" Message
    AutomationRule "1" --> "*" AutomationRun
```

---

## 17. Class — Segmentation, Custom Fields, Imports, FX & Usage

```mermaid
classDiagram
    class Company {
        +UUID id
        +UUID organization_id  «FK»
        +str name
        +str industry
        +str website
        +str email
        +str country
        +int size
        +str avatar_key
        +dict custom_fields
        +UUID owner_id  «FK»
        +int version
    }
    class CustomFieldDefinition {
        +UUID id
        +UUID organization_id  «FK»
        +str entity_type
        +str key
        +str label
        +CustomFieldType field_type
        +list options
        +bool required
        +int position
    }
    class Tag {
        +UUID id
        +UUID organization_id  «FK»
        +str name
        +str color
    }
    class EntityTag {
        +UUID id
        +UUID organization_id  «FK»
        +UUID tag_id  «FK»
        +str entity_type
        +UUID entity_id
    }
    class SavedSegment {
        +UUID id
        +UUID organization_id  «FK»
        +str entity_type
        +str name
        +dict filters
        +UUID created_by_id  «FK»
    }
    class ImportJob {
        +UUID id
        +UUID organization_id  «FK»
        +ImportEntityType entity_type
        +ImportMode mode
        +ImportStatus status
        +str filename
        +str storage_key
        +int total_rows
        +int created_count
        +int updated_count
        +int error_count
        +list error_report
        +datetime finished_at
    }
    class SalesGoal {
        +UUID id
        +UUID organization_id  «FK»
        +UUID owner_id  «FK»
        +UUID team_id  «FK»
        +GoalPeriod period
        +date period_start
        +GoalMetric metric
        +Decimal target
    }
    class FxRate {
        +str base  «PK»
        +str quote  «PK»
        +Decimal rate
        +date as_of
        +str source
        +datetime fetched_at
    }
    note for FxRate "Global reference data — no organization_id, no RLS."
    class LlmUsage {
        +UUID id
        +UUID organization_id  «FK»
        +UUID user_id  «FK»
        +str use_case
        +str provider
        +str model
        +int input_tokens
        +int output_tokens
        +datetime created_at
    }
    Tag "1" --> "*" EntityTag
```

> ER cardinality legend (used in §6): `||` exactly one · `|o` zero-or-one · `o{` zero-or-many ·
> `}o..||` polymorphic (no real FK).

---

*Generated by reverse-engineering the live code. If you change `models.py`, the API surface,
the worker, or `docker-compose.yml`, update the affected diagram here in the same PR.*
*Last reconciled against the schema: 2026-06-15 (44 tables).*

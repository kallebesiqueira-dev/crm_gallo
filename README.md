# CRM Gallo

AI-powered multilingual CRM platform. Next.js + FastAPI + PostgreSQL/pgvector + Anthropic Claude / Ollama.

## What's in this scaffold

**Working today:**
- Auth (register / login / logout / JWT) with first user promoted to admin (race-safe via Postgres advisory lock)
- Per-resource ownership: any authenticated user reads; only the owner or admin/manager mutates
- Role-based gates on destructive operations (hard delete, empty trash)
- Login rate limiting (default 5/min/IP) via SlowAPI
- 7-language UI: English, Deutsch, Français, Italiano, Rumantsch, Português, Español
- Light/dark mode
- **Pricing & billing**: Free (2 seats) / Standard / Premium tiers in EUR, monthly+annual (-20%) cycles, public `/pricing` page, internal `/billing` page with plan card and Stripe Customer Portal
- **Stripe integration**: Checkout, Customer Portal, signed webhook with idempotency; Free works without keys, paid plans activate when Stripe is configured
- **Premium 14-day trial** via Stripe `trial_period_days`
- Modern login + register pages with eye-toggle password input and strength meter
- Dashboard with colorful sparkline + stage chart (recharts)
- Reports with area, bar, donut and funnel charts (recharts + curated palette)
- Leads, Customers, Deals, Tasks: list, search, create, detail, edit, soft-delete
- Pipeline kanban with drag-and-drop (drop on column or card)
- AI lead scoring + AI customer summary via Claude or Ollama (with heuristic fallback)
- AI sales assistant (chat) powered by the configured LLM
- Trash bin with restore and admin-only hard delete / empty
- Audit log writes for every mutation (read via DB; UI surface in roadmap)
- Plan badge + contextual banners (trial ending, seat-limit reached, subscription canceled) in app header
- Structured JSON logging with per-request `X-Request-ID`
- Themed confirm dialogs (no more native `confirm()` / `alert()`)
- `/health` (liveness) and `/ready` (DB ping) probes

**Not yet built (future phases):**
- Multi-tenant Organizations (next milestone — see Roadmap)
- Documents/RAG, Communication hub, Automation builder
- MFA, password reset email flow, refresh tokens, session revocation
- Alembic migrations (we currently `create_all` on startup for MVP convenience)
- Audit log UI

## Stack

| Layer    | Choice                                                       |
| -------- | ------------------------------------------------------------ |
| Frontend | Next.js 15 + React 19 + TypeScript + Tailwind + shadcn-style UI |
| i18n     | next-intl (7 locales, URL-prefixed)                          |
| Backend  | FastAPI (async) + SQLAlchemy 2.0 + Pydantic v2 + SlowAPI     |
| Logging  | structlog (JSON-ready) + request-id middleware               |
| Database | PostgreSQL 16 + pgvector (for future RAG)                    |
| Cache    | Redis 7                                                      |
| AI       | Anthropic Claude (Sonnet 4.6 default) or Ollama (local)      |
| Deploy   | Docker Compose (dev); Vercel + container host (prod)         |

## Quick start

```bash
cp .env.example .env
# Edit .env — set JWT_SECRET (>=32 chars) and, optionally, ANTHROPIC_API_KEY
docker compose up --build
```

Then open:
- Frontend: http://localhost:3030
- Backend docs: http://localhost:8001/docs
- Health: http://localhost:8001/health
- Readiness (DB ping): http://localhost:8001/ready

First account you register becomes admin.

## Running without Docker

**Backend:**
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate         # PowerShell on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## Billing / Stripe setup (optional for dev)

The Free plan works **without any Stripe configuration**. Standard and Premium
checkout require Stripe keys.

**Local dev:**

```bash
# 1. Install Stripe CLI: https://docs.stripe.com/stripe-cli
# 2. Create 4 Prices in your Stripe Dashboard (or via CLI):
#    Standard monthly / yearly, Premium monthly / yearly
# 3. Drop these into .env:
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_PRICE_STANDARD_MONTHLY=price_...
STRIPE_PRICE_STANDARD_YEARLY=price_...
STRIPE_PRICE_PREMIUM_MONTHLY=price_...
STRIPE_PRICE_PREMIUM_YEARLY=price_...

# 4. Forward webhook events to local backend (gives you STRIPE_WEBHOOK_SECRET):
stripe listen --forward-to http://localhost:8001/api/billing/webhook
# Copy the printed `whsec_...` into .env as STRIPE_WEBHOOK_SECRET
```

**Production:** rotate via your secrets manager, point the live webhook to
`https://crm.<your-domain>/api/billing/webhook`, enable Stripe Tax for EU VAT.

Pricing constants live in [backend/app/billing/catalog.py](backend/app/billing/catalog.py) — edit there to change copy and the display price (the source of truth for what gets charged remains the Stripe Price IDs).

## Security model

| Layer | Behavior |
| ----- | -------- |
| Startup | Refuses to boot in production with default/short `JWT_SECRET`. Logs a warning in dev. |
| Auth | bcrypt password hash; JWT (HS256) with `iat` + `exp`; symmetric same-error response for unknown email vs bad password (no enumeration). |
| Sessions | Stateless JWT, 60-min default expiry, client-side `isExpired()` pre-check. `/api/auth/logout` records the event for the audit trail. |
| Rate limit | 5/min/IP on `/api/auth/login` (configurable via `RATE_LIMIT_LOGIN_PER_MINUTE`). |
| CORS | Explicit allowlist; explicit methods (no wildcard); credentials enabled. |
| Ownership | `list`/`get` open to any authenticated user. `patch`/`delete` require `owner_id == user.id` OR role ∈ {admin, manager}. Tasks key off `assignee_id`. |
| RBAC | `/api/trash/{type}/{id}` (hard delete) requires admin or manager. `/api/trash/empty` requires admin. |
| Audit | Every mutation appends an `AuditLog` row in the same transaction (best-effort: a failure to audit never aborts the request). |
| Observability | Every response carries `X-Request-ID`. Structured logs include request id, method, path, status, duration_ms. |

## Hardening still required before production

- Tokens stored in `localStorage` — switch to httpOnly cookies + CSRF token
- `Base.metadata.create_all` on startup — replace with Alembic migrations
- MFA, password reset, refresh tokens, server-side revocation
- TLS termination + HSTS in front
- Audit log retention / export, anonymization for GDPR
- Multi-tenant Organizations (workspace isolation)

## Project layout

```
crm_gallo/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py            # FastAPI entry, CORS, request-id middleware, lifespan
│       ├── config.py          # Settings + runtime secret validation
│       ├── database.py        # Async SQLAlchemy session
│       ├── models.py          # User, Lead, Customer, Deal, Task, AuditLog + enums
│       ├── schemas.py         # Pydantic request/response models
│       ├── security.py        # Password hashing + JWT
│       ├── deps.py            # Auth + ownership + role guards
│       ├── rate_limit.py      # SlowAPI limiter (separate to avoid circular imports)
│       ├── logging_setup.py   # structlog configuration
│       ├── audit.py           # Audit log helper
│       ├── api/
│       │   ├── auth.py        # /register /login /logout /me + password change
│       │   ├── leads.py       # CRUD + AI scoring
│       │   ├── customers.py   # CRUD + AI summarization
│       │   ├── deals.py       # CRUD + kanban move
│       │   ├── tasks.py       # CRUD
│       │   ├── dashboard.py   # Stats
│       │   ├── assistant.py   # AI chat
│       │   └── trash.py       # Soft-delete bin + RBAC
│       └── services/
│           ├── llm.py         # Ollama/Anthropic abstraction + fallback
│           ├── ai_scoring.py  # Lead scoring with heuristic fallback
│           └── ai_assistant.py# Chat + customer summarization
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── next.config.ts
    ├── tailwind.config.ts
    ├── messages/               # en, de, fr, it, rm, pt, es
    └── src/
        ├── middleware.ts       # i18n locale routing
        ├── i18n/               # config + request handler
        ├── lib/                # api client + token storage
        ├── components/         # ui/, sidebar, theme, language switcher, confirm-dialog
        └── app/
            ├── layout.tsx
            ├── page.tsx        # → /<defaultLocale>/dashboard
            └── [locale]/
                ├── layout.tsx
                ├── login/      # public
                ├── register/   # public
                └── (app)/      # authenticated group, has sidebar
                    ├── dashboard/
                    ├── leads/  # + [id]/ + [id]/edit + new/
                    ├── customers/
                    ├── pipeline/
                    ├── tasks/
                    ├── calendar/
                    ├── reports/
                    ├── trash/
                    ├── assistant/
                    └── settings/
```

## Roadmap

**Phase 2 (next) — Multi-tenant Organizations**
- `Organization` model + `organization_id` on every domain table
- Workspace switcher in UI; invite flow
- Migrate ownership: ownership stays per-user inside an org; cross-org access denied

**Phase 3 — Auth hardening**
- MFA (TOTP) for admin/manager roles
- Password reset email flow
- Refresh tokens + server-side session revocation
- Replace `localStorage` token with httpOnly cookie + CSRF

**Phase 4 — RAG Knowledge Base**
- Document upload + chunking + pgvector embeddings
- AI assistant grounded on company knowledge, with citations

**Phase 5 — Communication + Tasks**
- Email integration (IMAP/Gmail/Outlook)
- Calendar sync, reminders
- Internal notes threaded to customer profiles

**Phase 6 — Automation + Analytics**
- Visual workflow builder
- Forecasting, channel attribution, lost-deal analysis
- Audit log UI

**Phase 7 — Production readiness**
- Alembic migrations + seed
- GDPR data export + erasure
- Per-tenant rate limiting, distributed rate limiter (Redis backend)
- CI/CD pipeline, staging env, k8s manifests

## License

CRM Gallo is licensed under the **GNU Affero General Public License v3.0 or later** (AGPL-3.0-or-later).

- Full license text: [LICENSE](LICENSE)
- Copyright notice: [NOTICE](NOTICE)
- Copyright © 2026 Kallebe Gallo

**What this means in practice:**
- You can use, modify, and self-host CRM Gallo freely.
- If you run a **modified version** as a network service (SaaS), you must publish your modifications under the same license.
- If you embed CRM Gallo in another product, that product must also be AGPL-3.0.
- A commercial dual-license is possible — contact the copyright holder if you need a non-AGPL license.

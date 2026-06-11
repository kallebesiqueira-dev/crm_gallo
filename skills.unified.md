# Gallo CRM — Single Source of Truth

> **One plan for every agent.** This file unifies the old `plan.md` (product) and
> `skills.md` (engineering) into a single living document. Read it first; update it
> when work changes state. When this lands, `plan.md` is removed and this file
> becomes `skills.md`.
> **Unified:** 2026-06-11.

---

## 0. Coordination protocol — READ FIRST (multiple agents share this repo)

- **Repo is PUBLIC** (`github.com/kallebesiqueira-dev/crm_gallo`). Never commit secrets; never re-paste a leaked value.
- **Isolation:** work from a fresh clone or a `git worktree` off `origin/main`. Commit ONLY your own files, squash-merge via PR. **Never `git checkout main` in a tree another agent shares**, and don't `git worktree remove --force` a tree that has another agent's `node_modules` junction inside it (the recursive delete follows the junction and wipes the real `node_modules`).
- **Alembic heads:** every new migration revises the *current* head. If two agents branch a migration off the same head you get **two heads** → prod `alembic upgrade head` fails. Whoever merges second runs `alembic merge -m "merge" <headA> <headB>`.
- **Shared hot files — announce before editing, expect conflicts:** `backend/app/models.py`, `backend/app/schemas.py`, `frontend/src/lib/api.ts`, `frontend/messages/*.json` (all 7), `frontend/src/components/sidebar.tsx`, and **this document**.
- **Deploy:** Railway does NOT auto-deploy on git push. After merging to `main`, ship with `railway redeploy -s <frontend|crm_gallo|worker> --from-source -y`. A `NEXT_PUBLIC_*` var only reaches the browser bundle if `frontend/Dockerfile` declares an `ARG`+`ENV` for it (build-arg, baked at build).

---

## 1. Product

> **Gallo CRM** — the CRM that makes sure no opportunity is forgotten.
> Setup in 30 min · learn in 15 · follow-up driven · AI-assisted · GDPR-ready.

**Why Europe:** fatigue with Salesforce/Dynamics/HubSpot/SAP. European SMBs want *"open it, use it, sell."* Differentiators: radical simplicity (no consultant), mandatory follow-up ("you forgot this client"), zero-consulting setup, **action-oriented dashboard** (not charts — *"Call João · deal X stalled 12 days"*), native GDPR as a selling point.

**Positioning:** *communication-first*, not WhatsApp-first. WhatsApp is mandatory in BR/ES/PT/IT; email dominates in DE/NL/UK/Nordics. Message: *sell through the channel your client prefers — email, WhatsApp, phone, or meeting.*

**Principles:** radical simplicity · no active deal without a defined next action · communication-first · **operational AI** (summarize, detect intent, suggest the next step, create the follow-up — not just a chat) · fast setup (<30 min, sector templates) · **action over dashboard** (answer "what do I do now to sell more?") · GDPR native from day 1.

**Guiding question for every new feature:** *Does this help the salesperson REMEMBER, PRIORITIZE, or EXECUTE the next commercial action?* If not → it probably doesn't belong now.

---

## 2. Current state — LIVE in production

The technical core is complete and in production (Railway). The gaps in §3 are product, not infrastructure.

- **Multi-tenant:** Organizations + Postgres RLS (ENABLE+FORCE+GUC, transaction-scoped via ContextVar), memberships, invites (create/accept/resend/prune), per-org seat enforcement, billing migrated to Org.
- **Auth:** JWT in httpOnly cookies + double-submit CSRF; refresh-token rotation + reuse-detection; MFA TOTP (mandatory for admin/manager, secret Fernet-encrypted at rest); password reset; sessions page; **Microsoft OAuth login** (existing accounts); Cloudflare Turnstile on register; constant-time login. (`/api/auth/login` exempt from CSRF — fixed the stale-cookie lockout.)
- **Leads / Customers / Companies:** full CRUD, cursor pagination, full-text search + `pg_trgm` fallback, AI scoring (leads) + AI summary (customers).
- **Deals/Opportunities:** kanban drag-drop, stages, optimistic locking (`If-Match`), FX-approx pipeline value.
- **Tasks · Calendar (internal) · Activity timeline · Notes · Notifications** (bell + page).
- **Quotes & Contracts:** full lifecycle quote→contract→e-signature→PDF (WeasyPrint in the worker); `Documents` list; merge-field templates. **Quote line items can be filled from the Products catalog.**
- **Products/Services catalog:** backend + list/new/edit pages + "add from catalog" in the quote form.
- **Imports/Exports:** CSV/XLSX, row validation, dedup, streaming export.
- **WhatsApp omnichannel:** Cloud API, webhook, inbox UI, conversations/messages, read receipts.
- **AI (one provider):** lead scoring, customer summary, assistant chat, and the public landing chatbot all call **one Groq** endpoint (`LLM_PROVIDER=openai_compat`, `openai/gpt-oss-120b`) via `app/services/llm.py`. No separate keys.
- **Billing:** Stripe LIVE (Swiss account), Free/Standard/Premium monthly+yearly, seats, 14-day trial, webhook = source of truth.
- **Public API + keys · Outgoing webhooks** (HMAC, outbox pattern, retry, auto-pause) · **Automations** (no-code trigger→condition→action) · **Reports + Performance** (analytics + sales goals) · **Audit log** (RLS-strict, UI).
- **Observability:** Prometheus, Grafana dashboard JSON, Sentry (FE+BE, EU), Arq DLQ + admin endpoint, alert rules; **PostHog** product analytics (EU).
- **i18n:** 7 locales (EN/PT/DE/FR/IT/RM/ES); CI audits key parity.
- **Onboarding (partial):** `GET /api/onboarding/checklist` + sector pipeline templates (`/api/onboarding/templates` ×7 + apply) — backend done; checklist widget + templates page on the frontend.
- **CI/CD (GitHub Actions):** backend (ruff/pytest/pip-audit/alembic), frontend (tsc/eslint/vitest), docker (Trivy gate), e2e (Playwright), security, db-backup.
- **Prod infra:** Railway (frontend / crm_gallo / worker / Postgres / Redis), **Cloudflare R2** (EU, GDPR) for file storage, **Resend** transactional email (`gallo-crm.com`), **Groq** LLM, **Turnstile**, **Microsoft OAuth**, **Cloudflare Pages** (a landing/site deploy — currently failing, see §3).

---

## 3. Roadmap — open work

Priority: **P1** = pitch blocker · **P2** = pre-scale · **P3** = later.

### P1 — the heart of the pitch
1. **Next-action fields on Deals** *(in progress — parallel session)* — `deals.next_action_type` (enum: call/whatsapp/email/proposal/meeting/follow-up/contract/collect/other) + `deals.next_action_at`; `PATCH /api/deals/{id}/next-action`; follow-up states (no-action / today / overdue / future / done); kanban card shows status + due.
2. **"Hoje" / action center** *(in progress — parallel session)* — route `/hoje` (overdue follow-ups, today's follow-ups, deals with no next action, stalled >7d, today's tasks, overdue tasks) backed by `GET /api/dashboard/today`. **This becomes the salesperson's landing screen** (see §4 — the dashboard should converge here).

### P2 — before scaling past one customer
3. **Onboarding < 30 min** *(backend + checklist/templates FE done; remaining:* empty-states-with-CTAs on every empty list, and the 3-question wizard → suggested pipeline*)*.
4. **Lead → Customer/Company/Deal conversion** *(in progress — parallel session, `lead_convert.py`)* — `POST /api/leads/{id}/convert` (atomic) + "Convert" button + `lead_converted` timeline event.
5. **GDPR native** *(not started; DEFERRED until the parallel session lands its models/schemas)* — `contact_consent_at` + `consent_source` on leads/customers; `POST /api/leads/{id}/forget` (anonymize PII, keep id for audit); `GET /api/leads/{id}/export`; configurable retention; GDPR settings page.
6. **Multi-currency** — `currency` on deals with `org.default_currency`; CHF/GBP/BRL in Stripe; currency selector on deal/quote; **replace the hardcoded `FX_TO_EUR` in `api/dashboard.py`** (display per-deal currency, no conversion).
7. **Products in the frontend** *(DONE — catalog pages + quote line-item picker).* 

### Open engineering items (genuinely not done)
- **e2e CI is red** — backend won't boot in CI: the crm_app password-rotation migration's guard fires because CI copies `.env.example` (placeholder password). *(parallel session's area.)*
- Optimistic locking on **Task + Customer** (Deal done); flip `If-Match` to strict once the FE always echoes `version`.
- **Frontend data layer:** adopt **TanStack Query** (kill ~12 `useEffect(()=>api.x().then(setX),[])`) + **openapi-typescript** (kill FE/BE type drift); toast system; pagination UI; loading skeletons; fix `react-hooks/exhaustive-deps`.
- Cache `GET /api/dashboard/stats` in Redis (60s TTL, invalidate on mutation); trash-list pagination; N+1 eager-loads.
- **Staging env + post-deploy smoke** (host TBD); Sentry source-map upload.
- v2 follow-ups: Notes (markdown/@mentions), Notifications (SSE push, retention prune), Team (round-robin, user-picker UI), Search (typo tolerance, deals search).

---

## 4. Scope decisions — keep it action-first (what to cut / merge)

Code is clean (no dead code). The bloat is *scope*: 23 nav routes, several not serving the next-action goal. Recommended (decide before executing — they touch the sidebar/nav/routes):

| Item | Decision | Why |
|---|---|---|
| **Duplicati** (page + API) | **Cut → P3** | Data housekeeping, not sales execution. Fold dedup into import. |
| **Automazioni** | **Cut / defer** | Half-built, no run history/audit — reps won't trust an unobservable engine. Prefer task templates + a prominent next-action. |
| **"Attività recenti"** dashboard widget | **Cut / rename** | Mislabeled — renders recent *leads*, which the Leads page already shows. |
| **Reports** | **Merge → Performance** | Both are analytics; make them tabs of one screen. |
| **Calendario** | **Merge → Attività** | Calendar is view-only (can't complete a task from it); Tasks is actionable. Offer a "month view" toggle on Tasks instead. |
| **Dashboard financial block** (Importi aperti + Preventivi) | **Slim** | Overlapping + empty on young orgs. Dashboard should be **KPIs + "what to do today"** (= the Hoje screen). Move the charts into Reports. |
| Forms · Documenti · Notifiche (page) · Assistant (page) | **Rework** | Forms→into Inbox queue; Documenti→status hub or drop (Quotes/Contracts already do CRUD); Notifiche→header bell only; Assistant→slide-out from any entity, not a nav page. |

**North star:** the dashboard converges into the **Hoje** action screen; cutting/merging the above takes nav from ~23 → ~12 and redirects effort to "what do I do in the next hour?".

---

## 5. Architecture decisions (ADRs — one-liners)

1. Permissive ownership (any auth reads; owner/admin/manager mutates). 2. Stateless JWT (+ Redis refresh revocation). 3. ~~create_all~~ → Alembic owns schema (ADR-012). 4. Audit log best-effort, not transactional. 5. One LLM via `openai_compat` (was Ollama+Anthropic fallback). 6. Background jobs via **Arq** (not Celery). 7. **Outbox** pattern for events (`FOR UPDATE SKIP LOCKED` + backoff + DLQ cap). 8. Postgres FTS first; dedicated engine only past ~1M rows. 9. **Multi-tenant = shared schema + RLS** defense-in-depth; two DB roles (`crm` owner/Alembic, `crm_app` NOBYPASSRLS runtime). 10. Cursor pagination. 11. Stripe webhook = source of truth. 13. Org via `OrgMembership` junction + `User.last_active_org_id`. 14. AI data residency: redact/localize PII before it leaves the tenant. 15. **Money = integer minor units / Decimal, never float.** 16. E-signature via a qualified EU/CH provider. 17. Transactional email = provider-abstracted worker workstream (Resend).

---

## 6. Conventions & where to find things

- **Backend** `backend/app/`: `api/` (routers, one per resource) · `models.py` · `schemas.py` (Pydantic) · `services/` (llm, ai_scoring, ai_assistant, stripe, chatbot) · `worker/` (Arq jobs/settings) · `database.py` (RLS GUC) · `deps.py` (auth/org deps) · `billing/catalog.py` (plan prices). Ruff (line 100, py312); money as Decimal; set the RLS GUC for any tenant query.
- **Frontend** `frontend/src/`: `app/[locale]/(app)/<route>/page.tsx` (authed pages) · `app/[locale]/(pricing|login|register|...)` (public) · `components/` · `lib/api.ts` (typed client, `credentials:include`, CSRF mirror, single-flight 401 refresh) · `lib/auth.ts` · `messages/<locale>.json` (i18n, 7 locales, parity-checked in CI). Strict TS; responsive-first (every grid needs a base `grid-cols-1`; flag/icon UIs use SVG, never emoji on Windows).
- **Workflows:** `docker compose up` (db/redis/backend/worker/minio/ollama). After a model change: edit `models.py` → `alembic revision --autogenerate` → review → applied on container restart. CI runs ruff/tsc/eslint/pytest/vitest/trivy/playwright.

---

## 7. Production infra (live facts)

- **Railway** project `zonal-surprise` / env `production`: services `frontend`, `crm_gallo` (API), `worker`, `Postgres`, `Redis`. Reach prod DB from outside via `DATABASE_PUBLIC_URL` + local psql.
- **Storage:** Cloudflare R2 (EU jurisdiction, GDPR), bucket `crm-gallo-attachments`, on both `crm_gallo` and `worker` (endpoint MUST be `https://`, `.eu.r2.cloudflarestorage.com`).
- **Email:** Resend on `gallo-crm.com` (`no-reply@`), DKIM/SPF/MX/DMARC verified.
- **AI:** Groq (`api.groq.com/openai/v1`, `openai/gpt-oss-120b`). Local `.env` LLM keys stay EMPTY.
- **Stripe:** LIVE Swiss account; one account only (dual IT+CH would be a separate feature). Local `.env` Stripe keys stay EMPTY.
- **Turnstile** (register) + **Microsoft OAuth** (Azure redirect URI EXACTLY `https://api.gallo-crm.com/api/auth/oauth/microsoft/callback`).
- **Hosting = Railway only (NO Cloudflare Pages).** A leftover CF Pages project `crmgallo` had been auto-building the repo (via Cloudflare's GitHub app, no repo config) and **failing on every push** — it was redundant (the Next.js app runs on Railway) and was **deleted 2026-06-11**. If "Workers Builds: crmgallo" checks or `cloudflare-workers-and-pages[bot]` emails ever reappear, the fix is to delete the project in the Cloudflare dashboard (Workers & Pages → crmgallo → Settings → Delete), not in repo config.

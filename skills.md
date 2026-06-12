# Gallo CRM — Single Source of Truth

> **One plan for every agent.** This file replaces the old `plan.md` (product plan —
> **100% executed, all 7 gaps closed 2026-06-12**, see git history for the line-item log)
> and the old 800-line `skills.md` (engineering backlog — its full verification history
> lives in git). Read this first; update it when work changes state.
> **Unified:** 2026-06-12.

---

## 0. Coordination protocol — READ FIRST (multiple agents share this repo)

- **Repo is PUBLIC** (`github.com/kallebesiqueira-dev/crm_gallo`). Never commit secrets; never re-paste a leaked value.
- **Isolation:** work from a fresh clone (preferred while other sessions are active) or a `git worktree` off `origin/main`. Commit ONLY your own files, squash-merge via PR. **Never `git checkout main` in a tree another agent shares**, and never junction/symlink `node_modules` into a worktree another agent may `worktree remove --force` (the recursive delete follows the junction and wipes the real `node_modules`). Commit+push early.
- **Git gotcha that bit us:** `git mv` moves the INDEX entry (the old blob) — if you rewrote the file on disk without `git add`, the commit ships the OLD content. After any scripted/file-tool write followed by `git mv`/commit, run `git add <file>` and check `git diff --cached` before committing.
- **Alembic heads:** every new migration revises the *current* head. If two agents branch a migration off the same head you get **two heads** → prod `alembic upgrade head` fails. Whoever merges second runs `alembic merge -m "merge" <headA> <headB>`.
- **Shared hot files — announce before editing, expect conflicts:** `backend/app/models.py`, `backend/app/schemas.py`, `frontend/src/lib/api.ts`, `frontend/messages/*.json` (all 7), `frontend/src/components/sidebar.tsx`, and **this document**.
- **Deploy:** Railway does NOT auto-deploy on git push. After merging to `main`, ship with `railway redeploy -s <frontend|crm_gallo|worker> --from-source -y`. A `NEXT_PUBLIC_*` var only reaches the browser bundle if `frontend/Dockerfile` declares an `ARG`+`ENV` for it (build-arg, baked at build) — verify by grepping the live JS chunks.

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

The technical core AND the product plan (old `plan.md`, 7 gaps) are complete and in production (Railway).

- **Follow-up engine (the pitch):** `deals.next_action_type/_at` + `PATCH /api/deals/{id}/next-action`, follow-up states (no-action/today/overdue/future/done) on kanban cards; **"Hoje" action center** at `/hoje` (`GET /api/dashboard/today`: overdue + today's follow-ups, no-next-action, stalled >7d, today's/overdue tasks) with sidebar badge.
- **Multi-tenant:** Organizations + Postgres RLS (ENABLE+FORCE+GUC, transaction-scoped via ContextVar) on every tenant table **including strict audit SELECT**; memberships, invites (create/accept/accept-while-logged-in/resend/prune), per-org seat enforcement.
- **Auth:** JWT in httpOnly cookies + double-submit CSRF (`/login` + `/mfa/verify` CSRF-exempt — stale-cookie lockout fix); refresh rotation + reuse-detection; MFA TOTP (mandatory admin/manager, secret Fernet-encrypted); password reset; sessions page; **Microsoft OAuth** (existing accounts; email read from the **id_token**); Turnstile on register (fails open if the provider errors); rate limits on register/assistant/score/imports/webhook-receiver.
- **Leads / Customers / Companies:** full CRUD, cursor pagination (stable sort), FTS + **pg_trgm typo fallback**, AI scoring + AI summary, **owner assignment**, optimistic locking (Deal/Task/Customer/Lead), **Lead → Customer/Company/Deal conversion** (atomic, dedup-aware, Convert button + timeline events).
- **Deals:** kanban drag-drop + **deal detail page** (`/pipeline/[id]`: notes/attachments/activity, next-action scheduler, stage switcher), per-deal `currency` inheriting `org.default_currency`; dashboard KPI shows per-currency breakdown (no fake FX).
- **Tasks (list + month view) · Activity timeline · Notes · Notifications** (header bell with view-all; the standalone calendar and notifications pages left the nav).
- **Quotes & Contracts:** quote→contract→e-signature→PDF (WeasyPrint in worker); merge-field templates; **line items pre-fillable from the Products catalog**.
- **Products/Services catalog:** backend + list/new/edit pages + sidebar + quote picker.
- **Imports/Exports:** CSV/XLSX, row validation, dedup, streaming export; the Duplicati tool is reached from the Imports page.
- **WhatsApp omnichannel:** Cloud API, webhook, inbox UI, read receipts.
- **AI (one provider, locale-aware):** lead scoring, customer summary (context: open deals + recent tasks/notes), assistant chat (**SSE streaming + conversation history**), public landing chatbot — all through **one Groq** endpoint via `app/services/llm.py`. **Every LLM call site takes a `locale` and answers in it.**
- **GDPR:** `contact_consent_at`+`consent_source` on leads/customers; `POST /{leads|customers}/{id}/forget` (anonymize-in-place, audit anchor survives) + `GET .../export`; per-org retention (`organizations.retention_months`, daily worker sweep, leads only); GDPR settings card in `/settings`.
- **Onboarding:** computed checklist widget + 7 sector pipeline templates (browse/apply page) + empty-states-with-CTA on every list.
- **Billing:** Stripe LIVE (Swiss account), Standard/Business/Premium monthly+yearly (yearly = exact −20%, totals shown), public checkout honors cycle + currency price points (CHF/GBP/BRL positioned), seats, trial, webhook = source of truth.
- **Public API + keys · Outgoing webhooks** (HMAC, outbox, retry, auto-pause, settings UI) · **Automations** (trigger→condition→action; triggers incl. customer.created/task.overdue/user.invited; URL-only while it lacks run history) · **Performance screen with a Report tab** (analytics + sales goals + the financial block) · **Audit log** (RLS-strict, UI).
- **Observability:** Sentry FE+BE (EU; **source-map upload wired, inert until `SENTRY_AUTH_TOKEN` is set**), PostHog (EU), Prometheus metrics + `/ready` probes in-code, Arq DLQ (`arq:dead` + depth gauge) + outbox lag gauge. (Standalone `monitoring/` Grafana/alert artifacts were removed — no Prometheus server in prod.)
- **Frontend platform:** toast system, list skeletons, responsive-first (every grid has base `grid-cols-1`), 7 locales with CI key-parity audit.
- **CI/CD:** backend (ruff/pytest/pip-audit/alembic), frontend (tsc/eslint/vitest/i18n-parity), docker (Trivy gate), e2e (Playwright smoke), security (gitleaks/trufflehog), db-backup, Dependabot. All green on `main`.

---

## 3. Roadmap — open work

**The product plan is closed.** What remains is engineering quality + user-side actions. Priority: **P2** = pre-scale · **P3** = later.

### Needs the USER (not code)
- Set `SENTRY_AUTH_TOKEN` / `SENTRY_ORG` / `SENTRY_PROJECT` in Railway frontend build env (un-minified prod stack traces).
- **Romansh (rm)** plan-card copy is machine-translated — needs native review.
- Legal pages (privacy/security/terms) are templates — need lawyer/DPO review.
- Footer Instagram link is a `#` placeholder — provide URL or drop it.
- The three §4 **reworks** (Forms→Inbox, Documenti, Assistant slide-out) need a design decision before coding.

### P2 — engineering
- **TanStack Query** (kill the ~12 `useEffect`+`setState` fetch patterns) + **openapi-typescript** (kill FE/BE type drift).
- Pagination UI on lists (backend cursors are ready); replace `…` placeholders with spinners; fix `react-hooks/exhaustive-deps`.
- ICU pluralization (`{count, plural, …}`) in messages.
- Webhook follow-ups: `POST /{id}/rotate-secret`, `POST /{id}/test`, delivery metrics, 90d delivery retention prune.
- **Staging env + post-deploy smoke** (host TBD).

### P3 — later
- LLM token-usage tracking per org/user; per-use-case temperature.
- Note v2: markdown rendering, @-mentions; "Add note" entry on the timeline; deal `score` activity.
- ts_rank relevance sort; per-locale FTS dictionary; dedicated search engine only past ~1M rows.

### Out of scope until paying customers
Gmail/Outlook/Calendar sync · RAG/pgvector document search · Instagram/Messenger · mobile app.

---

## 4. Scope decisions — keep it action-first

Code is clean (no dead code); the bloat was *scope*. Status after the 2026-06-12 execution round (PRs #95/#98/#99 — nav 27 → 22 entries):

| Item | Decision | Status |
|---|---|---|
| **Duplicati** (page + API) | Cut from nav → reach it from Imports | ✅ DONE #95 (button on the Imports header) |
| **Automazioni** | Defer from nav (no run history/audit yet) | ✅ DONE #95 (route stays URL-reachable) |
| **"Attività recenti"** dashboard widget | Cut (mislabeled — rendered recent leads) | ✅ DONE #95 (one fewer API call on mount) |
| **Notifiche** (page) | Header bell only | ✅ DONE #95 (bell gained a view-all link; page off the nav) |
| **Calendario** | Merge → Attività | ✅ DONE #98 (List\|Month toggle on Tasks; `/calendar` redirects) |
| **Reports** | Merge → Performance | ✅ DONE #99 (Performance\|Report tabs; `/reports` redirects) |
| **Dashboard financial block** | Slim — move charts into Reports | ✅ DONE #99 (`<FinancialOverview>` lives in the Report tab) |
| **Forms** | Rework → into Inbox queue | ✅ DONE #107 (Inbox channel pills WhatsApp\|Forms; queue = recent leads with a web-form source; management stays on `/forms`, off the nav) |
| **Documenti** | Rework → status hub | ✅ DONE #103 (group tiles w/ counts as filters + search + localized status badges; PDFs stay on detail pages) |
| **Assistant** (page) | Rework → slide-out from any entity | ✅ DONE #106 (global panel from a top-bar ✨ button; `/assistant` redirects; conversation survives open/close) |

**§4 is fully executed (2026-06-12).** Nav went 27 → 20. **North star:** the dashboard converges into the **Hoje** action screen.

---

## 5. Architecture decisions (ADRs — one-liners)

1. Permissive ownership (any auth reads; owner/admin/manager mutates). 2. Stateless JWT (+ Redis refresh revocation). 3. Alembic owns schema (no create_all). 4. Audit log best-effort, not transactional. 5. One LLM via `openai_compat`. 6. Background jobs via **Arq**. 7. **Outbox** pattern for events (`FOR UPDATE SKIP LOCKED` + backoff + DLQ). 8. Postgres FTS (+pg_trgm) first; engine only past ~1M rows. 9. **Multi-tenant = shared schema + RLS** defense-in-depth; two DB roles (`crm` owner/Alembic, `crm_app` NOBYPASSRLS runtime). 10. Cursor pagination. 11. Stripe webhook = source of truth. 13. Org via `OrgMembership` + `User.last_active_org_id`. 14. AI data residency: redact/localize PII before it leaves the tenant. 15. **Money = integer minor units / Decimal, never float.** 16. E-signature via a qualified EU/CH provider. 17. Transactional email = provider-abstracted worker workstream (Resend).

---

## 6. Conventions & where to find things

- **Backend** `backend/app/`: `api/` (routers, one per resource) · `models.py` · `schemas.py` · `services/` (llm, ai_scoring, ai_assistant, stripe, chatbot) · `worker/` (Arq jobs/settings) · `database.py` (RLS GUC) · `deps.py` · `billing/catalog.py`. Ruff (line 100, py312); money as Decimal; set the RLS GUC for any tenant query. **Every new AI/LLM feature MUST take a `locale` and instruct the model to answer in it.**
- **Frontend** `frontend/src/`: `app/[locale]/(app)/<route>/page.tsx` (authed) · `app/[locale]/(pricing|login|register|...)` (public; `/` re-exports `pricing`) · `components/` · `lib/api.ts` (typed client, `credentials:include`, CSRF mirror, single-flight 401 refresh) · `messages/<locale>.json` (7 locales, CI parity). Strict TS; **responsive-first** (base `grid-cols-1` on every multi-col grid; `min-w-0` beside any `flex-1 truncate`; full-screen overlays center in `h-[100dvh]`, portal out of `backdrop-blur` parents); SVG flags/icons, never emoji.
- **Workflows:** `docker compose up` (db/redis/backend/worker/minio/ollama). Model change: edit `models.py` → `alembic revision --autogenerate` → review → applies on restart. CI runs ruff/tsc/eslint/pytest/vitest/trivy/playwright/i18n-parity.

---

## 7. Production infra (live facts)

- **Railway** project `zonal-surprise` / env `production`: `frontend` (app.gallo-crm.com), `crm_gallo` (api.gallo-crm.com), `worker`, `Postgres`, `Redis`. Reach prod DB from outside via the Postgres service's `DATABASE_PUBLIC_URL` + local psql (e.g. through `docker exec crm_gallo_db psql …`).
- **Storage:** Cloudflare R2 (EU jurisdiction, GDPR), bucket `crm-gallo-attachments`, on both `crm_gallo` and `worker` (endpoint MUST be `https://…eu.r2.cloudflarestorage.com`).
- **Email:** Resend on `gallo-crm.com` (`no-reply@`), DKIM/SPF/MX/DMARC verified.
- **AI:** Groq (`api.groq.com/openai/v1`, `openai/gpt-oss-120b`). Local `.env` LLM keys stay EMPTY.
- **Stripe:** LIVE Swiss account, one account only; 6 plan prices (monthly + yearly −20%) + non-EUR price points; local `.env` Stripe keys stay EMPTY (never live).
- **Turnstile** (register) + **Microsoft OAuth** (Azure redirect URI EXACTLY `https://api.gallo-crm.com/api/auth/oauth/microsoft/callback`).
- **Hosting = Railway only (NO Cloudflare Pages).** The orphan CF Pages project was deleted 2026-06-11; if `cloudflare-workers-and-pages[bot]` checks/emails reappear, delete the project in the Cloudflare dashboard — there is no CF config in this repo.

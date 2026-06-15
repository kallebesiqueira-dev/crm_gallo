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

**The original product plan is closed.** Work is now driven by the **launch-readiness roadmap below** (user-prioritized, 2026-06-14) plus the standing engineering backlog. Priority order: 🚀 **launch-readiness** → **P2** (pre-scale) → **P3** (later).

### 🚀 LAUNCH-READINESS ROADMAP — PRIORITY (user, 2026-06-14)

Goal: take Gallo CRM to a polished, **Enterprise-grade**, commercial-launch product. Cross-referenced against §2 — **shipped items are compacted, only the delta is new**. Tags: 🆕 new · 🟡 partial · ✅ shipped.

1. **Multi-currency display layer** 🟡 — *shipped:* per-entity `currency` (deal ← `org.default_currency`), Stripe price points (CHF/GBP/BRL), per-currency dashboard breakdown with **no FX** (ADR #15). *New:* user-selectable **display currency** (EUR/CHF/USD/GBP), persisted per user, applied across reports/invoices/customers/stats/dashboards, extensible. ⚠️ **Needs an FX layer** — this reverses the "no fake FX" ADR: pick a rate source + cache + as-of stamping (or convert for display only) and replace the hardcoded FX in `dashboard.py`.
2. **Onboarding & in-app tutorial** 🟡 — *shipped:* onboarding checklist + 7 sector pipeline templates + empty-states-with-CTA. *New:* interactive first-run guided tour, contextual tooltips app-wide, integrated help center, step-by-step guides (customers/leads/pipeline/reports/finance/settings).
3. **Landing-page audit** 🆕 — every advertised feature must exist; clear value prop; screenshots/copy match the current UI; SEO; conversion-focused; fully responsive.
4. **Demo video** 🆕 (marketing, not code) — full + short-marketing + social cuts; cover dashboard, customers, pipeline, reports, multi-currency, automations, differentiators.
5. **Public README & living docs** 🆕 — polished GitHub README (screenshots/GIFs/video, install + deploy guides, API docs, detailed changelog); refresh docs after each feature. (`skills.md` stays the internal plan.)
6. **Frontend finalization** ✅ DONE (via the #11 audit, 2026-06-15) — loading/error states, form validation, dialog a11y/focus-traps, 412 conflict handling, locale-aware formatting all fixed + deployed. (Pagination UI + `exhaustive-deps` remain as low-priority P2 polish; TanStack migration still P2.)
7. **Backend finalization** ✅-mostly — APIs/RLS/auth/MFA/authz/audit/rate-limits/Arq-DLQ/observability/db-backup/pytest+e2e are live & mature (§2). *New:* a final hardening + perf + integration-coverage audit only.
8. **Keyboard shortcuts** ✅ DONE+LIVE (2026-06-15) — `⌘/Ctrl+K` command palette (navigate to any route + quick-create + entity search) + `?` shortcuts-help overlay + `g`+`d/h/l/c/p/t` go-to leader shortcuts. (Single-letter `+N`/`+S` creates skipped — the palette covers create; bare keys are conflict-prone.)
9. **Customer photos** ✅ shipped (PR #38) — `avatar_key` on user/customer/company, presigned R2 GET + image-only multipart POST, `<AvatarUpload>` in edit headers + top-bar chip, default avatar. *New (enhancement only):* drag-&-drop + client-side crop/resize.
10. **Enterprise UI redesign** ✅ DONE+LIVE (2026-06-15) — squarer radius tokens (#140), emoji→lucide icons (#143), shared Select/Textarea primitives + 29-file sweep (#148), brand accent-color on native form controls, centered form cards (`mx-auto`), brand-gradient section titles (light+dark). Tables/cards/buttons were already consistent. Paired with #11.
11. **UX/UI audit** ✅ DONE+LIVE (2026-06-15) — full-app audit → all P0/P1/P2 fixed + deployed: loading/error states (#151, incl. the Hoje hung-skeleton P0), i18n strings + aria (#153), dialog focus-trap/Esc (#156), 412 version-conflict (#157 products/deals, #169 leads), form validation (#158), website/currency inputs (#168), locale-aware date/money (#174).
12. **Final QA** 🆕 — pre-launch FE/BE/mobile/responsive/cross-browser/perf tests, security + UX audit, deploy + DB validation; zero critical bugs / incomplete features.

**A. AI Assistant — Gemini-in-Gmail redesign** ✅ DONE+LIVE (2026-06-15, #162/#164/#165/#166/#171) — replaced the global slide-out with a **smart AI card on the Dashboard** (AI icon + "Como posso ajudar você hoje?" + simplified input + quick-action chips: Analisar Pipeline / Criar Proposta / Gerar Relatório / Resumir Clientes / Criar E-mail) that opens a **bottom-sheet** (mobile 70–85% height, dashboard visible behind + soft blur, rounded top, drag-down to dismiss) / **floating panel** (desktop, centered/anchored, not full-screen). Route-aware context (dashboard→insights, customers→summarize, leads→conversion), SSE streaming (already wired), `Enter` send / `Shift+Enter` newline, contextual suggestion chips. **NOT** a chatbot / standalone page / generic modal. ✅ Screenshot received 2026-06-15 → shipped as the mobile bottom-sheet / desktop floating panel + chips + brand-gradient greeting; fixed chat-stream auth (cookie+CSRF, not the dead Bearer — #164) + panel height-clip (#166). The dashboard AI-card entry (#165) was **removed per user** — the top-bar ✨ suffices (#171).

> **Mission:** audit the *whole* project beyond this list (FE/BE/DB/APIs/auth/flows/landing/docs/infra/deploy/perf/security) and execute the plan to reach Enterprise-grade, commercial-launch quality.

### Needs the USER (not code)
- Set `SENTRY_AUTH_TOKEN` / `SENTRY_ORG` / `SENTRY_PROJECT` in Railway frontend build env (un-minified prod stack traces).
- **Romansh (rm)** plan-card copy is machine-translated — needs native review.
- Legal pages (privacy/security/terms) are templates — need lawyer/DPO review.
- Footer Instagram link is a `#` placeholder — provide URL or drop it.
- **AI-assistant Gemini-in-Gmail redesign** (§3 priority **A**) needs the **reference screenshot** + a design sign-off before coding. *(The earlier §4 reworks — Forms→Inbox, Documenti, Assistant slide-out — all shipped: #103/#106/#107.)*

### P2 — engineering
- **TanStack Query** (kill the ~12 `useEffect`+`setState` fetch patterns) + **openapi-typescript** (kill FE/BE type drift).
- Pagination UI on lists (backend cursors are ready); replace `…` placeholders with spinners; fix `react-hooks/exhaustive-deps`.
- ICU pluralization (`{count, plural, …}`) in messages.
- ~~Webhook follow-ups: `POST /{id}/rotate-secret`, `POST /{id}/test`, delivery metrics, 90d delivery retention prune.~~ ✅ DONE — rotate-secret (one-time secret, audited), synchronous `/test` ping (records a `webhook.test` delivery row, never touches auto-pause, works while paused), `GET /{id}/metrics` (windowed counts + success rate + p50/p95 latency), and the `prune_webhook_deliveries` daily cron (03:41 UTC, 90d cutoff). Settings card gained Test + Rotate buttons and a per-endpoint metrics line.
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
| **Assistant** (page) | Rework → slide-out from any entity | ✅ DONE #106 (global slide-out from a top-bar ✨); **🔁 redesign requested 2026-06-14** → Gemini-in-Gmail dashboard card + bottom-sheet (see §3 priority **A**) |

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

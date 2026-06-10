# Engineering Backlog & Project Status

> **Living document.** Update when work changes state. Read this first when resuming work.
> **Last reviewed:** 2026-06-09 (WhatsApp omnichannel + premium dashboard live; Products catalog backend built + verified)

---



## 1. Quick context

**CRM Gallo** is an AI-powered multilingual CRM (Next.js 15 + FastAPI + PostgreSQL/pgvector + Claude/Ollama).
Current stage: **post-MVP hardening complete**, pre-multi-tenant.
Last big sweep: surgical hardening pass on 2026-05-28 (security, RBAC, audit, i18n, dialogs).

For the user-facing story, see [README.md](README.md). This document is the engineering view.

---

## 2. Current state

### ✅ Done (2026-06-09 — WhatsApp omnichannel + premium dashboard + Products catalog)
- **WhatsApp omnichannel (PR #25, live):** `whatsapp_accounts` (non-RLS routing root — resolves the tenant from the unauthenticated inbound webhook) + `conversations` + `messages` (org-scoped, RLS ENABLE+FORCE+GUC policy) via migration `c5d6e7f8a9b0`; send/receive API, inbound webhook, worker jobs, inbox UI, i18n in all 7 locales. 29 tests green.
- **Premium dashboard redesign (PR #22–#25, live):** purple brand theme, glassmorphism widgets, **6-group sidebar** (Vendite / Clienti / Lavoro / Crescita / Gestione / Sistema; `inbox` under Lavoro), clean topbar (search · mail→inbox · bell · help), clickable card controls. tsc + eslint clean.
- **Products / Services catalog — BACKEND done & verified:** `products` org-scoped tenant table (RLS ENABLE+FORCE+GUC policy) + `producttype` enum via migration `d7e8f9a0b1c2`; `Product` model, `ProductCreate/Update/Out` schemas, full CRUD `/api/products` (mirrors `companies.py`). ruff clean, migration applies locally, RLS confirmed. **Frontend (list/new/edit + sidebar entry + i18n) is the next slice; not yet deployed.**
- **Insight that re-scoped the roadmap:** most "missing" nav features already have BACKENDS — `deals`=Opportunità, `exports`=Esportazioni, `notifications`=Notifiche, `teams`=Team, `attachments`/`document_templates`=Documenti. They need FRONTEND pages, not new entities. Only the catalog needed a new table.

### ✅ Done (2026-06-01 security hot-patch)
- `python-jose` 3.3.0 → 3.5.0 (closes PYSEC-2024-232/233 + PYSEC-2025-185 — JWT lib)
- `python-multipart` 0.0.12 → 0.0.30 (closes 4 CVEs in the multipart parser — upload surface)
- `fastapi` 0.115.0 → 0.120.4 (needed to allow newer starlette)
- `starlette` pinned at 0.49.3 (was 0.38.6 — closes GHSA-f96h-pmfr-66vw + GHSA-2c2j-9gv5-cj73)
- `pip` upgraded to 26.1 in the Dockerfile (closes 4 GHSA on the installer itself)
- CI `pip-audit` allowlist for the 2 vulns we can't close yet (TD-28, TD-29) — each carries a comment with the unblock condition
- Smoke: pytest 17/17, login + /score-async end-to-end green after the JWT lib bump

### ✅ Done (2026-06-02 — Quotes frontend + critical RLS/pool fix)
- **Quotes frontend (ADR-016 UI slice):** list / new / edit / detail pages + shared `QuoteForm` (live totals) under `app/[locale]/(app)/quotes/`; status-driven actions (draft→edit/send/delete, sent→accept/decline, non-draft→resend); PDF generate-poll-download. API client gained Quote types + 10 methods; `FileAttachment`/`listAttachments` widened to `quote`. Sidebar switched `documents`→`quotes` (orphan route deleted). All 7 locales. tsc clean for quote files.
- **🔴 Critical RLS/pool bug — FOUND & FIXED.** The tenant GUC was set **connection-scoped** (`set_config(..., false)`). Routes commit mid-request, which releases the connection to the pool (size 5); the post-commit readback (`_get_quote_or_404`, `db.refresh()`) reacquired a DIFFERENT pooled connection → no GUC (flaky 404) or **another tenant's GUC (cross-tenant data leak)**. Concurrent repro: 7/10 readbacks landed on the wrong org. App-wide (every commit-then-readback endpoint). Fix = transaction-scoped GUC via `ContextVar` + `begin` event (see Phase 6 bullet, now revised). Verified: repro 0/10, HTTP quote-create 5/5 consistent 201 (was flaky), pytest 111/111.
- **Worker GUC parity + audit:** worker was safe-by-convention only; hardened with the same transaction-scoped mechanism (`register_org_guc` on the worker engine + `set_current_org_id` in jobs). Quote-PDF job verified end-to-end as `crm_app`.
- **Attachments bug fix:** `EntityType` literal in `api/attachments.py` omitted `quote` → list/upload of quote attachments returned 422, blocking the quote detail page's PDF display. Added `quote`.
- **`file_attachments` RLS (TD-42) — FIXED.** The last tenant table without row-level security; now ENABLE + FORCE with the standard `app.current_org_id` GUC policy (migration `c8e4d3f9a1b2`). Verified safe — every reader/writer already sets the GUC. Direct `crm_app` battery green (no GUC→0, own→N, cross-org SELECT→0, cross-org INSERT→RLS violation); API attachment list still 200; suite 111/111.

### ✅ Done (2026-06-01 — backend depth)
- **Background worker** (Arq, ADR-006): `worker` service in compose; jobs `score_lead`, `drain_outbox` (5s cron), `deliver_webhook` — closes TD-14.
- **Outbox + event bus**: `outbox_events` + `record_event` producer, `drain_outbox` consumer (`FOR UPDATE SKIP LOCKED` + backoff + DLQ cap), in-process subscribers — closes TD-16.
- **Outgoing webhooks**: HMAC-signed, arq-retried, auto-pausing endpoints + `WebhookDelivery` log.
- **Full-text search**: stored `tsvector` + GIN on leads/customers — closes TD-13.
- **Optimistic locking on Deal**: `version` + `If-Match` → 412 — closes TD-12.
- **Refresh token rotation + reuse detection**: rotates per `/refresh`; reuse revokes all sessions.
- **Redis-backed rate limiter** — closes TD-15.

### ✅ Done (2026-05-28 hardening pass)
- RBAC enforcement on destructive endpoints (`hard_delete`, `empty_trash`)
- Permissive ownership: list/get open, mutate requires owner or admin/manager
- SlowAPI rate limit on `/api/auth/login`
- `JWT_SECRET` runtime validation (refuses weak secrets in production)
- Race-safe first-user-admin (Postgres advisory lock)
- `register` returns `{user, token}` in one round-trip; `/logout` endpoint
- structlog + per-request `X-Request-ID` + `/health` / `/ready` split
- `AuditLog` populated on every mutation (best-effort)
- Pipeline drag-drop validates target stage (fixes drop-on-card bug)
- Calendar uses local date (fixes TZ rotation)
- Dashboard fully i18n + `Intl.NumberFormat` per locale
- `ConfirmProvider` + `useConfirm` replaces native `confirm()`/`alert()`
- 401 interceptor in `lib/api.ts` + cross-tab token listener
- Backend Dockerfile non-root + healthcheck; frontend uses `npm ci`
- All 7 locales updated with new keys

### ✅ Done (billing + design pass)
- **Pricing model**: Free / Standard / Premium with monthly+annual (-20%) cycles, prices in EUR
- **Plan catalog** as single source of truth in `backend/app/billing/catalog.py`
- **Seat enforcement**: Free capped at 2 users; 3rd registration returns 402 with upgrade hint
- **Stripe integration** (ADR-011): Checkout session, Customer Portal, signed webhook with idempotency table (`stripe_events`)
- **Webhook handlers**: `checkout.session.completed`, `invoice.paid`, `customer.subscription.deleted`
- **Audit log** entries for every billing transition (`billing.checkout_session.create`, `billing.subscription.activated`, `billing.invoice.paid`, `billing.subscription.canceled`)
- **Premium 14-day trial** wired through `trial_period_days` on the Stripe subscription
- **Public pricing page** (`/pricing`) — split hero, monthly/annual toggle, tier cards, feature matrix, FAQ, trust signals
- **Internal billing page** (`/billing`) — current plan card, seat usage progress, upgrade matrix, Stripe Portal redirect, billing-history placeholder
- **PasswordInput component** — eye toggle + zxcvbn-lite strength meter
- **Login + Register redesign** — split-screen brand panel, gradient hero, plan picker on register, password strength, terms checkbox
- **Plan badge** in app header (per-tier styling: slate/blue/amber-fuchsia gradient)
- **Contextual banners** in app layout: trial ending in ≤7 days, seat-limit reached, subscription canceled
- **Colorful charts** with recharts: dashboard sparkline + stage bars; reports area chart, bar chart, donut, horizontal funnel; themed `<ChartTooltip>` + curated palette in `components/charts/`
- **Skeleton component** + actual skeletons on billing page load
- All 7 locales (en/pt/de/fr/it/rm/es) ship `pricing`, `billing`, `marketing` namespaces

### 🔄 In progress
*(nothing committed — pick the next P1 item)*

### ⏭️ Next milestone
**P0 multi-tenant is DONE** (orgs + RLS + invites + billing migration — all of §3 P0). So is the P1 backend-depth round (worker, outbox, webhooks, search, locking), the **Transactional-email workstream** (DONE 2026-06-01, ADR-017), and the **full ADR-016 Documents stack** — PDF foundation, versioned Quotes, versioned Contracts (backend + frontend + create-from-quote), merge-field templates, e-signature on both quotes and contracts, bulk Imports/Exports, and the Public API + API keys are ALL DONE and pushed to `main` (commits `4cfb6bc`/`37dcf6b`/`40ea9b2`/`b0374dc`/`5a02240`/`a7c5c1a`/`2e0302a`/`380898d`). Cursor pagination (TD-11) and money→Decimal (TD-30) done too. **CI is green** on all 4 workflows; frontend Vitest + backend cross-org RLS guard + Playwright e2e (core gate + opt-in scoring) all landed 2026-06-04.

**Genuine remaining pre-paying-customer candidates (none started):**
- **Run the e2e in CI** — the core Playwright smoke is deterministic but un-wired; needs the full docker stack stood up in GH Actions (db+redis+worker+ollama+backend+frontend). Heaviest-but-highest-signal gate.
- **Auth hardening leftovers** — MFA mandatory for admin/manager (§P1 191), MFA secret at-rest encryption (192), DB-load of user on `/refresh` to honor `is_active=false` instantly (189).
- **Audit SELECT strict policy / repo grep guard** (§Database 169) — today audit cross-org safety leans on app-layer filtering.
- ~~Audit-matrix tests~~ DONE — base matrix existed since 2026-06-04 (`test_audit_matrix.py`), widened 2026-06-10 (company/product/tag/note/trash.empty/invite/api_key/team). Per-resource lifecycle tests also DONE 2026-06-10 (`test_crud_lifecycles.py`).
- **Staging env + post-deploy smoke** (231) — deferred until a host is chosen.

---

## 3. Roadmap

Priority legend:
- **P0** — next milestone, blocks everything else
- **P1** — should do before scaling beyond 1 customer
- **P2** — quality-of-life, polish
- **P3** — future phases / nice-to-have

---

### 🟥 P0 — Multi-tenant Organizations

Prerequisite for selling to more than one company. Every other feature is downstream.

**Phase 1 — schema + backfill (DONE 2026-05-30, migration `bcac4a2cdbfa`):**
- [x] `Organization` model — id (UUID), name, slug (unique), plan, billing_cycle, plan_*_at, trial_ends_at, stripe_customer_id, stripe_subscription_id
- [x] `OrgMembership` junction (user_id, organization_id, role) — composite PK so the same user can belong to multiple orgs with different roles
- [x] `organization_id` FK (NOT NULL) on Lead, Customer, Deal, Task
- [x] `organization_id` FK (nullable) on AuditLog — platform-level events have no org context
- [x] `User.last_active_org_id` — current-org pointer; switching orgs is a PATCH /me, no JWT reissue
- [x] Backfill migration creates `default-workspace`, attaches every existing user as a member preserving their legacy role, re-parents every existing lead/customer/deal/task/audit_log row
- [x] Compound indices: `(organization_id, created_at DESC)` on leads/customers/audit_logs, `(organization_id, stage, updated_at DESC)` on deals, `(organization_id, due_date)` on tasks — see ADR-013

**Phase 2 — query scoping + cross-org isolation (DONE 2026-05-30):**
- [x] New `get_current_org_id` dep — resolves from `User.last_active_org_id`, falls back to oldest membership, raises 403 if user has zero memberships
- [x] New `get_current_membership` dep — returns role-in-current-org for org-scoped RBAC checks
- [x] Every CRUD endpoint (leads / customers / deals / tasks / dashboard / trash) filters by `Model.organization_id == org_id` on SELECT and sets `organization_id = org_id` server-side on INSERT; `organization_id` is stripped from PATCH bodies so a buggy client can't move a row across tenants
- [x] Cross-org reads return 404 via `_get_*_or_404` helpers (no 403 to avoid existence leaks)
- [x] Signup creates `OrgMembership` and pins `User.last_active_org_id`; fresh installs bootstrap `default-workspace`
- [x] `record_audit(..., organization_id=...)` propagates org context into every audit row
- [x] `UserOut` schema includes `last_active_org_id` so the frontend org switcher can highlight the active workspace
- [x] **Manual smoke test 2026-05-30:** seeded a second org + lead via SQL, then as user `kalle` (default-workspace) probed `GET/PATCH/DELETE /api/leads/<probe-id>` — all returned **HTTP 404 "Lead not found"**, never 403. `GET /api/leads` returned only the home-org lead. Invariant confirmed for leads.
- [x] **Debt — DONE 2026-06-04** (commit `f83b22a`). Wired into pytest as `tests/test_org_isolation.py`: a parametrized guard over lead/customer/deal/task asserting cross-org access returns 404 (never 403) on detail/list/trash routes + the audit log. 17 cases, runs on every backend CI build. Task has no GET-detail route so its detail case probes PATCH/DELETE only.

**Phase 3 — billing migration (User → Organization) (DONE 2026-05-30, migration `67d7b27d5ceb`):**
- [x] New `get_current_org` dep — returns the Organization object so billing endpoints don't need a second query
- [x] `billing.py` /me, /upgrade, /checkout, /portal all read/write `Organization` instead of `User`
- [x] Stripe webhook handlers (`_on_checkout_completed`, `_on_invoice_paid`, `_on_subscription_deleted`) update `Organization.plan / .stripe_*`; webhook-driven audits use `actor=None` + `organization_id=org.id` (no user is "the actor" of a Stripe-fired event)
- [x] Stripe Customer is 1:1 with Organization — checkout/portal metadata carries `organization_id` instead of `user_id`; `_find_org_by_customer` replaces the old user lookup
- [x] Seat enforcement is per-org: `_seats_used(db, org_id)` counts `OrgMembership` rows JOIN active users; `can_accept_new_user(db, org_id)` checks the destination org's plan, not a global cap
- [x] `auth.register` resolves the org first, then runs the per-org seat check
- [x] Migration `67d7b27d5ceb_drop_user_billing_columns` removes 8 columns from `users` (plan, billing_cycle, plan_*_at, trial_ends_at, stripe_customer_id, stripe_subscription_id) and the two `ix_users_stripe_*` indices; composite tenant indices from the previous migration are preserved
- [x] `User` model in `models.py` no longer declares billing fields — single source of truth is `Organization`

**Phase 4 — invite flow (DONE 2026-05-30, migration `62fa86d2429c`):**
- [x] `OrgInvite` model — id, organization_id, email, role, token (unique, urlsafe 32-byte), expires_at (+7d default), created_by_user_id, accepted_at, created_at
- [x] `POST /api/orgs/current/invites` (admin-of-current-org only via `get_current_membership`) — generates `secrets.token_urlsafe(32)`, dedupes against pending-not-expired same-(org,email), returns invite + `invite_url`, audits `invite.create`
- [x] `GET /api/orgs/current/invites` — admin lists pending (accepted_at IS NULL AND not expired); composite index `(organization_id, accepted_at)` for the query
- [x] `DELETE /api/orgs/current/invites/{id}` (admin) — revokes, audits `invite.revoke`
- [x] `GET /api/invites/{token}` — public preview, returns org name + email + role + expires_at; emits 410 for accepted-or-expired (so the UI can distinguish "wrong link" from "used link")
- [x] `POST /api/auth/register-with-invite` — public, rate-limited (same cap as /login). Creates user + membership atomically with the invite burn (`accepted_at = now()`). Per-org seat check runs BEFORE the writes — Free plan at cap returns 402 even with a valid token
- [x] Audit events on every transition: `invite.create`, `invite.revoke`, `invite.accept`
- [x] Email delivery is currently `log.info("invite.dispatched", invite_url=…)` + the create response includes the URL. Real SMTP belongs to P1 auth hardening.
- [x] **Smoke-tested end-to-end (2026-05-30) — 11 probes:** create / dedupe-returns-same / public preview / accept blocked by seat cap / accept after upgrade / re-accept burned token (410) / DB verification (user+membership+burned invite) / non-admin invite (403) / revoke (204). All green.

**Phase 4 known gaps (follow-ups, not blockers):**
- [ ] Existing logged-in user accepting an invite to join a NEW org (today the endpoint refuses, message tells them to log in first — but there's no "accept while logged in" route yet)
- [ ] Resend / regenerate invite endpoint
- [ ] Background sweep deleting expired-and-unaccepted invites older than 30 days

**Phase 5 — frontend:** ✅ done 2026-05-30
- [x] Backend orgs API: `GET /api/orgs/me`, `POST /api/orgs/me/switch` (404 if not member), `POST /api/orgs` (auto-switch)
- [x] API client: `Role`, `Organization`, `Membership`, `Invite`, `InvitePreview` types + 7 new methods
- [x] `<OrgSwitcher>` in header — hides for <=1 membership, inline "create new org" form, page reload on switch
- [x] `/[locale]/invite/[token]` accept page — public preview, register form with pinned email, friendly 404/410 dead-link UI
- [x] `<TeamCard>` on `/settings` — email+role invite form, pending list, revoke, one-time `invite_url` copy-to-clipboard
- [x] All UI strings in 7 locales (`team.*` + `auth.invite*`)
- [x] **Smoke-tested 2026-05-30 — 15 probes:** login, list orgs (1), create invite, public preview, bad-token 404, list returns `invite_url: null` (one-time view), 
seat-cap 402, create new org, auto-switch verified, list orgs (2), create+accept invite in new org, agent isolation (own org only, no foreign leads), replay 410, switch back, switch-to-non-member 404, revoke 204. All green.


**Phase 6 — defense-in-depth (RLS):** ✅ done 2026-05-30
- [x] **PostgreSQL Row-Level Security** ENABLE + FORCE on `leads`, `customers`, `deals`, `tasks` with symmetric `USING / WITH CHECK (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)` policy. `audit_logs` has split policy (SELECT permissive when GUC unset for system code paths, INSERT `WITH CHECK (true)`). `org_invites` intentionally NOT RLS'd — public token-lookup endpoints have no current_org_id.
- [x] **Two-role split** (migration `f5fde59e0dc8`): `crm` = bootstrap superuser / owner / Alembic; `crm_app` = LOGIN NOSUPERUSER NOBYPASSRLS / FastAPI runtime. `DATABASE_URL` (crm, Alembic) and `APP_DATABASE_URL` (crm_app, runtime) split in `.env`; `Settings.runtime_database_url` falls back to `database_url` if unset.
- [x] **Tenant GUC is transaction-scoped** (REVISED 2026-06-02 — the original session-persistent design was a cross-tenant bug; see "Critical RLS/pool bug" in §2 Done). `get_current_org_id` stashes the org in a `ContextVar` (`app.database.current_org_id_ctx`) via `set_current_org_id()`; a `@event.listens_for(engine.sync_engine, "begin")` handler (`register_org_guc`) re-applies `set_config('app.current_org_id', …, true)` (SET LOCAL) at the start of EVERY transaction — including the autobegin after a mid-request commit. SQLAlchemy's greenlet copies the contextvars, so the begin handler sees the request task's value. Transaction-local ⇒ auto-clears at commit ⇒ cannot leak across pooled connections.
- [x] `get_db` no longer wipes a connection-scoped GUC (nothing to wipe); it just resets the ContextVar on close.
- [x] **Worker parity:** the Arq worker builds its own engine, so `_startup` also calls `register_org_guc(engine)`; jobs call `set_current_org_id(org)` instead of the old `set_config(false)`. Each job is a fresh asyncio task (clean context copy) so the GUC can't leak between jobs.
- [x] **Smoke-tested 2026-05-30:** direct SQL as `crm_app` proves enforcement — no GUC → 0 rows on tenant tables; foreign GUC → 0 rows; own GUC → N rows; cross-org INSERT (no/wrong GUC) → `new row violates row-level security policy`. Full API battery (auth/orgs/leads/customers/deals/tasks/dashboard/invites + CRUD + soft-delete + org switch) all 200/204. Two bugs caught and fixed during smoke: `db.refresh` after commit losing GUC (solved by session-persistent GUC + cleanup); audit_logs `INSERT...RETURNING` from unscoped system routes failing the SELECT-via-RETURNING check (solved by relaxing SELECT policy to allow when GUC unset).

**Phase 6 known gaps / hygiene (follow-ups, not blockers):**
- [x] `file_attachments` brought under RLS — done 2026-06-02 (TD-42, migration `c8e4d3f9a1b2`). Was the last tenant table relying on app-layer filtering only; now ENABLE + FORCE with the standard GUC policy.
- [ ] Audit_logs SELECT policy is RLS-advisory (not strict) — relies on app-layer filtering. If a future route reads audit cross-org without a `WHERE organization_id` clause it will leak. Add a lint or repo grep guard if this risks regression.
- [ ] `crm_app` password (`crm_app_dev_2026`) is hardcoded in migration. Rotate via `ALTER ROLE crm_app PASSWORD '…'` before any non-local deploy and update `APP_DATABASE_URL`.
- [ ] Future data-touching migrations run as `crm` (owner, RLS-respecting under FORCE) — they must either set the GUC or temporarily `DISABLE ROW LEVEL SECURITY` around the data step. Pure DDL is unaffected.

**Watch out for:**
- `User.email` currently global-unique. Decide: still global (one identity per email) or per-org (same email can join multiple orgs)? Probably global.
- `Lead.email` is non-unique today. With orgs, decide if it's unique-per-org.
- Existing `User.role` field — moves to `OrgMembership.role`; keep `Useris_platform_admin` boolean for our own staff support access.
- The current billing fields on `User` (`plan`, `billing_cycle`, `plan_started_at`, `plan_renewed_at`) move to `Organization` — the migration is destructive without a clear org-per-user backfill plan.




---

### 🟧 P1 — Should do before scaling

#### Auth hardening
- [x] Replace `localStorage` token with **httpOnly cookie + CSRF token** — done 2026-05-30. JWT now lives in `access_token` httpOnly cookie set by backend on login/register/register-with-invite; matching `csrf_token` cookie (JS-readable, ~32 bytes urlsafe) emitted alongside. CSRF middleware in `main.py` enforces double-submit on POST/PUT/PATCH/DELETE when an auth cookie is present (constant-time compare via `secrets.compare_digest`); GET/HEAD/OPTIONS exempt; unauthenticated mutating endpoints (login, register, reset, webhooks) exempt by absence of cookie. `get_current_user` reads from cookie first, falls back to Authorization header (transitional for non-browser callers — curl, tests, integrations). Frontend `lib/auth.ts` keeps `getToken/setToken/clearToken` as compat shims (no-ops; `getToken` returns sentinel from `csrf_token` cookie presence) so the 23 call sites compile unchanged; `lib/api.ts` adds `credentials: 'include'` to every fetch and auto-mirrors `csrf_token` cookie into `X-CSRF-Token` header on mutating methods. CORS already allowed credentials + specific origin; added `X-CSRF-Token` to `allow_headers`. Logout clears both cookies via Set-Cookie. **Smoke verified end-to-end:** login → cookies set, GET via cookie 200, POST without CSRF 403, POST with CSRF 201, logout 204, post-logout GET 401.
- [x] **Refresh tokens** (short-lived access, long-lived refresh) + Redis revocation — done 2026-05-30. Access JWT shortened to 15 min (was 60); opaque URL-safe refresh token (~43 chars) lives in Redis (`refresh:{token}` → user_id) with 30-day TTL. `app/redis_client.py` (new): async singleton pool, `store/resolve/revoke` helpers. Three cookies: `access_token` (httpOnly, path=/, 15min), `refresh_token` (httpOnly, path=/api/auth, 30d — narrower than / so it's only sent to auth endpoints, including /refresh and /logout for revoke), `csrf_token` (JS-readable, path=/, 30d — outlives access so SPA can echo CSRF when calling /refresh after access expiry). `POST /api/auth/refresh` reads refresh cookie, validates in Redis, rotates ONLY access cookie (non-rotating refresh — simpler, avoids two-tab-race; rotation is a P2 hardening item). Logout revokes Redis entry AND clears all three cookies. **Smoke verified end-to-end:** login (200, all 3 cookies, Redis TTL ≈ 2591997s/30d), refresh (200, access rotated, refresh preserved), GET with new access (200), logout (204, Redis empty), stale-token replay refresh (401). Frontend `lib/api.ts` has a singleton in-flight `attemptRefresh()` — N concurrent 401s collapse to ONE /refresh call; on success the original request is retried once (with `_retrying` flag to prevent loops), on failure it falls through to the existing 401 handler.
- [x] **Refresh token rotation + reuse detection** — done 2026-06-01. `/refresh` rotates the refresh cookie on every call (`rotate_refresh_token` in `app/redis_client.py`); the superseded token is kept as a tripwire — any second use fires `refresh.reuse_detected`, revokes ALL of the user's sessions (steal signal), and returns 401. A missing cookie stays a plain 401 ("no refresh token") so it's never confused with the alarm. Covered by `tests/test_refresh_rotation.py` (4 tests: rotates / old-token-invalidated / reuse-revokes-all-sessions / no-cookie-plain-401).
- [ ] DB-load of user on /refresh to enforce `is_active=false` instantly (today the next protected call catches it)
- [x] **MFA (TOTP)** — done 2026-05-30 (opt-in for all users; mandatory enforcement for admin/manager remains a follow-up). `pyotp==2.9.0`. New model fields on `users` (`mfa_secret` base32, `mfa_enabled` bool, `mfa_enrolled_at` ts) + table `mfa_backup_codes` (id, user_id, code_hash bcrypt, used_at) — migration `aff1800a6b5d`. Service module `app/mfa.py`: `generate_secret`, `provisioning_uri`, `verify_totp` (±1 step skew), `generate_backup_codes` (10 codes, hashed, wipes prior unused), `consume_backup_code` (constant-time across candidate set), `count_unused_backup_codes`. Endpoints in `auth.py`: `GET /api/auth/mfa/status`, `POST /mfa/setup` (issues secret + provisioning URI), `POST /mfa/enable` (validates first code, activates, returns 10 plaintext backup codes ONCE), `POST /mfa/disable` (requires password AND a current TOTP/backup code), `POST /mfa/verify` (second step of login, takes `mfa_token` + code). `/login` now branches: MFA off → full session as before; MFA on → returns `{mfa_required, mfa_token}` (short-lived 5-min challenge JWT with `purpose=mfa_challenge`). `get_current_user` rejects challenge tokens for non-/verify endpoints. Frontend: 2-step login UI on `/[locale]/login` (form swaps to TOTP/backup input on challenge), `<MfaCard>` on /settings with QR (rendered via api.qrserver.com — TODO: swap for client-side renderer in prod), enroll/enable/disable flows, backup-code one-time display + copy. All 7 locales updated (auth.mfa* 7 keys + new `mfa.*` namespace 22 keys). **Smoke verified end-to-end:** setup → enable (TOTP 200, backup codes returned) → status `enabled=true, backup_codes_remaining=10` → re-login returns challenge (no cookies) → verify with TOTP 200 (full session) → verify with backup code 200 (count drops to 9) → replay burned backup code 401 → disable 204 (status enabled=false, codes=0). Backend container image rebuilt to bake `pyotp` into requirements.
- [ ] **MFA mandatory for admin/manager** — config flag + login enforcement (today opt-in for all roles)
- [ ] **MFA secret at-rest encryption** — currently plaintext base32 in `users.mfa_secret`; production should use envelope encryption via a KMS key
- [x] **Password reset** email flow (token + expiry) — done 2026-05-30. `PasswordResetToken` model (migration `f403f55cf0b4`), 1-hour TTL, single-use; POST `/api/auth/password-reset/request` returns 204 even for unknown emails (no enumeration), POST `/api/auth/password-reset/confirm` distinguishes 404 (never existed) from 410 (used/expired). Dev "delivery" via structured log line `password_reset.dispatched url=…`; SMTP is the prod swap. Frontend pages `/[locale]/forgot-password` + `/[locale]/reset-password/[token]` with dead-link UI; login page now links to forgot-password. 7 locales updated. Rate-limited at 3/min/IP on both endpoints.
- [x] Rate limit `/register` — done 2026-05-30. `@limiter.limit(f"{settings.rate_limit_register_per_minute}/minute")`, default 5/min/IP. Verified: hits 1–5 = 402 (Free plan cap), hit 6 = 429.
- [x] "Sessions" page: list active sessions, "log out other devices" — done 2026-05-31. Redis schema extended: `session:{session_id}` hash carries `{user_id, token, created_at, last_seen_at, user_agent, ip_address}` and `user_sessions:{user_id}` SET indexes them. `session_id = sha256(refresh_token)[:32]` — deterministic so we never need a reverse index, safe to expose since one-way from the secret. Three endpoints in `auth.py`: `GET /api/auth/sessions` (lists own sessions, flags `current=true` for the caller via refresh-cookie lookup), `DELETE /api/auth/sessions/{id}` (refuses 400 on own session — use /logout instead — and 404 on foreign/missing to avoid enumeration), `POST /api/auth/sessions/revoke-others`. `create_session` (replaces old `store_refresh_token`) does atomic pipeline write + captures UA (truncated 200 chars) + Starlette client IP. `/refresh` calls `touch_session` to bump `last_seen_at`. Frontend: `<SessionsCard>` on /settings — device icon (mobile vs desktop heuristic), browser+OS label parsed from UA, IP, signed-in/last-seen timestamps, current badge, revoke X, "Sign out N other devices" button. All 7 locales updated (`sessions.*` 11 keys). **Smoke verified:** 4 concurrent logins → list shows all 4 with correct current flag → DELETE foreign session 204 → its /refresh now 401 → revoke-others returns `{revoked: 3}` → list down to 1 (current).
- [x] Constant-time email lookup in `/login` — done 2026-05-30. Always runs `verify_password` (even on missing user, against a precomputed dummy hash) so the bad-email path doesn't return faster than the bad-password path. Verified: bad-email = 563ms, bad-password = 466ms (both bcrypt-bound).

#### Database & migrations
- [x] **Alembic** configured (async env.py reading `app.config`), baseline migration generated + DB stamped (2026-05-30) — see ADR-012
- [x] Replace `Base.metadata.create_all` in lifespan with `alembic upgrade head` (run in compose `backend.command` before uvicorn; lifespan only logs the current revision)
- [x] Partial unique indices on `(organization_id, lower(email)) WHERE deleted_at IS NULL AND email IS NOT NULL` for Lead and Customer — migration `ddd83138c832`. Tenant-scoped (same email allowed across orgs), case-insensitive, excludes deleted (so re-importing a trashed contact works). User skipped: no soft-delete on User today + email is already globally unique. Verified: case-folded `DUP@EXAMPLE.COM` collides with existing `dup@example.com` (currently surfaces as 500 from uncaught `IntegrityError` — UX nit, follow-up: catch and return 409).
- [x] Composite `(organization_id, stage, created_at DESC)` on Lead (mirrors existing `idx_deals_org_stage_updated` on Deal); partial `(organization_id, {owner_id|assignee_id}) WHERE deleted_at IS NULL` on Lead/Customer/Deal/Task for "my open records" — all in migration `ddd83138c832`.
- [x] `SoftDeleteMixin` (2026-05-31). Marker mixin in `models.py` carrying the `deleted_at` column; Lead/Customer/Deal/Task inherit it. Global filter wired in `database.py` via `do_orm_execute` event + `with_loader_criteria(SoftDeleteMixin, lambda cls: cls.deleted_at.is_(None), include_aliases=True)`. Auto-excludes deleted rows from EVERY SELECT (incl. eager + lazy relationship loads, joined aliases). Trash routes opt out per-statement via `.execution_options(include_deleted=True)` (constant `_SHOW_DELETED` in trash.py). Dropped 12 redundant `.where(Model.deleted_at.is_(None))` calls across leads/customers/deals/tasks/dashboard. Smoke-verified: GET endpoints exclude deleted, GET single deleted → 404, /trash sees them via opt-out, restore + hard_delete + empty_trash all work.
- [x] `(organization_id, expected_close_date) WHERE deleted_at IS NULL AND stage NOT IN ('won','lost')` partial index on Deal for forecast queries — migration `ddd83138c832`. Predicate keeps the index small (only open pipeline; realised stages excluded).
- [x] **UX nit — DONE 2026-06-04:** the partial-unique email index (`uq_leads_org_email_live` / `uq_customers_org_email_live`) now surfaces as a friendly **409** ("A {lead|customer} with this email already exists in this workspace") instead of a raw 500. Shared helper `app/api/_errors.py::raise_for_duplicate_email(exc, entity)` matches the `_org_email_live` constraint suffix and **re-raises any other `IntegrityError`** so genuine failures (FKs, other indices) are never masked. Wired into create (`flush`) **and** update (`commit`) on both leads and customers, each with a preceding `db.rollback()`. ruff + format clean; backend hot-reloaded healthy. Follow-up: a pytest case asserting the 409 belongs in the test round (left to the in-flight test workstream).

#### Tests
- [x] pytest infra (2026-06-01): `pytest==8.3.3` + `pytest-asyncio==0.24.0`; `backend/pytest.ini`; `backend/tests/conftest.py` with two-engine split — runtime QueuePool (RLS GUC survives commits) for the app + a SYNC psycopg2 engine for fixture seed/teardown (loop-agnostic; no asyncpg loop-binding issues). Session-scoped TestClient (one anyio BlockingPortal for the whole suite); per-test `clean_db` autouse fixture wipes `pytest-*` namespaced rows + resets slowapi limiter; factories for `test_org`, `other_org`, `admin_user`, `other_user`, `foreign_user`; `CsrfAwareClient` wrapper auto-injects `X-CSRF-Token` on mutating requests. Backend container image rebuilt with pytest deps baked in. **Required a refactor first:** the two `@app.middleware("http")` decorators in `main.py` (csrf, request-context) were converted to pure ASGI middleware classes (`CSRFMiddleware`, `RequestContextMiddleware`) registered via `app.add_middleware(...)` — the old `BaseHTTPMiddleware` pattern is incompatible with TestClient's BlockingPortal + asyncpg pool. Real-app smoke confirmed no regression: cookies + CSRF 403 + X-Request-ID header still work end-to-end.
- [x] Backend: auth happy path + ownership negative cases (cross-user 403) — `tests/test_auth.py` (7 tests: login sets 3 cookies, unknown email 401, wrong pwd 401, /me requires auth, /me with cookie, logout clears cookies + re-auth 401, CSRF-required-on-mutating). `tests/test_ownership.py` (5 tests: non-owner cannot mutate 403, non-owner CAN read, admin bypass ownership, cross-org returns 404 not 403 on GET/PATCH/DELETE, random UUID 404 sanity).
- [x] Backend: smoke test every CRUD endpoint — `tests/test_crud_lead.py` (2 tests: full lifecycle create→list→get→patch→soft-delete→trash→restore→hard-delete; trust-boundary check that `organization_id` in body is ignored). **Coverage gap:** only Lead is exercised; Customer/Deal/Task/Dashboard follow the same patterns but aren't yet tested. Add per-resource lifecycle tests as a follow-up.
- [x] Backend: audit log fires for each mutation — `tests/test_audit.py` (3 tests: lead.create + lead.update + user.login each leave an audit row with correct actor_id + organization_id). **Coverage gap:** doesn't yet assert every audit `action` value across the API surface. Follow-up: parametrize over the full action vocabulary.
- [x] Per-resource lifecycle tests (Customer / Deal / Task incl. full Trash flow) — done 2026-06-10, `tests/test_crud_lifecycles.py` (6 tests: 3 lifecycles mirroring `test_crud_lead.py` create→list→get→patch→soft-delete→trash→restore→hard-delete, with the strict If-Match contract baked in — missing→428, stale→412, version bumps on PATCH and deal /move; + parametrized organization_id trust-boundary over customer/deal/task). Dashboard has no lifecycle (read-only aggregate) — not applicable.
- [x] Audit coverage matrix — `tests/test_audit_matrix.py`. Base matrix (lead/customer/deal/task full lifecycle incl. trash restore/hard_delete) landed 2026-06-04; widened 2026-06-10 with non-trash-able resources (company/product/tag: create→update→soft_delete), polymorphic note lifecycle, `trash.empty`, and the security surfaces (invite create/revoke, api_key create/revoke, team create/update/delete) — 12 tests. External-dependency call sites (billing/whatsapp/imports/e-sign) stay with their dedicated module suites by design.
- [x] Frontend: Vitest for `lib/auth.ts`, `lib/api.ts` interceptor — done 2026-06-04 (commit `9d90322`). Vitest (jsdom) configured; `tests/auth.test.ts` (13 tests: readCookie present/missing/url-decode/prefix-collision, getToken sentinel/null, isExpired, listener bus) + `tests/api.test.ts` (16 tests: request headers + CSRF mirroring, 200/204/4xx/text-fallback responses, the full 401 single-flight refresh+retry flow incl. concurrent coalescing, login form-encoding + 429 mapping). 29/29 green. CI step enabled in `frontend.yml`. Gotcha: scope the rollup override to `@sentry/nextjs` — a global `overrides.rollup` pin breaks Vite's `./parseAst` export.
- [x] Frontend: Playwright for register → login → create lead → score → logout — done 2026-06-04. `playwright.config.ts` (runs against the already-running stack; no `webServer` since the API/worker/LLM can't be spun up by Playwright) + `e2e/smoke.spec.ts`, split into two tests: (1) **core golden path** register→signout→login→create lead→logout — deterministic, ~36s, the per-PR CI gate; (2) **AI scoring** create lead→score→assert "Priority:" — gated behind `SCORE_E2E=1` (skipped in CI) because the inline Ollama call takes ~156s and varies run-to-run. Hydration gotcha: `next dev` wires onSubmit/onClick only after React hydrates, so each interaction is fronted by a hydration gate (register: wait for the "Strong" strength label; app-layout pages: wait for the header email after `me()` resolves). Seat-cap note: every plain signup joins `default-workspace` (Free caps 2 seats) — a fresh stack fits the single core-test register; dirty local DBs can 402.

#### Observability
- [x] **Sentry** on backend + frontend — done 2026-06-01. Backend: `sentry-sdk[fastapi]==2.18.0`, `app/sentry_setup.py::init_sentry()` called in `main.py` BEFORE `FastAPI(...)` so the ASGI integration wraps from outside. Gated by `SENTRY_DSN`; empty = no init = zero overhead. `send_default_pii=False` plus a project-specific `before_send` hook that scrubs sensitive headers (Authorization, Cookie, Set-Cookie, X-CSRF-Token) and body keys (password*, *_token, mfa_secret, code). `traces_sample_rate` configurable per env (default 0.1). Frontend: `@sentry/nextjs==^8.40.0`, `src/sentry/init.ts` dynamic-imports the SDK ONLY when `NEXT_PUBLIC_SENTRY_DSN` is set (zero bytes shipped when disabled). `<SentryBoot/>` client component in `[locale]/layout.tsx` fires init once on mount. Source-map upload skipped intentionally (would require `SENTRY_AUTH_TOKEN` in CI; tracked as a follow-up).
- [x] Prometheus metrics — done 2026-06-01. `prometheus-client==0.21.0`. `app/metrics.py`: `REQUEST_COUNT` Counter labelled by method/route/status + `REQUEST_LATENCY` Histogram labelled by method/route (11 buckets 5ms→10s). `PrometheusMiddleware` is pure-ASGI (mirrors CSRF/RequestContext refactor); uses the matched route template (`scope["route"].path`) instead of the rendered path to cap cardinality. `GET /metrics` (hidden from OpenAPI) returns the exposition format; `/metrics` itself excluded from instrumentation to avoid self-referential rate calcs.
- [x] Audit log UI — done 2026-06-01. `GET /api/audit` (admin+manager only via `require_roles`); filters `actor_id`/`action` ILIKE/`entity_type`/`since`/`until`; limit≤200; aliased User join denorms actor email+name (no N+1). Org scope: own-org rows OR `org_id IS NULL` rows whose actor is in the current org (so user.login etc. surface). Frontend `/[locale]/(app)/audit/page.tsx`: filter form, paginated table (50/page), code-pill for action, truncated metadata, sidebar entry under `nav.audit` (not role-gated client-side; surfaces friendly "admin/manager only" on 403). 7 locales (`audit.*` 17 keys + `nav.audit`).
- [x] Extend `/ready` to ping Redis + LLM — done 2026-06-01. Returns `{status, components: {db, redis, llm}}`. Required (db + redis) down → overall `down` + HTTP 503. LLM is best-effort: `ollama` does a TCP-level probe of `/api/tags`; `anthropic` just checks the API key is non-empty (deeper probes would burn quota); unknown providers mark `degraded`. Per-component dict so monitoring can attribute outages without re-probing.
- [ ] **Sentry source-map upload** (follow-up): wire `withSentryConfig` in `next.config.ts` + `SENTRY_AUTH_TOKEN` in CI for un-minified stack traces in production.
- [ ] **Grafana dashboard JSON** committed to repo so a fresh env sees request rate + p95 latency + error rate by route out of the box.

#### CI/CD
- [x] GitHub Actions backend — `.github/workflows/backend.yml` (2026-06-01). Path-filtered, concurrency-cancel. Postgres + Redis service containers; `crm_app` runtime role spun up by `create_crm_app_runtime_role` migration. Steps: `pip install` (cached), `ruff check`, `ruff format --check`, `alembic upgrade head` (validates the full migration chain end-to-end), `pytest`, `pip-audit --strict`. **Re-greened 2026-06-03 (the workflow stops at the first failing step, so blockers surfaced one at a time):** (1) ruff — added `allowed-confusables = ["×"]` to `pyproject.toml` (keeps RUF001 homoglyph detection but allows the intentional multiplication sign in line-item copy), `ruff check --fix .` (I001 + F401), `ruff format .` (19 files of pre-existing drift); (2) once ruff passed, pip-audit then failed on `jinja2 3.1.4` (3 CVEs) → bumped to 3.1.6. Full suite 261/261 with both bumps; pip-audit clean (2 ignored = TD-28/29). `pyproject.toml` configures ruff with line-length=100, py312 target, rule set `E,W,F,I,B,UP,RUF,C4,TID`; per-file ignores let `tests/` use long lines + `assert`. Initial codebase ruff sweep: 100 issues, 82 auto-fixed by `--fix`, remaining 18 fixed manually (B904 raise-from on billing/deps, RUF005 list-concat in logging_setup, RUF012 ClassVar in conftest, E501 line splits in models/billing/ai_*, E741 `l`→`row` in tests). `ruff format` reformatted 29 files. Real-app smoke + pytest 17/17 still green. **Two more blockers surfaced once the lint/audit steps passed and CI actually reached the later steps:** (a) the storage/FileAttachment tests had no S3 to talk to — GitHub Actions `services:` can't pass MinIO its required `server /data` command, so MinIO is started as a `docker run -d` step (commit `1ed0dfa`) with a health-poll on `/minio/health/live`, and the job env gained `S3_ENDPOINT_URL`/`S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY`/`S3_BUCKET`; (b) `alembic upgrade head` failed against CI's fresh Postgres with `type "plan" does not exist` — the empty-baseline bug, fixed in `1c8b98c` (see TD-1b). The persistent dev volume had hidden both; CI's from-zero run is what exercised the full migration chain.
- [x] GitHub Actions frontend — `.github/workflows/frontend.yml` (2026-06-01). Path-filtered, concurrency-cancel. Steps: `npm ci` (lockfile-strict), `npm run lint` (eslint), `npx tsc --noEmit`, `npm run build`, `npm audit --production --audit-level=high` (HIGH+ in runtime deps block; dev-only vulns informational). Vitest step is live as of 2026-06-04 (`npm run test -- --run`, see Tests §).  **Fixed 2026-06-03:** the lint step had been failing on EVERY run because there was no ESLint config at all — `next lint` then drops into an interactive "Strict/Base" prompt that hangs/fails in non-interactive CI. Added `frontend/.eslintrc.json` (`extends: next/core-web-vitals`) + `eslint@^8.57.1` & `eslint-config-next@15.5.18` devDeps (lockfile regenerated). `npm run lint` now exits 0 (only pre-existing `<img>` warnings). `next lint` deprecation tracked as TD-45. Two more blockers then surfaced behind lint: (a) `tsc --noEmit` failed on 3 long-standing marketing type errors — `comparison-section.tsx` passed `variant="fade-right"/"fade-left"` which weren't in `RevealVariant` (added both as real directional-fade variants in `reveal.tsx`, faithful to author intent — they'd been rendering with NO animation), and `dashboard-carousel.tsx` accessed `.highlight` on a union where only one card had it (annotated `COLUMNS` with `highlight?: boolean`); (b) `npm audit --production --audit-level=high` flagged `rollup` (CVE-2026-27606 RCE) pulled in transitively via `@sentry/nextjs`'s build-time webpack plugin — fixed with a `package.json` `overrides` pin to `rollup 3.30.0` (clean patch within the installed 3.29.5's major; clears both the npm-audit HIGH and the same CVE in the Docker image). (c) `next build` then failed its static-prerender pass: the `register`, `billing`, and `pricing` pages call `useSearchParams()` at the top of a `"use client"` component, which forces a CSR bailout and errors the build unless wrapped in a Suspense boundary. Fixed in `e3c007a` by extracting a tiny `SearchParamWatcher` component (`@/components/search-param-watcher`) that isolates `useSearchParams()` inside its own `<Suspense fallback={null}>` and pushes the value out via an `onValue` callback — so the host page keeps static prerendering instead of de-opting the whole route to client-side rendering.
- [x] Secret scanning — `.github/workflows/security.yml` (2026-06-01). Two jobs: `gitleaks` (PR + push, weekly full-history sweep via cron) and `trufflehog` (full history, complementary rule set; verified+unknown results). gitleaks gets PR-comment perms to flag leaks inline.
- [x] Container scanning — `.github/workflows/docker.yml` (2026-06-01). Matrix over backend + frontend (`fail-fast: false` so one image's result never cancels the other's). PR runs build+scan only (no push). main/tag pushes to GHCR. Trivy scans HIGH+CRITICAL with `ignore-unfixed=true`. Cache via `type=gha,scope=<component>,mode=max` so repeat builds are fast. **Fixed 2026-06-03:** Trivy had been failing on both images. Backend: one runtime-reachable HIGH — `weasyprint 62.3` SSRF (CVE-2025-68616) — **upgraded** to 68.0 (pydyf→0.12.1, +tinyhtml5; the old "62.3↔0.10.0" pin only forbade bumping pydyf *under* 62.3, not bumping weasyprint itself — all 6 `test_pdf.py` render tests pass on 68.0). Frontend: 11 HIGH, all dev-toolchain transitives (node-tar/glob/minimatch/cross-spawn) that only ship because the image is a dev container (TD-44) — suppressed in root `.trivyignore` with per-CVE justifications (mirrors the pip-audit allowlist convention). The remaining failures were base-image OS-package CVEs, addressed two ways in commit `600c264`: (1) `backend/Dockerfile` now runs `apt-get upgrade` to pull patched OS packages, and (2) Trivy was briefly made report-only (`exit-code: "0"`) to unblock `main` while the base-image CVEs were being patched. Once both images were confirmed clean (verified locally 2026-06-03 by building from the current Dockerfiles and scanning: backend 0 HIGH/CRITICAL after `apt-get upgrade`, frontend 0 with the `.trivyignore` allowlist) the scan was **split into a real gate + a report**: a `Trivy scan (gate)` step with `format: table` + `severity: HIGH,CRITICAL` + `exit-code: "1"` (table honors the severity filter for the exit code, so only HIGH/CRITICAL hard-fail — see gotcha (a) below), and a separate report-only `Trivy scan (SARIF report)` step (`format: sarif`, `exit-code: "0"`, `if: always()`) that feeds the upload. The `upload-sarif` step is kept but marked `continue-on-error: true` — code-scanning upload needs GitHub Advanced Security, which this private repo doesn't have ("Resource not accessible by integration"); the SARIF is still retained as a build artifact. **Gotchas:** (a) the SARIF format makes the trivy-action evaluate exit-code against ALL severities, not just `--severity HIGH,CRITICAL`; (b) the SARIF format also hides the CVE table from CI logs — to see findings, run `trivy image --severity HIGH,CRITICAL --ignore-unfixed <img>` locally (via **PowerShell**, not Git-Bash, which mangles the `-v "${PWD}/.trivyignore:/.trivyignore"` mount path) or read the GH Security tab.
- [x] Docker image build + push on tag — same workflow. Tag strategy: `:edge` on main (mutable "newest known-good"), `:vX.Y.Z` on semver tag (immutable), `:latest` ONLY on real release tags (never main). PR builds skip GHCR login.
- [ ] **Staging environment + post-deploy smoke** — infra-level, depends on the host (Vercel/Railway/Fly/etc); deferred until hosting is chosen. The smoke spec when it lands: `curl /ready` → expect 200 with all three components OK; tagged Playwright `@smoke` suite hitting login + create lead.
- [x] CI must block on type errors / failing tests / vulns ≥ HIGH / invalid migrations / lint errors — covered by the workflows above. Branch protection on `main` (require all checks to pass) is a one-time repo setting, not in the YAML.

**Bonus dropped in alongside:**
- `.env.example` brought up to date (added `APP_DATABASE_URL`, refresh TTL, register/password-reset rate limits, frontend Sentry vars).
- `backend/pyproject.toml` with ruff config — first lint/format gate in the repo.

#### Domain models (true-CRM gaps)
These are the modules every serious CRM has and we don't.

- [x] **Activity model** — done 2026-06-01. Append-only ledger DISTINCT from `audit_logs` (audit = security/compliance, activity = user-facing timeline; curated `ActivityType` vocabulary so the UI can render icons + i18n labels). Polymorphic by `entity_type + entity_id` (no DB FK — lets future Quote/Contract join the timeline without a schema change). Migration `dd5318916104`: `activities` table + composite `(organization_id, entity_type, entity_id, created_at DESC)` index for the "give me the timeline for this entity" query + explicit `GRANT` to `crm_app`. `app/activities.py` service mirrors `record_audit` (called in the same session, caller commits). Wired into `leads.py`: `create` → `created` activity, `update` → `stage_change` (with `{from,to}` metadata) OR `updated` (with field list), `score` → `ai_scored` (with score/priority). `GET /api/activities?entity_type=&entity_id=` (read-only, org-scoped, paginated, JOIN actor for denorm name/email). Frontend `<ActivityTimeline />` on `/[locale]/(app)/leads/[id]`: icon per type, localised label that builds from metadata for structured types (stage_change → "Stage: new → qualified") and falls back to `content` for free-form types (call, meeting, …). 7 locales (`activity.*` 18 keys). Customer/Deal wiring + Note-add UI + "log a call" entry-point are follow-ups. **Mixin refactor along the way**: extracted `SoftDeleteMixin` from `app/models.py` to a new `app/mixins.py` to break a circular import that the new model surfaced (env.py imports models → models imports Base from database → database tries to import the mixin from the half-loaded models module). Zero regressions: 17/17 pytest, /api/activities smoke shows 3 ordered rows (created → stage_change → updated) with correct metadata, dev pages render 200.
- [~] **Activity wiring follow-ups**: customer.create/update + deal.create/update/move now emit activities (2026-06-03, `test_activity_wiring.py`, suite 139/139). Customer detail page wired with Notes/Attachments/Activity panels. STILL OPEN: deal `score` activity; "Add note" UI entry-point on the timeline (depends on Note model); no deal detail page exists (deals live in pipeline kanban) so deal panels not surfaced in UI.
- [x] **Note model** — done 2026-06-01. Per-user markdown notes on Lead/Customer/Deal, distinct from the legacy single-field `notes` scratchpad. Migration `31c9a3466f9c`: `notes` table (id, organization_id, author_user_id, entity_type, entity_id, body Text, soft-deletable via `SoftDeleteMixin`) + partial composite `(org, entity_type, entity_id, created_at DESC) WHERE deleted_at IS NULL` + explicit GRANT to `crm_app`. Endpoints `POST/GET/PATCH/DELETE /api/notes` in `app/api/notes.py`: list by entity, create (also emits `note_added` Activity with first 80-char preview as content + records audit), patch (`ensure_can_mutate` against author OR admin/manager), soft-delete (same ownership rule). Frontend `<NotesPanel />` on `/[locale]/(app)/leads/[id]`: compose textarea + post, list newest-first with author + relative time + "(edited)" marker, inline edit, delete with confirm. 7 locales (`notes.*` 11 keys). Customer/Deal pages get the same panel for free once they're wired (next round). **Gotcha caught**: `from __future__ import annotations` + `-> None` return on a `DELETE` returning 204 trips FastAPI's "Status code 204 must not have a response body" assertion — the future-annotations import makes `None` resolve to a JSON-serialisable type at introspection time. Fix: drop the return annotation on the delete handler (documented with a comment).
- [ ] **Note v2 (follow-ups)**: render full markdown via `react-markdown` (today body is plain `whitespace-pre-wrap`); @-mentions (depends on Notification model); attachments (depends on FileAttachment model). Plug `<NotesPanel />` into customer/deal detail pages.
- [x] **FileAttachment model** — done 2026-06-01. S3-compatible storage (MinIO sidecar in docker-compose; swap endpoint to AWS S3 / R2 in prod with zero code change). `boto3==1.35.60` wrapped in `asyncio.to_thread` (sync SDK in thread pool — simpler than aioboto3, sufficient for ~MB attachments). `app/storage.py`: `ensure_bucket()` (idempotent, called from lifespan startup), `put_object/delete_object/presigned_download_url` (5-min TTL with `Content-Disposition: attachment; filename=…` override so the download saves with the original filename instead of the UUID). Migration `e05d0dcd743e`: `file_attachments` (id, org_id, uploader_user_id, entity_type, entity_id, filename, content_type, size_bytes, sha256, storage_key) + partial composite `(org, entity_type, entity_id, created_at DESC) WHERE deleted_at IS NULL` + GRANT to crm_app. Endpoints `POST /api/attachments` (multipart upload, 25 MB cap, sha256 computed, blob → S3, row + `file_attached` activity + audit), `GET ?entity_type=&entity_id=` (list), `GET /{id}/download` (returns presigned URL JSON; SPA redirects), `DELETE /{id}` (soft-deletes row + HARD-deletes blob from bucket so storage is freed — trade-off accepted: restoring a soft-deleted attachment would require re-uploading). Storage key layout: `org-{org_id}/{entity_type}/{entity_id}/{att_uuid}` (tenant-prefixed for blast-radius containment). `lifespan` calls `ensure_bucket()` with try/except — backend boots even when MinIO is down, attachments fail at upload time with a clear message. Frontend: `<AttachmentsPanel />` with file input + list + download (via presigned URL window.location) + delete with confirm; mime-icon heuristic (image/text → specialised icons). 7 locales (`attachments.*` 9 keys + 2 new `activity.typeFileAttached/typeFileRemoved`). Activity timeline learned `file_attached`/`file_removed` types with Paperclip icon. **Smoke verified end-to-end from inside container** (Git Bash mangles `/tmp` paths so curl couldn't open the file from the host): upload returns row with correct sha256, list shows it, download URL fetches the file contents back from MinIO with original filename, delete 204 + list `[]`. Pytest 17/17 still green.
- [ ] **Virus scan webhook** (P3 follow-up): hook post-upload to a ClamAV or VirusTotal callback; quarantine the row if `scan_status != 'clean'`.
- [ ] **Presigned-PUT direct-from-browser** (P2 hardening): bypass the API for the upload bytes path entirely — frontend gets a signed PUT URL + claim endpoint binds the resulting key to the entity.
- [x] **Team model** + `team_id` on User/Lead/Deal — done 2026-06-01. Migration `94990b0118ae`: `teams` table (id, org_id, name, slug, soft-deletable) + `team_id` nullable FK on `users`, `leads`, `deals` (`ON DELETE SET NULL` — hard team delete keeps records alive; soft team delete clears `team_id` on members + records via app-layer SQL UPDATEs in the endpoint since FK SET NULL only fires on actual row delete). Slug uniqueness per-org via partial unique index `(org, slug) WHERE deleted_at IS NULL` so a re-created same-named team reclaims the slug. 5 endpoints in `app/api/teams.py`: GET list (any member; includes member roll for chip rendering), POST create (admin/manager only, 409 on slug clash with friendly message instead of raw IntegrityError), PATCH rename/re-slug, DELETE soft-delete (clears team_id on users + leads + deals), POST `/members` add, DELETE `/members/{uid}` remove. Lead/Deal list endpoints gained a `?team_id=` filter. Lead/Deal schemas extended with `team_id` field (caught a Pydantic silent-drop bug — create accepted `team_id` in JSON but pydantic threw it away because the schema didn't declare it; smoke verified the field is now round-tripped). Frontend `<TeamsCard />` on /settings (admin/manager only via `canManage` prop; backend role check is the real gate). 7 locales (`teams.*` 12 keys with ICU pluralisation on `memberCount`). **Smoke verified end-to-end**: create team → assign kalle → list shows member_count=1 → create lead with team_id → filter `?team_id=` returns 1 → 409 on duplicate slug → soft-delete team → direct DB check confirms `team_id` cleared on lead while lead itself stays alive. Pytest 17/17 still green.
- [ ] **Team v2 follow-ups**: round-robin assignment (Redis cursor per team for "next owner"); user-picker UI for adding team members from /settings (today add-member is API-only since there's no GET /api/users yet); team chips on Lead/Deal list rows + detail headers; team filter in the leads/deals list UI.
- [x] **Pipeline + PipelineStage models — Phase 1** done 2026-06-01. Models `Pipeline(SoftDeleteMixin, Base)` (id, org_id, kind ENUM lead|deal, name, slug, is_default) + `PipelineStage(SoftDeleteMixin, Base)` (pipeline_id, name, slug, position, probability%, is_won, is_lost). Migration `3639bde75ea7`: both tables + partial unique `(org, kind, slug) WHERE deleted_at IS NULL` on pipelines and `(pipeline, slug) WHERE deleted_at IS NULL` on stages + GRANT to crm_app. `app/pipelines.py` service: `get_or_seed_default_pipeline(db, org_id, kind)` — first call materialises a "Default lead funnel" (7 stages mirroring legacy LeadStage enum) + "Default sales funnel" (6 stages mirroring DealStage), so the admin UI is never empty + the Phase 2 backfill is a simple slug-join. 5 endpoints in `app/api/pipelines.py`: GET list (auto-seeds both kinds, optional `?kind=` filter), GET detail (with stages eager-loaded), POST create empty pipeline (admin/manager, 409 on slug clash), PATCH rename + reconcile stages in-place (incoming list with `id=null` → insert, present id → update, missing id → soft-delete — single endpoint instead of three for the SPA drag-reorder + inline rename + delete-stage flow), DELETE soft (refuses default since auto-seed would just re-create it). `is_default=true` PATCH demotes the previous default within the same kind. Frontend `<PipelinesCard />` on /settings (admin/manager gated): create form (lead|deal selector + name), per-pipeline expand to inline stage editor (name + probability + won/lost checkboxes + add/remove rows), set-default + delete buttons, default badge with star icon. 7 locales (`pipelines.*` 23 keys). **Smoke verified**: GET auto-seeds 2 defaults (lead 7 stages, deal 6 stages, correct probabilities + won/lost flags), create custom pipeline returns 201, PATCH stage reconcile 200, delete default 400 (refused with friendly message), delete custom 204. Pytest 17/17 green. **Bug caught**: `seeded_kinds = {k for k in [KIND_LOOKUP[kind]] if kind}` eagerly evaluated `KIND_LOOKUP[None]` before the `if` filter ran → KeyError on every list call without `?kind=`. Fixed by replacing with a plain conditional.
- [ ] **Pipeline Phase 2** (next round): add `pipeline_stage_id` nullable FK on Lead/Deal; backfill from existing enum via slug join (`UPDATE leads SET pipeline_stage_id = (SELECT id FROM pipeline_stages s JOIN pipelines p ON s.pipeline_id=p.id WHERE p.organization_id=leads.organization_id AND p.kind='lead' AND p.is_default AND s.slug=leads.stage::text)`); migrate /api/leads + /api/deals filters from `stage == enum` to JOIN through pipeline_stage; reskin kanban to read stage columns from the active pipeline; eventually drop the LeadStage/DealStage enum columns once nothing references them.
- [x] **Notification model** (in-app inbox, v1) — done 2026-06-01. Per-user, org-scoped row carrying `type` (curated slug — `task_assigned`, `lead_stage_changed`, `deal_stage_changed`, `deal_won`, `deal_lost`, `note_mention`, `file_attached`), `title`, `body`, `link_url` (locale-less relative path; SPA prefixes the active locale), `actor_user_id` (denormalized for "Alice assigned you a task" rendering), `metadata_json`, `read_at`. Migration `1d4dca386af7` with TWO hot-path indices: partial `(user_id, created_at DESC) WHERE read_at IS NULL` for the bell badge + full `(user_id, created_at DESC)` for the inbox list. `app/notifications.py::notify()` helper mirrors `record_audit/record_activity` (same-session insert, caller commits — failed mutations never leave phantom bells). Wired into 2 events for v1: `leads.update` bells the lead owner when SOMEONE ELSE moves the stage; `tasks.create` + `tasks.update` bell the assignee when assignee changes AND the assigner isn't the assignee themselves (self-bell = spam). 5 endpoints in `app/api/notifications.py`: GET list (`?unread=true|false` filter + pagination), GET `/counts` (cheap COUNT against the partial index — pollable from the bell), POST `/{id}/read` (idempotent), POST `/mark-all-read` (zeros the bell, returns new counts in one round-trip), DELETE `/{id}`. Frontend `<NotificationsBell />` in app header: badge with unread count (caps at "99+"), dropdown opens on click + fetches full list on first open (only counts polled until then), click on row marks read + navigates to `link_url` prefixed with the active locale, "Mark all read" button shown only when unread>0, per-row dismiss (X) on hover, polling every 60s + on tab focus, paused while tab hidden. 7 locales (`notifications.*` 5 keys). Email fanout, @-mentions and 90-day retention pruning are P2/P3 follow-ups. **Smoke verified end-to-end**: GET counts=0 + list=[] when empty → seed 2 unread via SQL → counts=2 → list shows both newest-first → unread filter narrows → mark one read 200 → counts=1 → mark-all-read returns {unread:0} → delete 204 → final list has 1 survivor. App runs at db_revision `1d4dca386af7`; pytest regress for this round was blocked by a transient Docker Desktop bind-mount I/O error on `/app` (the app itself stayed healthy; symptom is `docker compose exec` losing FS access while the running uvicorn keeps serving) — a backend container restart will recover. Pytest 17/17 was last green on the pipelines round prior.
- [ ] **Notifications v2 follow-ups**: SMTP email fanout (depends on a worker — outbox + Arq/Celery is the P1 path); @-mention parser in NotesPanel emits `note_mention` notifications; 90-day retention prune cron; SSE/WebSocket push instead of 60s polling; multi-org bell unification (today the bell scopes to the active org).

#### Background jobs / worker process
- [x] **Arq chosen + `worker` service live** — done 2026-06-01 (ADR-006). Separate `worker` container in `docker-compose.yml` runs `arq app.worker.settings.WorkerSettings` off the same image/env as the backend; `_startup` builds one long-lived async engine per worker. `max_tries=5`, `job_timeout=60s`, `keep_result=3600s`.
- [x] `worker` service added to `docker-compose.yml`
- [x] First jobs: **lead AI scoring** (`score_lead`, backs `POST /score-async`), **outbox drain** (`drain_outbox` cron), **webhook delivery** (`deliver_webhook`), **email send** (`send_email` — DONE 2026-06-01, ADR-017). Customer summarization + audit shipping not yet ported.
- [x] Job idempotency: `score_lead` is safe to repeat (read-only scoring + overwrite); outbox/webhook subscribers dedupe by `event_id`.
- [ ] **Dead-letter queue + alert** — arq has no built-in DLQ (after `max_tries` the job is dropped + logged). The *outbox* has a DLQ-by-cap (`attempt_count >= OUTBOX_MAX_ATTEMPTS=10`, surfaced via `/api/outbox?status=failed`), but the arq job queue itself still needs an `arq:queue:dead` list + an alert on depth > 0. (P2)

#### Outbox + event bus (foundation for automations + webhooks)
- [x] **`outbox_events` table** — done 2026-06-01 (migration `22779df17c2e`). `record_event(db, event_type, organization_id, payload)` in `app/events.py` appends a row in the SAME session as the domain mutation, so it commits-or-rolls-back with it — never a phantom event.
- [x] **Worker drains** (`drain_outbox`, cron every 5s) → claims a batch with `FOR UPDATE SKIP LOCKED` + exponential backoff (`occurred_at + 2^attempt s`) → dispatches to in-process subscribers (`app/events_dispatcher.py`) AND fans out to outgoing webhooks → marks `processed_at`.
- [x] Event types (v1 subset): `lead.created`, `lead.stage_changed`, `deal.created`, `deal.stage_changed`, `deal.won`, `deal.lost`. **Follow-up:** `task.overdue`, `customer.created`, `user.invited` not emitted yet.
- [x] Unlocks reliable webhooks (live — see below). Automation actions + search indexing are downstream consumers that can now register as subscribers.
- [ ] **Lag alert** (per §10): `/api/outbox?status=failed` already surfaces DLQ rows; still need an alert when the oldest unprocessed `occurred_at` is > 60s behind.

#### Webhooks (outgoing)
- [x] **Webhook outgoing (Phase 1)** — done 2026-06-01. Builds on the Outbox foundation (registered as a wildcard `@subscribe(EventType.x)` against every event type via `_fanout_to_webhooks`). `WebhookEndpoint` model + `WebhookDelivery` log (migration `dc830726fed0`) — neither RLS'd (same reasoning as outbox; admin endpoint filters by `organization_id`). HMAC-SHA256 signing in `app/webhook_sign.py`: header format `X-CRM-Signature: t=<unix>,v1=<sha256_hex>` (Stripe-style); `verify_signature()` enforces ±5min replay window via `max_age_seconds`. Per-delivery retry via arq `Retry(defer=2^attempt)` capped at 240s → 8 tries total (~17min wall time). Auto-pause: `consecutive_failures >= 10` flips `paused_at = now()` and short-circuits remaining retries; unpause via PATCH resets the counter. Body shape: `{event_id, event_type, organization_id, payload}` JSON-encoded with `sort_keys=True` for stable signature recomputation. Headers also send `X-CRM-Event-Id` + `X-CRM-Event-Type` for receiver-side dedup convenience. CRUD endpoints `/api/webhooks` (admin-only POST/PATCH/DELETE; admin+manager GET) — secret returned ONCE on create (`WebhookEndpointCreated`), never on subsequent reads. URL guard rejects loopback hostname / loopback IP / private RFC1918 IP / non-http(s) scheme; lenient on unresolvable hostnames (might be VPN-only). 18 new pytest (signing roundtrip + tamper detection + stale TS + secret strength + CRUD happy paths + cross-org 404 + URL guard + slug validation + delivery list + role gate). Real-app smoke verified end-to-end: POST /api/leads → outbox drain → fanout → arq `deliver_webhook` job → POST signed with HMAC → 405 from /health → `webhook.failed` row + retry @ 2s → next retry @ 4s; `WebhookDelivery` rows captured `attempt, status='failed', response_code, latency_ms (~20ms), error='HTTP 405'`. 44/44 suite green.
- [ ] **Webhook follow-ups (P2/P3)**: `POST /{id}/rotate-secret` (intentional + audited; today secret rotation requires a recreate); `POST /{id}/test` manual ping endpoint; receiver-side reference middleware as a docs example; admin UI page on `/settings`; `webhook_deliveries_total` + `webhook_delivery_duration_seconds` Prometheus metrics; retention prune for `webhook_deliveries` (90d default); test isolation for `deliver_webhook` success/auto-pause paths (currently smoke-only — see comment in `tests/test_webhooks.py`).

#### Imports / Exports — DONE 2026-06-03 (ADR-016 slice; leads + customers)
- [x] CSV/XLSX upload → S3 → import job → background validation → row-level error report. `app/imports/` (parsers: BOM/`;`-sniff CSV + openpyxl read-only XLSX, `MAX_ROWS=50k`; spec: header→field resolution w/ aliases + Pydantic row models). `POST /api/imports` uploads to S3 + creates `ImportJob` (pending) + enqueues `process_import`; SPA polls `GET /api/imports/{id}`. Worker job is 3-phase (claim → parse off-conn → one atomic write txn), idempotent (completed job is a no-op; retry redoes whole file). `error_report` JSONB capped at 1000 rows; whole-file failure (unreadable/missing required col) → `failed`, per-row errors → `completed` with counts.
- [x] Dedupe by `(org_id, lower(email))` then `(org_id, normalized_phone)`. `create` mode skips matches, `upsert` overwrites non-empty cells. Index built once from a narrow `(id,email,phone)` projection; within-file dupes match via `flush()`.
- [x] **Formula-injection prevention on export (TD-22)**: `app.exports.csv_safe` prefixes any cell starting with `=`, `+`, `-`, `@`, `\t`, `\r` with a single quote. Runs on EVERY exported cell.
- [x] Streaming exports: `stream_csv` is a keyset-paged (`created_at,id`) async generator; `GET /api/exports/{entity}?format=csv` returns a `StreamingResponse` (get_db session survives the stream).
- [x] Per-tenant import guards: 1 concurrent (pending/processing → 409) + rolling-24h daily cap (`import_daily_cap=50` → 429). Frontend: `[locale]/imports` page (upload + mode + poll + template download), Export-CSV buttons on leads/customers, sidebar entry, 7-locale i18n. Tests: `test_imports_parsing.py` (36), `test_imports_api.py` (14), `test_imports_worker.py` (6) — suite 241/241.

#### Transactional email (workstream — DONE 2026-06-01, see ADR-017)
Invites and password-reset used to only `log.info("…dispatched", url=…)`. Solved ONCE as a workstream (provider abstraction + worker delivery + localized templates), not per-feature.
- [x] Provider behind `app/email/sender.py::send(*, to, template, locale, ctx, dedupe_key)` — swappable via `EMAIL_PROVIDER`: `console` (dev default, logs, never raises), `resend` (httpx → api.resend.com), `smtp` (stdlib smtplib in a thread, STARTTLS). `get_provider()` factory; unknown → console fallback. SMTP self-host path is the EU/CH data-sovereignty answer (ADR-014).
- [ ] Deliverability: SPF + DKIM + DMARC on a dedicated sending subdomain; bounce/complaint webhook → suppression list. **(prod-infra follow-up — not code)**
- [x] Localized HTML+text templates (7 locales en/pt/de/fr/it/rm/es), rendered server-side in `app/email/render.py`. HTML part uses an **autoescaping** Jinja env (XSS-in-inbox defense — `<script>` in an org name is escaped; verified by `test_email.py`); text part is a separate non-escaping env. Branded inline-CSS table layout.
- [x] Sent through the worker (Arq `send_email` job) so a slow provider never blocks the request; inherits the worker's `max_tries=5` backoff. Callers (invite create, password reset) enqueue best-effort (try/except, URL still logged as recovery fallback) so a Redis hiccup never 500s a user action. Deferred import breaks the email↔worker import cycle.
- [x] **Smoke-verified end-to-end 2026-06-01:** enqueued an invite (locale=pt, org_name with `<script>`) → worker rendered + delivered via console provider → `{status: sent, provider: console}`; HTML escaping confirmed. `tests/test_email.py` (10 tests, all green): invite+reset render all 7 locales, HTML escapes, unknown-locale→en, pt-BR→pt, unknown-template raises, console never raises, resend/smtp raise without config.
- [x] Unblocks: invite dispatch, password reset (both wired). Still TODO downstream: notification fanout, contract send, dunning emails (consume the same `email_service.send`).
- [ ] **DLQ follow-up:** after `max_tries` the `send_email` job is dropped + logged (arq has no built-in DLQ); a real dead-letter list is tracked in `worker/settings.py` as a P2.

#### Documents, PDF & Contracts (sales-critical gap — see ADR-016)
The Activity model was already designed to accept a future `Quote/Contract` (its polymorphic `entity_type`).
- [x] **PDF generation foundation — DONE 2026-06-02.** Shared capability: HTML-template → PDF via WeasyPrint (pure-Python, pinned `weasyprint==62.3` ↔ `pydyf==0.10.0` — pydyf ≥0.11 broke the `Stream.transform` API 62.3 calls; native Pango/HarfBuzz/fonts libs added to the Dockerfile). `app/pdf/` = `render.py` (Jinja2 autoescaping env + `money` filter, `render_html`/`render_pdf`), `templates/base.html` + `deal_summary.html`, `store.py` (`store_pdf_attachment` → sha256 + S3 put + `FileAttachment` row, caller commits). Worker job `generate_deal_pdf(ctx, deal_id, org_id)` sets the RLS GUC, reads the deal, renders **off the event loop via `asyncio.to_thread`** (WeasyPrint is sync CPU-bound ~20s; running it inline starved the Redis heartbeat + `drain_outbox` cron and threw a spurious `CancelledError` — fixed), stores the attachment, audits `deal.pdf_generated`. Endpoint `POST /api/deals/{id}/pdf` → 202 + arq enqueue with a 5-min dedupe key (double-click → `{queued:false}`). Generated PDFs reuse the existing attachment list + presigned-download surface (zero new download code). 6 tests in `test_pdf.py` (markup/money/autoescape + one real `render_pdf` → `%PDF-`). Suite 91/91. E2E smoked: login → create deal → enqueue → worker renders → download returns `%PDF-1.7`. **Follow-ups:** render latency ~20s even warm (fontconfig/Pango setup per call — investigate caching a `FontConfiguration`); retry re-renders into a NEW attachment row (acceptable v1); `file_attachments` not RLS'd (TD-42).
- [x] **`Quote` entity + line items, versioned — backend DONE 2026-06-02.** `quotes` + `quote_line_items` tables (hand-written migration `b7f3a2c1d4e8`, both ENABLE+FORCE RLS with the standard `app.current_org_id` GUC policy + `crm_app` grants; `quote_line_items` carries a denormalised `organization_id` so it's RLS-scoped at the row level rather than via the join — avoids a TD-42-style gap). Polymorphic to Deal **and** Customer (both nullable FK SET NULL). **Versioned:** `number` (e.g. `Q-000007`, zero-padded, MAX-based + per-org `pg_advisory_xact_lock` for race safety, partial-unique `(org, number, version) WHERE deleted_at IS NULL` backstop) is stable across revisions; `version` increments on re-issue. **State machine** (`app/api/quotes.py`): `draft —send→ sent —accept→ accepted` / `—decline→ declined`; only `draft` is mutable, illegal transitions → 409. **Resend** (`POST /{id}/resend`) deep-copies a non-draft quote into a fresh `draft` at `version+1` and sets the prior row's `superseded_by` (draft → 409). **Totals never trusted from the client** — `app/services/quotes.recompute_totals` recomputes line totals + subtotal + tax (`tax_rate` is a %, e.g. 7.7) server-side on every create/update. CRUD + transitions + `POST /{id}/pdf` (202 + arq enqueue, 5-min dedupe, worker `generate_quote_pdf` renders `templates/quote.html` off the event loop → `FileAttachment` entity_type=`quote`, reusing the existing attachment/download surface). Audit (`quote.create`/`send`/`accept`/`decline`/`resend`/`pdf_generated`) + outbox events (`quote.created`/`sent`/`accepted`/`declined`). **20 tests** in `test_quotes.py` (totals math, CRUD, full state machine incl. illegal transitions, versioning/supersede, ownership 403, cross-org 404). Suite **111/111**. E2E smoked: create → send → enqueue → worker rendered `quote-Q-000001-v1.pdf` (11.6 KB `%PDF`) in ~12s, audit + outbox + attachment all confirmed. **Still open:** `Contract` entity, template merge-field editor, e-signature.
- [x] **Template engine with merge fields — DONE 2026-06-03.** Admin/manager-editable `document_templates` (hand-written migration `c3d4e5f6a7b8`, ENABLE+FORCE RLS + standard `app.current_org_id` policy + `crm_app` grants; soft-delete; partial-unique `(org, lower(name)) WHERE deleted_at IS NULL`; `doc_type` enum = `contract` today; `is_default` with single-default-per-org demotion on toggle). **Render engine `app/documents/merge.py` is deliberately NOT a template language** — a fixed allow-list catalog (`FIELD_CATALOG`, 14 tokens: today, organization.name, contract.number/title/value/currency/effective_date/end_date, customer.name/company/email/address, owner.name, line_items) + a plain regex `{{ token }}` pass against a resolved `dict[str,str]`. No expression eval, no attribute walking → **SSTI out of scope by construction** (vs. the WeasyPrint Jinja env which renders *our* HTML, not user input). Unknown tokens pass through verbatim so a typo stays visible in the draft. `{{ line_items }}` is the one computed token — `build_contract_context` rolls the source quote's lines into a newline-delimited bullet block (`- desc — qty × unit = total`, `.normalize():f` to drop Numeric(12,3) trailing zeros; survives both the PDF `white-space: pre-line` and the detail page `pre-wrap`). **Materialize-at-apply:** rendering freezes into `Contract.body` (NOT late-bound); `applied_template_id` FK is provenance only. `app/api/document_templates.py`: `GET /fields` (catalog → picker, any member), CRUD (list/get any member; create/patch/delete require_manager), all audit-logged. `contracts.py`: `POST /{id}/apply-template/{tid}` (draft-only 409, ensure_can_mutate) + `from-quote?template_id=` query. **Frontend:** `document-templates-card.tsx` in Settings (field picker inserts `{{ token }}` at cursor; create/edit/default/delete); apply-template `<select>` on the contract detail page (draft only) and on the accepted-quote create-contract block; `api.ts` typed (`DocumentTemplate*`/`MergeField` + 7 methods); i18n `documentTemplates.*` across all 7 locales (reworded to avoid literal `{{ }}` which breaks ICU MessageFormat). **18 tests** in `test_document_templates.py` (render purity incl. no-eval/unknown-passthrough/whitespace, line-items block, catalog match, fields endpoint, CRUD, default-toggle demotion, sales_agent 403, apply renders/409/404, from-quote roll-up, cross-org 404). Suite **185/185**, tsc clean (only the two pre-existing marketing errors remain). **Still deferred:** per-doc-type catalog (today contract-only); a real browser click-through smoke.
- [x] **E-signature on quotes — backend DONE 2026-06-02.** `signature_requests` table (hand-written migration `f1a2b3c4d5e6`, ENABLE+FORCE RLS + denorm `organization_id`, soft-delete, partial-unique `sign_token`). Provider seam mirrors the email pattern: `app/signing/` = `providers.py` (`SignatureProvider` Protocol + `EnvelopeHandle`; `ManualProvider` signs in-app via an opaque `{org_hex}.{secret}` token link, no vendor/secret; `Skribble`/`Scrive` stubs RAISE until a vendor account is wired — a legal-signature path fails loud, never degrades to click-to-accept), `service.py` (`store_signature_artifact` → audit-trail JSON to S3 as a `FileAttachment`, mirrors the PDF store). `app/api/signatures.py`: authed CRUD + state machine `drafted —send→ sent —view→ viewed —sign→ signed` (`/decline`, `/cancel`; illegal → 409), **unauthenticated signer surface** (`GET`/`POST /sign/{token}` — RLS GUC recovered from the token's org prefix before the lookup, since the table is RLS'd unlike `org_invites`), and an **HMAC-verified inbound `/webhook`** (`X-CRM-Signature`; 503 unconfigured, 400 bad/missing sig; org recovered from the signed body). **Completion side effect:** signing a request whose quote is still `sent` auto-accepts the quote (audit `quote.accept via=signature` + outbox `quote.accepted`). Audit + 5 outbox event types (`signature.requested/viewed/signed/declined/cancelled`). **21 tests** in `test_signatures.py` (create-from-sent-quote, 409 on draft source, send mints token, manual view→signed→quote-accepted, decline, cancel, webhook valid/bad-sig/unconfigured/unknown-envelope, ownership 403, cross-org 404). Suite **137/137**. **Frontend DONE 2026-06-02:** public signer surface at `[locale]/sign/[token]/page.tsx` (phase machine loading→ready→signed/declined/gone/notfound; 410→"already done", other errors→"invalid link"; prefills typed-name from `signer_name`; renders quote number/title/total via `AuthShell`) + a top-level `sign/[token]/page.tsx` redirect shim → `/{defaultLocale}/sign/{token}` (the `{org_hex}.{secret}` token's dot makes next-intl middleware treat it as a static file and skip the locale prefix, so the shim re-adds it). `SignaturePanel` on the quote detail page (request form only when quote is `sent`; per-row Send→copies minted link / Copy-link→re-fetches `signing_url` since the list omits it / Cancel with confirm). `lib/api.ts` typed (`SignatureStatus`/`SignatureRequest`/`SignatureSignContext` + 9 methods). i18n `signatures.*` block across all 7 locales. tsc clean for the e-sign files; routes smoke 200 + shim 307. Bonus: moved `STATUS_VARIANT` out of `quotes/page.tsx` into `quotes/status.ts` — a `page.tsx` may not have extra named exports, it was a latent `next build` type error. **Still deferred:** real vendor (Skribble/Scrive) API wiring incl. moving the create-envelope network call to a worker job (the stubs are the seam — wiring is a config change, needs an account); `countersigned` declared but not yet reachable; a real browser click-through smoke (verified at route + integration-test level only).
- [x] Timeline states: drafted → sent → viewed → signed (countersigned deferred — needs a vendor that supports it).
- [x] **E-signature on contracts — DONE 2026-06-03.** Widened the signing envelope so a `signature_request` signs a **quote XOR a contract** (ADR-016). Schema design (user-chosen): typed nullable FKs `quote_id`/`contract_id` + DB CHECK `(quote_id IS NOT NULL) <> (contract_id IS NOT NULL)` (migration `b2c3d4e5f6a7`) — preserves CASCADE integrity for the legal record over a polymorphic `entity_type/id`. `SignatureRequestCreate` validates exactly-one-document (422 otherwise); `SignatureSignContext` generalised from `quote_*` to `document_{type,number,title,total,currency}`. `signatures.py`: `create_signature_request` branches quote/contract (requires source `sent`, else 409; 404 on missing/deleted), `_load_document_summary` + `_doc_ref` generalise the signer view + every event payload, `list` gains a `contract_id` filter. **Completion side effect:** signing a request whose contract is still `sent` advances it to `signed` (`_maybe_sign_contract`, mirrors the manual contract sign transition + `contract.sign via=signature` audit + `contract.signed` outbox). **Frontend:** `SignaturePanel` generalised to `{documentId, documentType, documentStatus}` and mounted on both the quote and contract detail pages; sign page + `api.ts` switched to `document_*`; i18n `sign.quoteLabel` → `sign.documentLabel.{quote,contract}` across all 7 locales. **6 new tests** (create-from-sent-contract, 409 on draft contract, 404 missing, exactly-one 422, sign→contract-signed, contract_id filter) + renamed-field fixups. Suite **167/167**. tsc clean (only the two pre-existing marketing errors remain). **Still deferred:** real vendor wiring (unchanged from quotes); browser click-through smoke.

#### Public API & API keys (Premium sells "API + Webhooks" — no plan exists)
Auth is browser cookie + CSRF, which can't do server-to-server, and routes aren't versioned.
- [x] **`ApiKey` model + bearer path — DONE 2026-06-03.** `api_keys` table (hand-written migration `e5f6a7b8c9d0`, ENABLE+FORCE RLS + standard `app.current_org_id` policy + `crm_app` grants; soft-revoke via `revoked_at`, not a row delete, so the audit trail survives). Token shape `crmk_{org_hex}_{secret}` (`secrets.token_urlsafe(32)`); **at rest we store only `sha256(token)`** (mirrors `WebhookEndpoint.secret`) — a leaked DB row can't be turned back into a usable key. The plaintext is returned **once** on create (`ApiKeyCreated.token`); reads expose only `display_prefix` (`crmk_a1b2c3d4…wxyz`). Scopes = `read`/`write` JSON list (default least-privilege `["read"]`). `app/api_keys.py` = pure helpers (`mint_token`/`hash_token`/`build_display_prefix`/`parse_org_id`/`encode_scopes`/`decode_scopes`/`required_scope_for_method`). **Bearer dependency `app/api_auth.py` (`require_api_key` → `ApiPrincipal`)** is a path distinct from the cookie path: parse the org out of the token → set the RLS GUC → look the key up **under RLS** (so a cross-org hash match returns zero rows → 401, can't reach another tenant), reject revoked/expired, load the creator `User` (401 if the user was deleted [SET NULL] or deactivated — a deliberate v1 coupling so no orphaned credential outlives its human owner), scope-check the verb (read for GET/HEAD/OPTIONS, write otherwise → 403), rate-limit, throttled `last_used_at` touch. The key **acts on behalf of its creator** so audit/activity/ownership all behave identically to the cookie path. Management CRUD `app/api/api_keys.py` (`/api/api-keys`, admin-gated cookie+CSRF, same trust model as webhooks): mint (audit `api_key.create`), list/get (admin+manager), soft-revoke (admin, idempotent, audit `api_key.revoke`). **Frontend** `api-keys-card.tsx` in Settings (admin-gated like invites; create with name/write-toggle/optional-expiry → shows the secret once with copy-to-clipboard; lists keys with prefix/scopes/last-used/expiry + revoked & expired badges greyed out; revoke with confirm), `api.ts` typed (`ApiKey`/`ApiKeyCreated`/`ApiKeyCreate` + 4 methods), i18n `apiKeys.*` across all 7 locales.
- [x] **Versioned routes (`/api/v1/…`) + deprecation policy — DONE 2026-06-03.** `app/api/v1.py` is a **thin adapter, not a re-implementation** — it authenticates with the bearer dependency then delegates to the SAME handler functions the cookie-authed `/api/leads` and `/api/customers` routes call (they're plain async funcs; passing explicit args bypasses `Depends`), so audit/activity/outbox/ownership/org-scoping all behave identically regardless of credential. v1 surface (user-chosen): **leads + customers**, list/get/create for both, `CursorPage` envelope reused. `app/api/versioning.py` `stamp_version` dependency stamps `X-API-Version: v1` on every response and carries the RFC 8594 deprecation machinery (`_SUNSET`/`Deprecation`/`Sunset`/`Link` headers) wired but dormant until a sunset date is set — the policy is documented in the module docstring.
- [x] **Per-key Redis rate limit — DONE 2026-06-03.** Fixed-window counter in `_enforce_rate_limit` (`apikey_rl:{key_id}:{epoch//60}`, INCR + 70s expire, **fail-open** on Redis error like SlowAPI's in-memory fallback so a Redis blip doesn't take the API offline), separate from the per-IP login limit. Budget = `settings.api_key_rate_limit_per_minute` (default 120); over-budget → 429 + `Retry-After: 60`. **20 tests** in `test_api_keys.py` (management CRUD + secret-once + hash-at-rest + role/cross-org guards + revoke idempotency; bearer happy path + version header + scope-enforcement 403 + missing/garbage/unknown/revoked/expired 401 + rate-limit 429 + org isolation + last_used recorded). Suite **261/261**, ruff clean, tsc clean (only the 2 pre-existing marketing errors). Browser click-through NOT yet smoked (verified at route + integration-test level only).
- [ ] Ship the OpenAPI + a generated SDK; wire `redocly lint` (already in §11) as a CI gate. **DEFERRED 2026-06-03 (user-chosen):** ship runtime API + frontend + tests first; SDK/redocly tracked as a follow-up.

#### Search
- [x] **Full-text search via Postgres FTS (TD-13)** — done 2026-06-01. Migration `062fbc7b628d` adds a STORED generated `search_vector tsvector` column on `leads` + `customers` with weighted token contributions (`A` for first/last name, `B` for email + company, `C` for industry on customers). Follow-up migration `fb4c1a3697b9` refines the email tokenization via `regexp_replace(email, '[@.]', ' ', 'g')` BEFORE `to_tsvector`, so `founder@acmecorp.example` indexes as three tokens (`founder`, `acmecorp`, `example`) — searching for any one of them hits. GIN index `idx_{leads,customers}_search_vector` on the column. `simple` config (not `english`) because data is multilingual (7 locales). `?q=` filter on `GET /api/leads` and `GET /api/customers` now uses `search_vector @@ websearch_to_tsquery('simple', :q)` — Google-style multi-token AND, `"exact phrase"`, `-exclusion` all work. STORED generated columns are auto-maintained by Postgres on every write — zero app-layer bookkeeping. **Pytest 7 new** covering: first_name match / email match / company match / search_vector auto-updates on PATCH / `websearch_to_tsquery` AND semantics / cross-org isolation / customers smoke. Real-app smoke: GIN index exists + planner uses it under load (currently chooses Seq Scan on the 9-row dev table because it's cheaper at this size — correct planner behaviour, confirmed via EXPLAIN). 51/51 suite green.
- [ ] **Search v2 (P2 follow-ups)**: `pg_trgm` extension + similarity fallback for typo tolerance (e.g. "bratrice" → Beatrice); ts_rank surfacing in the response for relevance-sorted lists; deals search (currently no `q` param on /api/deals); index per-locale dictionary swap if the dataset becomes locale-uniform.
- [ ] Defer dedicated search engine (Meilisearch/OpenSearch) until > 1M records or ranking matters

#### Pagination + concurrency
- [x] **Cursor pagination** (`?cursor=...&limit=50`) — **DONE 2026-06-02 (TD-11)** on the unbounded table lists (leads/customers/quotes); `app/pagination.py` keyset helper + `CursorPage` envelope. Kanban/calendar/trash deliberately stay full-fetch (they need the whole set). Limit/offset is gone from those three.
- [x] **Optimistic locking on Deal (Phase 1)** — done 2026-06-01. Migration `4d3d59906702` adds `version int NOT NULL DEFAULT 0` to `deals`. `DealOut` exposes it. `PATCH /api/deals/{id}` and `POST /api/deals/{id}/move` accept `If-Match: <int>` header (RFC 7232 quoted form `"7"` also works), 412 Precondition Failed on mismatch, 400 on malformed value, and v1 leniency: missing header logs a warning but proceeds (gives the frontend a rollout window before strict mode). Server bumps `version += 1` on every successful mutation. Pytest 8 new (fresh deal starts at 0, no-header lenient path, correct match, stale 412, quoted form, malformed 400, /move also enforces, concurrent edit scenario one-wins-one-loses). 59/59 suite green.
- [ ] **Optimistic locking on Task + Customer** — copy the Deal pattern + same migration shape. Not done yet because Deal is the highest-collision target (sales reps editing during meetings); Task/Customer follow.
- [ ] **Strict mode**: flip `_check_if_match` to require the header once the frontend echoes `version` on every PATCH; currently logs `deal.if_match_missing` as the rollout signal.
- [ ] Stable sort key (always `(updated_at DESC, id DESC)`) — same order twice for the same data.

#### Rate limiting beyond /login
- [ ] `/api/auth/register` (5/min/IP, already P1 but flag here)
- [ ] `/api/assistant/chat` (30/min/user — LLM cost protection)
- [ ] `/api/leads/{id}/score` (10/hour/user — LLM cost protection)
- [ ] Imports endpoint (1 concurrent/org)
- [ ] Webhook receiver endpoints (per-org bucket)
- [x] **Move from SlowAPI's in-process limiter to Redis-backed** — done 2026-06-01. `app/rate_limit.py` passes `storage_uri=settings.redis_url` + `key_prefix="rl:"` + `in_memory_fallback_enabled=True` to `Limiter(...)`. `limits[redis]` (transitive via slowapi) provides the `RedisStorage` backend. Verified: 6th /login in a minute returns 429; Redis shows `LIMITS:LIMITER/rl:/<ip>//api/auth/login/5/1/minute` key. `limiter.reset()` propagates to Redis (pytest fixture still works — 51/51 green). In-memory fallback means a Redis outage degrades to per-replica counting instead of refusing every request.

#### CRM-specific metrics to track
- [ ] p95/p99 latency for: leads list, customers list, pipeline board, search, dashboard, AI scoring
- [ ] Slow query count (`pg_stat_statements`)
- [ ] Queue depth + job failure rate (Arq)
- [ ] Webhook delivery success rate + p95 latency
- [ ] LLM call: tokens in/out, cost, error rate, fallback rate (Anthropic → Ollama)
- [ ] Login failures per IP + rate-limit triggers (security signal)
- [ ] Per-org request count + bytes (noisy-neighbor signal)

---

### 🟨 P2 — Quality of life

#### Frontend DX
- [ ] **TanStack Query** — eliminate ~12 `useEffect(() => api.foo().then(setX), [])` patterns; gain cache, retries, mutations
- [ ] **openapi-typescript** — generate `Lead`, `Customer`, etc. from FastAPI's OpenAPI schema; kill drift between front/back types
- [ ] `<Skeleton>` on every list page during initial load
- [ ] Toast system (radix-toast or simple custom) for transient errors (assistant, mutations)
- [ ] Pagination UI on lists (backend already accepts `limit`/`offset`)
- [ ] Fix `react-hooks/exhaustive-deps` warnings throughout
- [ ] Replace `…` loading placeholders with proper spinners

#### AI
- [ ] Assistant chat: **stream responses** (SSE or fetch ReadableStream)
- [ ] Assistant chat: include **conversation history** in each request
- [ ] Customer summary: include open deals + recent tasks/notes in the LLM prompt (currently it gets only basic fields — junior smell)
- [ ] Per-user / per-org LLM token usage tracking
- [ ] Configurable temperature/max_tokens per use case

#### Performance
- [ ] N+1 audit: eager-load `owner` where listed (`selectinload(Lead.owner)`)
- [ ] Cache `/api/dashboard/stats` in Redis (60s TTL, invalidate on mutation)
- [ ] Trash list pagination (currently loads all soft-deleted rows)
- [ ] Switch `passlib + bcrypt` → `argon2-cffi` (remove the `(trapped) bcrypt version` warning at startup)

#### i18n quality
- [ ] CI script: assert all locale files have identical key set
- [ ] Pluralization: messages with counts should use ICU/`{count, plural}` syntax

#### API quality
- [ ] OpenAPI lint in CI (`redocly lint`) — block schema regressions
- [ ] Generate `openapi.yaml` artifact on every build; diff against previous to flag breaking changes
- [ ] **Contract testing** between frontend and backend (Pact or schema diff) — prevents the "back ships breaking change, front breaks silently in prod"

#### Synthetic monitoring
- [ ] External uptime probe hitting `/ready` + a tagged auth flow every 60s (UptimeRobot, Better Uptime, or self-hosted with Healthchecks.io)
- [ ] Probe a representative authenticated endpoint (`/api/dashboard/stats`) with a dedicated test account

#### Billing production hardening
- [ ] **Stripe webhook idempotency stress test** — replay the same event 10× and assert plan flips happen once
- [ ] **Webhook retry budget**: store the raw payload and processing error in `stripe_events` for forensics
- [ ] **Grace period**: when `customer.subscription.deleted` fires mid-period, keep plan active until `current_period_end` instead of immediately downgrading
- [ ] **Failed payment flow**: handle `invoice.payment_failed` — email the admin, show dunning banner, lock paid features after 3 retries
- [ ] **Proration UI**: when changing cycle (monthly→yearly), show the prorated charge before confirming
- [ ] **Tax**: enable Stripe Tax for EU VAT (auto MOSS/OSS) — once activated in Stripe dashboard, only env wiring is needed
- [ ] **Invoice emails**: configure Stripe to send hosted invoice emails (no engineering work, but check the box)
- [ ] **Currency switch**: today everything is EUR. When opening EU regions outside EUR (CHF, GBP), add a `currency` column to plan picker and create the matching Stripe Prices
- [ ] **Annual prorate-credit on cancel**: yearly subscribers who cancel mid-cycle currently lose remaining time; decide policy and document
- [ ] **Move plan/billing fields from `User` to `Organization`** — locked behind P0 multi-tenant work

---

### 🟦 P3 — Future phases (post-multi-tenant, per README roadmap)

- **RAG / Documents**: upload → chunk → embed in pgvector → grounded assistant with citations
- **Email integration**: IMAP/Gmail/Outlook sync, threads attached to customers, AI drafts
- **Omnichannel inbox**: WhatsApp Business Cloud API first (highest ROI in BR/LatAm), then Instagram Messaging + Messenger (shared Meta Graph + the existing webhook layer). `Conversation` + `Message` models polymorphic to Lead/Customer; media in S3. Gated by Meta Business verification + message-template approval (calendar-bound, weeks). **GTM note:** for a Lusophone/LatAm launch this is a P1 candidate, not P3 — WhatsApp is the primary sales channel there.
- **Calendar sync**: Google/Outlook events ↔ Task model
- **Automation builder**: visual workflows (trigger → condition → action) — runs on top of outbox/event bus from P1
- **GDPR**: per-user + per-org data export + right to erasure (cascade-aware), audit log redaction policy
- **Mobile**: React Native or PWA optimization

#### Advanced infra (when scale demands)
- **Database partitioning**: `audit_logs` and `activities` by month (`PARTITION BY RANGE (created_at)`). Drop old partitions instead of `DELETE`.
- **Read replicas**: route analytics queries (dashboard, reports) to replica; mutations stay on primary.
- **Per-tenant quotas**: enforce limits on API calls, AI tokens, storage. Noisy-neighbor isolation via Redis-backed token bucket per `org_id`.
- **Feature flags**: launchdarkly-style toggles for risky rollouts (Unleash self-hosted is the OSS path)
- **Canary deploys**: ship to 5% of traffic, watch error rate + p95, then 50%, then 100%
- **Shadow reads**: during migrations, run new + old query, compare, log divergences before cutting over
- **Backfill scripts with checkpoints**: large data ops resume from last successful batch on crash
- **Chaos testing**: periodically kill Redis/worker/LLM in staging; verify graceful degradation

---

## 4. Tech debt log

Items below are real debt, not new features. Listed once so we stop re-discovering them.

| ID | Item | Cost to fix | When |
| --- | --- | --- | --- |
| ~~TD-1~~ | ~~`Base.metadata.create_all` in lifespan~~ — **DONE 2026-05-30** (Alembic) | M | ~~P1~~ |
| ~~TD-1b~~ | ~~Baseline migration is empty (live DB stamped).~~ **DONE 2026-06-03** (commit `1c8b98c`). The `be40f9fed1a8_baseline` stub was populated with the exact pre-baseline schema (8 enums + users/customers/leads/deals/tasks/audit_logs/stripe_events + indexes/FKs), reconstructed by cloning the live `crm` schema into an isolated throwaway Postgres, stamping head, running the hand-written `downgrade()` chain back to baseline, and `pg_dump`ing the result. Issued as per-statement `op.execute` (asyncpg rejects multi-statement strings). Verified: fresh `alembic upgrade head` reaches head byte-identical to live dev; pytest 261/261. CI's fresh-Postgres `alembic upgrade head` now passes (had been failing at `bcac4a2cdbfa` with `type "plan" does not exist`). **Lesson:** an empty/stamped baseline means `upgrade head` from zero is never exercised — the persistent dev volume hid it; only CI's fresh DB caught it. | S | ✅ |
| TD-2 | Tokens in `localStorage` | M | P1 (cookies + CSRF) |
| TD-3 | `bcrypt` + `passlib` version warning | S | P2 (argon2 swap) |
| TD-4 | Soft-delete filter repeated everywhere | S | P1 (mixin) |
| TD-5 | Frontend/backend types duplicated by hand | M | P2 (openapi-typescript) |
| TD-6 | No N+1 protection on relationship loads | S | P2 |
| TD-7 | `…` as loading state | S | P2 (Skeleton) |
| TD-8 | Customer summary LLM call lacks context | S | P2 |
| TD-9 | Assistant chat no streaming, no history | M | P2 |
| TD-10 | Audit log has no UI surface | M | P1 |
| ~~TD-11~~ | ~~Lists paginate with `limit/offset`~~ — **DONE 2026-06-02.** Keyset (cursor) pagination on the unbounded table lists: **leads, customers, quotes**. `app/pagination.py` = `CursorPage[T]` envelope (`items`/`next_cursor`/`has_more`) + opaque base64 cursor of `(created_at, id)` + async `paginate()` using a row-value `tuple_(created_at,id) < cursor` keyset, order `created_at DESC, id DESC`, fetch `limit+1` to know `has_more` without a COUNT. Frontend: `Page<T>` type + `?cursor` arg + a "Load more" button (7-locale `common.loadMore`); analytics/dropdown consumers (dashboard, reports, pipeline/new) use new `listAllLeads`/`listAllCustomers` page-walking helpers so they still get every row. **Deliberately NOT paginated:** deals (kanban, sorted `stage,sort_index`), tasks (calendar, `due_date nullslast`), trash (polymorphic union) — they need full datasets. 5 tests in `test_pagination.py`; suite 116/116. HTTP-smoked: limit=2 → 2 pages descending no-overlap, bad cursor → 400. | M | ✅ |
| ~~TD-12~~ | ~~No `version` column → concurrent edits on same Deal silently overwrite~~ — **DONE 2026-06-01** (Deal only; Task/Customer follow). | S | ~~P1~~ |
| ~~TD-13~~ | ~~Search uses `LOWER(...) LIKE '%q%'` → full table scan~~ — **DONE 2026-06-01** (FTS via stored tsvector + GIN on leads + customers; email pre-tokenized via regex). pg_trgm fuzzy match deferred to P2. | S | ~~P1~~ |
| ~~TD-14~~ | ~~No background worker — AI scoring blocks the API request~~ — **DONE 2026-06-01** (Arq `worker` service; `score_lead` / `drain_outbox` / `deliver_webhook` jobs). | M | ~~P1~~ |
| ~~TD-15~~ | ~~Rate limiter is in-process (SlowAPI default) — wrong on multi-replica~~ — **DONE 2026-06-01** (Redis storage_uri + in-memory fallback). | S | ~~P1~~ |
| ~~TD-16~~ | ~~No outbox → automations/webhooks would lose events on crash~~ — **DONE 2026-06-01** (Phase 1, in-process subscribers). Webhook outgoing fanout in next round. | M | ~~P1~~ |
| TD-17 | Billing fields live on `User` (will need to move to `Organization`) | M | P0 (multi-tenant) |
| TD-18 | No file attachment story (no S3 client, no model) | M | P1 |
| TD-19 | No Activity timeline — CRM-critical for sales reps | M | P1 |
| TD-20 | One global pipeline — real customers want multiple pipelines per org | M | P1 |
| TD-21 | `pricing/catalog.py` is hardcoded — admin can't change prices without deploy | S | P2 |
| ~~TD-22~~ | ~~CSV export vulnerable to formula injection~~ — RESOLVED 2026-06-03: `app.exports.csv_safe` neutralises every cell (`= + - @ \t \r` → `'`-prefixed); covered by `test_imports_parsing.py` | S | DONE |
| TD-23 | Billing fields on `User` instead of `Organization` (single-tenant assumption) | M | P0 (multi-tenant migration) |
| TD-24 | No grace period on `subscription.deleted` — user is downgraded instantly | S | P1 (billing hardening) |
| TD-25 | No `invoice.payment_failed` handler — dunning is invisible | S | P1 (billing hardening) |
| TD-26 | Stripe webhook secret + price IDs live in `.env` — rotate them via secrets manager before prod | S | P1 (deploy) |
| TD-27 | Frontend reads recharts at request time; no SSR-safe wrapper — large bundle on first dashboard hit | M | P2 (dynamic import) |
| TD-28 | `starlette==0.49.3` still has PYSEC-2026-161 (fixed in 1.0.1). Needs `fastapi>=0.131` to allow `starlette>=1.0` — bigger bump than the 2026-06-01 security round; revisit when next FastAPI bump happens. Currently ignored in CI `pip-audit` with comment. | S | P1 (next dep round) |
| TD-29 | `pytest==8.3.3` has GHSA-6w46-j5rx-g56g (tmp-dir DoS on shared runners). Fixed in 9.0.3 but `pytest-asyncio==0.24.0` is incompatible with pytest 9; need to bump both together. Dev-only; ignored in CI `pip-audit`. | S | P2 |
| TD-30 | ~~**Money stored as `float`**.~~ **DONE 2026-06-02 (ADR-015).** All 9 money columns (`leads.budget`, `deals.value`, `quotes.{subtotal,tax_rate,tax_amount,total}`, `quote_line_items.{quantity,unit_price,line_total}`) migrated `double precision → Numeric` (hand-written migration `d9f1a2b3c4e5`). Models `Mapped[Decimal]`; `app/money.py` helper (`q2` half-up, `ZERO`); quote totals + `billing/catalog.py` + dashboard FX now exact Decimal arithmetic. Strategy: **Decimal in / float out** — input schemas use `Decimal` (Pydantic routes JSON float→Decimal via str, no binary tail), output schemas keep `float` so JSON stays clean numbers (frontend untouched). `audit.py`/`events.py` `_to_jsonable` gained a `Decimal→float` branch. Smoke: 3×9.99 + 1.5×10.10 @7.7% → 45.12/3.47/48.59 exact. 111/111. | S | ✅ |
| TD-31 | **`crm_app` DB password hardcoded** in a migration (`crm_app_dev_2026`). Must rotate via `ALTER ROLE` + secrets manager before any non-local deploy; update `APP_DATABASE_URL`. | S | P0 (deploy blocker) |
| TD-32 | **Customer PII sent to Anthropic (US)** for scoring/summary/RAG. Conflicts with the EU/Swiss data-residency selling point + GDPR Art. 44+ transfer. No redaction, no EU-region option, no per-tenant opt-out to local Ollama. | M | P1 — see ADR-014 |
| TD-33 | **GDPR erasure vs soft-delete vs append-only audit**: soft-deleted rows and immutable `audit_logs`/`activities` still hold PII. "Right to erasure" needs a hard-delete/anonymize path that keeps the immutable trail intact (opaque actor id + erase the PII projection). | M | P1 (before GDPR endpoints) |
| TD-34 | **No automated dependency updates** — CVEs are hand-patched (see 2026-06-01 hot-patch). Add Dependabot/Renovate + an SBOM + an AGPL license-compat check on new deps. | S | P2 |
| TD-35 | **No timezone policy.** A "calendar local-date" bug was already fixed reactively. Decide + document: store UTC, render in a per-user/per-org tz preference; tasks/due-dates/reminders must be tz-aware. | S | P1 |
| TD-36 | **Pricing model ambiguous**: `monthly_eur` is a flat number but the property is `yearly_eur_per_user` and the copy says "unlimited users". Flat-vs-per-seat changes revenue ~5×. Decide before live billing. | S | P1 (product + billing) |
| TD-37 | **No product analytics** (activation / retention / funnel). Ops observability (Sentry/Prometheus) ≠ product telemetry. Add PostHog (self-hostable, EU region) — you can't improve activation you don't measure. | S | P2 |
| TD-38 | **No onboarding / seed data.** A fresh org lands on an empty CRM (bad first impression). Add sample data toggle + an onboarding checklist + empty-state CTAs. | S | P2 (activation) |
| TD-39 | **No defined SLOs.** Alerts fire on "p95 regression" with no numeric target. Set explicit SLOs (e.g. list p95 < 300ms, 99.9% uptime) + an error-budget policy to drive thresholds. | S | P2 |
| TD-40 | **DR has no RPO/RTO.** §10 says "backups + tested restore" but no recovery targets, no PITR/WAL strategy, no encryption/retention, no restore runbook. Define RPO/RTO and drill it. | M | P1 (before paying customer) |
| ~~TD-41~~ | ~~**CI ruff/test gates have never actually run green**~~ — **CODE PORTION DONE 2026-06-02.** Cleared the ruff backlog: `ruff check .` → all pass (fixed UP017/I001/RUF019/F401/RUF100 auto + 3 RUF002 ambiguous `×`→`x` in docstrings manually); `ruff format .` reformatted 34 files (28 in `app/`, 6 in `tests/` — the committed tree had never been formatted); `.local` (pip --user dir, gitignored) added to ruff `extend-exclude`. Suite 85/85. The `tests/test_refresh_rotation.py` cookie-jar domain bug (`testserver` vs real `testserver.local` host-only key) was fixed 2026-06-01. **Remaining (not code):** turn on branch protection on `main` so the now-green gate is mandatory. **Lesson:** run the full CI gate locally before declaring green; "tests exist" ≠ "tests pass", and "lint configured" ≠ "lint passes". | S | ~~P1~~ → branch-protection toggle only |
| ~~TD-42~~ | ~~**`file_attachments` is not RLS'd**~~ — **DONE 2026-06-02** (migration `c8e4d3f9a1b2`, hand-written). ENABLE + FORCE RLS with the byte-identical `app.current_org_id` GUC policy as every other tenant table; the `GRANT` was already present from the table's create migration. Verified safe because every reader/writer already sets the GUC (API via `get_current_org_id`; PDF worker jobs via `set_current_org_id`, re-applied on the post-render write txn by the transaction-scoped begin-event). Direct `crm_app` battery: no GUC → 0 rows, GUC=A → 6, GUC=B → 1, cross-org SELECT → 0, cross-org INSERT → `new row violates row-level security policy`, own-org INSERT → ok. API smoke: quote attachments list still 200 under FORCE RLS. Suite 111/111. | S | ~~P1~~ |
| TD-44 | **Frontend Docker image is a dev container.** `frontend/Dockerfile` does `npm ci` (incl. devDependencies) + `CMD npm run dev` — so the whole build toolchain ships in the scanned image, dragging in a recurring class of dev-tooling CVEs (node-tar/glob/minimatch/cross-spawn, currently suppressed in root `.trivyignore`). Give it a multi-stage production build (`next build` → standalone output, no devDeps); then delete the `.trivyignore` dev-toolchain block. | M | P1 (deploy) |
| TD-45 | **`next lint` is deprecated** (removed in Next 16). `frontend/package.json` `lint` script + the frontend CI step still call it (works today, prints a deprecation notice, reads `.eslintrc.json`). Migrate to the ESLint CLI / flat config (`npx @next/codemod next-lint-to-eslint-cli .`) before the Next 16 bump. | S | P2 |
| TD-43 | **WeasyPrint render is ~20-30s even warm.** `generate_deal_pdf`/`generate_quote_pdf` render a one-page PDF in ~20-30s on every call, not just cold — points at fontconfig scanning / Pango setup per render rather than a one-time cache. **Partially mitigated 2026-06-02:** render is off the event loop (`asyncio.to_thread`) AND both jobs now read into a plain context dict and RELEASE the DB connection before rendering (read→render→store as 3 phases), so a render no longer pins a pooled connection and starves the small worker pool. The remaining work is the render *latency* itself: process-level cached `weasyprint.text.fonts.FontConfiguration` + trimming installed font packages. | S | P2 (perf) |

---

## 5. Architecture decisions (ADRs)

Compact ADRs. Add one whenever you make a non-obvious technical choice.

### ADR-001 — Permissive ownership
**Date:** 2026-05-28
**Decision:** `list`/`get` open to any authenticated user; `PATCH`/`DELETE` require owner or admin/manager.
**Why:** Less invasive than strict scoping; user's pre-tested flows keep working.
**Consequence:** `ensure_can_mutate` on every mutation. Multi-tenant (P0) will tighten this to per-org.

### ADR-002 — Stateless JWT, no revocation list
**Date:** 2026-05-28
**Decision:** HS256 access tokens; client discards on logout; server logs the event.
**Why:** MVP scope; revocation requires Redis blacklist.
**Consequence:** Stolen tokens stay valid until `exp`. P1 to add refresh + revocation.

### ADR-003 — `create_all` over Alembic for MVP
**Date:** 2025-Q4 (inherited)
**Decision:** Lifespan calls `Base.metadata.create_all`.
**Why:** Schema churn was too fast for migrations to be worth the overhead.
**Consequence:** Any model change in dev needs `docker compose down -v`. Migrate to Alembic before first paying customer (P1).

### ADR-004 — Audit log is best-effort, not transactional
**Date:** 2026-05-28
**Decision:** `record_audit` catches and logs failures; never raises.
**Why:** Auditing must not break user-facing operations.
**Consequence:** Lost audit on DB error is accepted; structlog still has it.

### ADR-005 — Ollama + Anthropic with bidirectional fallback
**Date:** 2025-Q4 (inherited)
**Decision:** `services/llm.py::chat_completion` tries the configured provider first, falls back to the other.
**Why:** Dev runs without an API key (Ollama free); prod can pin to Anthropic and still degrade gracefully.
**Consequence:** Both clients must be in the container. Acceptable cost.

### ADR-006 — Background jobs via Arq (not Celery)
**Date:** 2026-05-28
**Decision:** When P1 worker work lands, use [Arq](https://arq-docs.helpmanual.io/) (async Redis queue).
**Why:** Our stack is already async (asyncpg, httpx async client, FastAPI). Celery is sync-first and the async path is a second-class citizen; mixing sync workers with our async DB pool causes connection waste. Arq is small, async-native, Redis-backed (we already have Redis). RQ is even simpler but sync-only.
**Consequence:** Less mature than Celery's ecosystem. Acceptable for our scope. If we ever need cron-like complex scheduling beyond Arq's `cron_jobs`, evaluate `apscheduler` as a sidecar.

### ADR-007 — Outbox pattern for event publishing
**Date:** 2026-05-28
**Decision:** Mutations write to `outbox_events` in the same transaction; a poller in the worker drains and dispatches.
**Why:** Without this, "fire webhook on lead created" loses events whenever the dispatch fails after commit. Outbox guarantees at-least-once delivery without distributed-transaction pain.
**Consequence:** Subscribers must be **idempotent** (use `event_id`). Slight DB write amplification. The poller becomes a critical-path component (alert on lag).

### ADR-008 — PostgreSQL full-text first; dedicated search later
**Date:** 2026-05-28
**Decision:** Lead/Customer search uses a `tsvector` GIN index with optional `pg_trgm` fuzzy fallback. Defer Meilisearch/OpenSearch until > 1M rows per tenant or ranking matters for UX.
**Why:** One less moving piece. Postgres FTS covers 95% of CRM search needs (name, email, company). Adding a search engine doubles the ops surface.
**Consequence:** Limited ranking and language support. If a customer demands faceted search or non-Latin scripts at scale, revisit.

### ADR-009 — Multi-tenant via shared schema + RLS (defense-in-depth)
**Date:** 2026-05-28
**Decision:** Single Postgres database, single schema, `organization_id` on every tenant table, **plus** Row-Level Security policies. Application code still filters by org_id; RLS is a safety net.
**Why:** Schema-per-tenant doesn't scale past low hundreds of tenants (migration pain, connection multiplication). DB-per-tenant is enterprise-only. Shared schema + RLS is the modern default (Supabase, Neon).
**Consequence:** Every connection must `SET LOCAL app.current_tenant_id = '...'` at the start of the request (FastAPI dependency). Forgetting it = no rows visible (fails closed, which is what we want). Audit-log writes need a dedicated bypass policy.

### ADR-010 — Cursor pagination, not limit/offset
**Date:** 2026-05-28
**Decision:** Every list endpoint takes `?cursor=<opaque>&limit=N`. The cursor encodes the last `(updated_at, id)` of the previous page.
**Why:** `OFFSET 50000` is a full scan. With writes happening concurrently, offset-paginated pages also duplicate or skip rows. Cursor is stable.
**Consequence:** Cannot "jump to page 47". For CRM list/feed UX this is fine; admin reports may still need offset for now.

### ADR-011 — Stripe for billing, webhook as source of truth
**Date:** 2026-05-28
**Decision:** Standard and Premium go through Stripe Checkout. The `customer.subscription.*` and `invoice.*` webhooks update `User.plan` and friends. The signed webhook is the only path that flips a paid plan; `/api/billing/upgrade` is admin-only and bypasses Stripe (kept for demo/support/automated tests).
**Why:** PCI-DSS scope avoidance, EU SCA out of the box, multi-currency-ready, Customer Portal for self-serve management. Trusting the post-checkout redirect to mark a user paid would create a security hole — anyone could craft the URL. The webhook + idempotency table (`stripe_events`) is the only reliable signal.
**Consequence:** Local dev requires `stripe listen --forward-to localhost:8001/api/billing/webhook` to receive webhooks; without it, paid plans never activate. Documented in README. When STRIPE_SECRET_KEY is unset, `/checkout` returns 503 with a clear message and the UI shows a friendly banner instead of breaking.

### ADR-013 — Multi-tenant via `OrgMembership` junction + `User.last_active_org_id`
**Date:** 2026-05-30
**Decision:** A user belongs to N organizations through the `OrgMembership` junction table (composite PK on `(user_id, organization_id)` carrying its own `role`). The user's "current" org is stored on `users.last_active_org_id`, not in the JWT — switching orgs is a `PATCH /me` and does not require a token refresh. Tenant tables (Lead/Customer/Deal/Task) carry a NOT NULL `organization_id` FK; AuditLog carries a nullable FK so platform-level events (auth, webhook idempotency) don't need a synthetic org context.
**Why:** Per-org JWTs would mean a token reissue every org switch — extra complexity for marginal security gain when the membership table is the real ACL. The composite PK on memberships lets the same user be admin in one org and sales_agent in another (think: an MSP managing multiple customer workspaces). Keeping AuditLog's FK nullable avoids a synthetic "platform" org that polluted reporting.
**Consequence:** Billing fields still live on `users` until Phase 3 — every endpoint that reads `user.plan` will be refactored to `user.last_active_org.plan` before the columns drop, in a follow-up migration. Phase 6 (RLS) is the safety net: even if a future query forgets `.where(organization_id == current_org_id)`, the Postgres policies block the cross-tenant read. Cross-org access must return 404 (not 403) to avoid leaking which IDs exist in other tenants.

### ADR-012 — Alembic owns the schema (async env, compose-driven upgrades)
**Date:** 2026-05-30
**Decision:** All schema changes go through Alembic migrations stored in `backend/alembic/versions/`. The `env.py` uses the async template, pulls `DATABASE_URL` from `app.config.get_settings()`, and imports `app.models` so autogenerate sees every mapped class. `Base.metadata.create_all` is gone from the lifespan; the docker-compose backend service runs `alembic upgrade head && uvicorn …`, so migrations apply on every container start. The lifespan only logs the current `alembic_version` so the boot output names the live revision.
**Why:** Schema drift was breaking the dashboard each time we hand-`ALTER`ed columns. Without migrations, multi-tenant work (P0) would either wipe data on every model change or accrete a pile of `ALTER TABLE` SQL files no-one trusts. Alembic gives us reproducible up/down history, autogenerate diffs, and a single mechanism for prod deploys.
**Consequence:** First adoption used the empty-baseline-then-stamp pattern — the live DB was stamped at revision `be40f9fed1a8` (baseline) so Alembic recognises the existing schema without re-creating it. A fresh DB deploy requires writing a full-schema initial migration (or running the legacy `create_all` once + `alembic stamp head`) until we capture the full `op.create_table` set in a real migration. For now, fresh-DB onboarding still uses `create_all` then stamps — flagged as a small follow-up in §4 (TD-1b). Multi-replica deploys must move `alembic upgrade head` out of `backend.command` into a one-shot release job so replicas don't race the migration.

### ADR-014 — AI data residency: redact or localize PII before it leaves the tenant
**Date:** 2026-06-01 (proposed)
**Decision:** Before any customer PII reaches a hosted LLM (Anthropic, US), apply a per-org policy (`ai_pii_mode` / `ai_data_region`): (a) redact/pseudonymize identifying fields, (b) route sensitive tenants to local Ollama, or (c) use an EU-region inference endpoint. Default to redaction.
**Why:** The product's wedge is EU/Swiss data sovereignty (Romansh, AGPL, self-host). Silently shipping names/emails/notes to a US API contradicts that and is a GDPR Art. 44+ transfer concern. This is a *selling point*, not just compliance.
**Consequence:** Scoring/summary/RAG prompts need a redaction pass + a provider router keyed on the org policy. Local-Ollama tenants get lower AI quality — surface that trade-off in the plan. Also defend RAG against prompt injection on user-uploaded docs.

### ADR-015 — Money as integer minor units, never float
**Date:** 2026-06-01 (proposed) → **ACCEPTED & IMPLEMENTED 2026-06-02 (TD-30)**
**Decision:** Store every monetary amount (deal value, plan prices, invoice/quote lines) as `Numeric(12,2)` (rate/quantity scales differ) — never `float`. Carry an explicit ISO-4217 `currency` next to every amount.
**Why:** Binary floats can't represent `0.10` exactly; sums drift and rounding bugs in money destroy trust in a paid CRM.
**Consequence:** Migration `d9f1a2b3c4e5` converted all 9 amount columns; `app/money.py` (`q2` half-up + `ZERO`) is the shared helper. Wire format = **Decimal in / float out** (Pydantic float→Decimal goes via str so no binary tail; output stays clean JSON numbers). Multi-currency (CHF/GBP) is now a column add, not a refactor.

### ADR-016 — E-signature via a qualified EU/CH provider, not homegrown
**Date:** 2026-06-01 (proposed)
**Decision:** For legally-binding contracts, integrate a QES/eIDAS provider — **Skribble** (Swiss) or **Scrive** — rather than building signing in-house. A homegrown click-to-accept is allowed only for low-stakes consent (terms, opt-ins).
**Why:** A qualified electronic signature has legal weight in CH/EU that a checkbox + IP log does not, and self-certifying QES is out of scope. A provider is faster and defensible. Reinforces the Swiss positioning.
**Consequence:** Per-envelope cost + an external dependency on the signing path; inbound completion via the existing webhook layer. Store the signed PDF + the provider's audit trail in S3.

### ADR-017 — Transactional email as a provider-abstracted worker workstream
**Date:** 2026-06-01 (implemented)
**Decision:** One `app/email` package owns all transactional mail. A thin `EmailProvider` Protocol (`console` / `resend` / `smtp`) is selected by `EMAIL_PROVIDER` config; callers never touch a provider directly — they call `email_service.send(...)`, which enqueues an Arq `send_email` job. Rendering (`render.py`) is locale-aware (7 locales) with a **two-env Jinja split**: HTML autoescapes, text does not. Payloads on the queue are the raw `(to, template, locale, ctx)` so rendering lives in exactly one place (the worker) and the Redis payload stays small + JSON-serializable.
**Why:** Five+ features (invites, reset, notifications, contracts, dunning) need delivery; building it per-feature would fork the template/retry/provider logic. Putting send on the worker keeps a slow SMTP/API call off the request path; the provider Protocol keeps us free to run **self-hosted SMTP for EU/CH data sovereignty** (ADR-014) or a deliverability-first SaaS (Resend) without touching call sites. Autoescaping the HTML part is a deliberate XSS-in-inbox defense (attacker-controlled org names render as data, not markup).
**Consequence:** Callers enqueue best-effort (the URL is still logged as a manual-recovery fallback) so a Redis hiccup never 500s a user action. Delivery retries are the worker's `max_tries=5` backoff; a hard fail after retries is logged + dropped (no DLQ yet — P2). Deliverability infra (SPF/DKIM/DMARC, bounce suppression) is prod-side and still open.

---

## 6. Coding standards

### Backend (FastAPI / SQLAlchemy)
- All endpoints use FastAPI dependencies for auth, ownership, DB session.
- **Mutation pattern:**
  1. read row → 2. `ensure_can_mutate(user, row.owner_id)` → 3. apply changes →
  4. `record_audit(...)` → 5. `await db.commit()` → 6. `await db.refresh(row)` → 7. return.
- Never `except:`. Use `except SomeError` or `# noqa: BLE001` when intentional.
- Logs via `from app.logging_setup import get_logger; log = get_logger(__name__)`. Never `print` or stdlib `logging`.
- Settings via `get_settings()` (memoized). Don't read `os.environ` directly.
- Type everything (`Mapped[…]`, response models, return annotations).

### Frontend (Next.js / React 19)
- `"use client"` on every interactive component.
- API calls via `lib/api.ts::api.*`. Never raw `fetch`.
- All user-facing strings via `useTranslations`. No hardcoded English.
- Confirms via `useConfirm()`. No `window.confirm/alert`.
- Errors render inline (banner). No `alert()`.
- Money: `new Intl.NumberFormat(locale, { style: "currency", currency })`.
- Dates: `.toLocaleDateString(locale, …)`. Never `.toLocaleString()` without locale.
- Path: imports use `@/` alias (mapped to `src/`).
- File names: kebab-case for files, PascalCase for components.

### Git
- Conventional commit prefix: `feat(scope)`, `fix(scope)`, `chore`, `refactor`, `docs`, `test`.
- One concern per commit. Squash WIP locally before push.
- PRs reference the P-level + a checkbox from this doc when applicable.

---

## 7. Where to find things

| Concern | File |
| --- | --- |
| App entry / middleware / lifespan | [backend/app/main.py](backend/app/main.py) |
| Settings + runtime validation | [backend/app/config.py](backend/app/config.py) |
| ORM models + enums | [backend/app/models.py](backend/app/models.py) |
| Pydantic schemas | [backend/app/schemas.py](backend/app/schemas.py) |
| Auth + ownership + role guards | [backend/app/deps.py](backend/app/deps.py) |
| JWT + password hashing | [backend/app/security.py](backend/app/security.py) |
| Audit log helper | [backend/app/audit.py](backend/app/audit.py) |
| structlog config | [backend/app/logging_setup.py](backend/app/logging_setup.py) |
| Rate limiter | [backend/app/rate_limit.py](backend/app/rate_limit.py) |
| LLM provider abstraction | [backend/app/services/llm.py](backend/app/services/llm.py) |
| API client + 401 interceptor | [frontend/src/lib/api.ts](frontend/src/lib/api.ts) |
| Token storage + cross-tab | [frontend/src/lib/auth.ts](frontend/src/lib/auth.ts) |
| Confirm dialog provider | [frontend/src/components/confirm-dialog.tsx](frontend/src/components/confirm-dialog.tsx) |
| i18n config + 7 locale files | [frontend/src/i18n/](frontend/src/i18n/) + [frontend/messages/](frontend/messages/) |
| Authenticated layout | [frontend/src/app/[locale]/(app)/layout.tsx](frontend/src/app/[locale]/(app)/layout.tsx) |

---

## 8. Developer workflows

### Run everything
```bash
cp .env.example .env  # then set JWT_SECRET (>=32 chars)
docker compose up --build
```
- Frontend → http://localhost:3030
- Backend → http://localhost:8001/docs
- Postgres → port 5433
- Redis → port 6380

### Logs
```bash
docker compose logs -f backend
docker compose logs -f frontend
```

### DB shell
```bash
docker compose exec db psql -U crm -d crm
```

### Reset DB (dev only — destroys data)
```bash
docker compose down -v
docker compose up --build
```

### After a model change (Alembic workflow)
```bash
# 1. Edit a model in backend/app/models.py
# 2. Generate the diff migration:
docker compose exec backend alembic revision --autogenerate -m "what-changed"

# 3. Review the generated file in backend/alembic/versions/ —
#    autogenerate misses: column renames (sees drop+add), check constraints,
#    server-side functions. Edit by hand if needed.

# 4. Apply it (the next container restart applies automatically; do it
#    manually for fast feedback during dev):
docker compose exec backend alembic upgrade head

# Rollback the last migration:
docker compose exec backend alembic downgrade -1

# Inspect state:
docker compose exec backend alembic current     # which revision is live
docker compose exec backend alembic history     # full chain
```

### Run backend tests (after P1 lands)
```bash
docker compose exec backend pytest
```

---

## 9. Open product questions

These need product/founder input, not engineering:

- [ ] Tier limits per Organization (number of users, leads, deals)?
- [ ] Self-hosted distribution vs SaaS-only? Affects license + deploy.
- [ ] AI usage billing model — included in plan, metered, BYO key?
- [ ] Multi-currency strategy: live FX rates (and provider) vs daily snapshot?
- [ ] Data retention: audit log forever, or rolling 12 months?

---

## 10. Production readiness checklist

Hard gate. Don't open `crm.<customer-domain>.com` to a paying customer until every box is checked.

### Security
- [ ] `JWT_SECRET` is 48+ random bytes, set via secrets manager (not `.env` on disk)
- [ ] `ENVIRONMENT=production` is set → secret validation runs
- [ ] TLS terminated in front (Nginx/Caddy/Cloudflare), HSTS enabled
- [ ] CORS allowlist is explicit, no wildcards
- [ ] Tokens in httpOnly cookies + CSRF token (TD-2)
- [ ] MFA required for admin/manager (P1)
- [ ] Password reset email flow live (P1)
- [ ] Rate limits live on auth, search, imports, webhooks (P1)
- [ ] Webhook receivers verify HMAC signature
- [ ] Outgoing webhooks are signed
- [ ] Audit log captures every mutation; cannot be edited (append-only)
- [ ] Logs scrubbed: no JWT, no password hash, no PII in error messages
- [ ] Dependency scan clean: `pip-audit`, `npm audit --production`, `trivy image` (no HIGH/CRITICAL)
- [ ] Secret scan clean: `gitleaks detect`, `trufflehog filesystem .`

### Multi-tenant isolation
- [ ] Every tenant-owned table has `organization_id` + FK + index starting with it
- [ ] Every list/get/mutate query is scoped by `current_org_id`
- [ ] **RLS policies enabled and tested** (cross-org probe → 0 rows)
- [ ] Test suite has explicit "cross-tenant access returns 404" cases
- [ ] Audit log includes `organization_id`

### Reliability
- [ ] DB has automated backups + a tested restore drill (write the date in this doc when last drilled)
- [ ] Migrations are reversible OR forward-fixable (no destructive migrations without a backup)
- [ ] Workers run as a separate process and restart on failure
- [ ] Outbox poller alerts when lag > 60s
- [ ] DLQ alerts when depth > 0
- [ ] `/ready` checks DB + Redis + (LLM optional)
- [ ] At least one read replica for analytics queries
- [ ] Idempotency keys on all critical mutations

### Observability
- [ ] Sentry on backend + frontend, source maps uploaded
- [ ] Structured logs shipping to Loki/Datadog with `request_id`, `org_id`, `user_id`
- [ ] Prometheus metrics: latency histogram, error rate, queue depth, webhook delivery rate, LLM cost
- [ ] Synthetic monitor probing `/ready` + a tagged auth flow every 60s from outside
- [ ] Slow query log + alert (`pg_stat_statements`)
- [ ] Alert on p95 latency regression + error rate > 1%

### Data
- [x] Cursor pagination on the unbounded table lists — leads/customers/quotes (TD-11, done 2026-06-02)
- [ ] tsvector + GIN index on Lead/Customer search fields (TD-13)
- [ ] Composite indices starting with `organization_id` on every tenant table
- [ ] No N+1 on detail pages (eager-load `owner`, `customer`, recent activities)
- [ ] CSV export sanitized against formula injection (TD-22)
- [ ] GDPR export + erasure endpoints work end-to-end

### Operations
- [ ] CI gate: lint + types + tests + migrations + sec scan, blocks merge on red
- [ ] CD pipeline: build → trivy → deploy to staging → smoke test → manual promote to prod
- [ ] Runbook for: DB restore, secret rotation, LLM provider outage, key compromise, Stripe webhook outage
- [ ] On-call rotation and incident channel defined

### Billing (Stripe live)
- [ ] Stripe account is in **Live mode**, not Test mode
- [ ] Live Price IDs configured in env (matching the live products)
- [ ] Live webhook endpoint pointing to `https://crm.<your-domain>/api/billing/webhook`, all required events selected
- [ ] Webhook secret rotated via secrets manager, never in `.env` in git
- [ ] Stripe Tax enabled (or explicit tax-not-collected disclosure if applicable)
- [ ] Customer Portal configured: features for cancel, update card, view invoices, switch plan
- [ ] Test card → real card path validated end-to-end (Checkout → Webhook → Portal cancel → Subscription deleted → User downgrades)
- [ ] Refund + manual subscription edit playbook documented

---

## 11. Engineer command pack

Stack-specific. Adapted from generic CRM-engineer reference for our Python/FastAPI + Next.js setup.

### Project hygiene (find dead code, cycles, duplicate deps)
```bash
# Backend
docker compose exec backend ruff check app
docker compose exec backend ruff format --check app
docker compose exec backend pyright app          # add to requirements: pyright
docker compose exec backend vulture app          # dead code; add: vulture

# Frontend
cd frontend
npx madge --circular src                          # circular deps
npx depcheck                                      # unused deps
npx ts-prune                                      # unused exports
npx eslint . --max-warnings 0
npx tsc --noEmit
```

### Database design + migrations (after Alembic lands)
```bash
docker compose exec backend alembic revision --autogenerate -m "describe change"
docker compose exec backend alembic upgrade head
docker compose exec backend alembic downgrade -1
docker compose exec backend alembic history
```

### Postgres performance + index audit
```bash
docker compose exec db psql -U crm -d crm
```
```sql
-- Enable + read the slow query log
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
SELECT query, calls, total_exec_time, mean_exec_time, rows
FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20;

-- Index usage — find indexes never used (candidates to drop)
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes ORDER BY idx_scan ASC LIMIT 30;

-- Sequential scans — find tables missing indexes
SELECT relname, seq_scan, idx_scan, n_live_tup
FROM pg_stat_user_tables ORDER BY seq_scan DESC LIMIT 20;

-- Verify a hot query
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM leads
WHERE organization_id = '<org>' AND deleted_at IS NULL
ORDER BY created_at DESC LIMIT 50;
```

### Recommended indices (run during a migration with `CONCURRENTLY`)
```sql
CREATE INDEX CONCURRENTLY idx_leads_org_created ON leads (organization_id, created_at DESC);
CREATE INDEX CONCURRENTLY idx_deals_org_stage_updated ON deals (organization_id, stage, updated_at DESC);
CREATE INDEX CONCURRENTLY idx_customers_org_email ON customers (organization_id, lower(email));
CREATE INDEX CONCURRENTLY idx_activities_org_entity_time
  ON activities (organization_id, entity_type, entity_id, occurred_at DESC);
CREATE INDEX CONCURRENTLY idx_audit_logs_org_time ON audit_logs (organization_id, created_at DESC);
-- Search
CREATE INDEX CONCURRENTLY idx_leads_search
  ON leads USING gin (to_tsvector('simple',
    coalesce(first_name,'') || ' ' || coalesce(last_name,'') || ' ' ||
    coalesce(email,'') || ' ' || coalesce(company,'')));
```

### N+1 detection during dev
```bash
# Echo every SQL statement
docker compose exec backend env SQLALCHEMY_ECHO=1 uvicorn app.main:app --reload
```
Watch the API logs while clicking through a list — repeated `SELECT * FROM users WHERE id = $1` per row = N+1. Fix with `selectinload(Lead.owner)`.

### Load testing (k6)
```bash
# Install: brew install k6 / choco install k6
k6 run --vus 50 --duration 2m load/leads.js
k6 run --summary-export results.json load/dashboard.js
```
Minimal k6 script (`load/leads.js`):
```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
const TOKEN = __ENV.TOKEN;
export default function () {
  const res = http.get(`${__ENV.BASE_URL}/api/leads`,
    { headers: { Authorization: `Bearer ${TOKEN}` } });
  check(res, { '200': r => r.status === 200, '<500ms': r => r.timings.duration < 500 });
  sleep(1);
}
```

### Profiling slow paths
```bash
# Sampling profiler — attach to a running container
pip install py-spy
docker compose exec backend py-spy record -o /tmp/profile.svg --pid 1 --duration 30
docker compose cp backend:/tmp/profile.svg ./profile.svg
# Memory
pip install memray
docker compose exec backend memray run -o /tmp/mem.bin app/main.py
```

### Security scanning
```bash
# Backend
pip install pip-audit
docker compose exec backend pip-audit -r requirements.txt
# Frontend
cd frontend && npm audit --production && npx snyk test
# Containers
trivy image crm_gallo_backend:latest
trivy image crm_gallo_frontend:latest
# Secrets in repo
gitleaks detect --source .
trufflehog filesystem .
# Filesystem CVEs
trivy fs .
```

### Health and metrics smoke
```bash
curl -fsS localhost:8001/health     # liveness
curl -fsS localhost:8001/ready      # DB ping
curl -fsS localhost:8001/metrics    # add when Prometheus lands (P1)
```

### API documentation
```bash
# FastAPI already exposes /docs and /openapi.json
curl localhost:8001/openapi.json > openapi.json
npx @redocly/cli lint openapi.json
npx @redocly/cli build-docs openapi.json -o redoc.html
```

---

## 12. Advanced patterns ("1% engineer" toolbox)

Patterns to reach for once the basics are solid. Each one is worth a separate ADR when adopted.

| Pattern | Use when | First step |
| --- | --- | --- |
| **Outbox + idempotency keys** | You need reliable webhooks or automations | ADR-007 already drafted; build `outbox_events` table |
| **Row-Level Security** | Multi-tenant defense-in-depth | ADR-009; write the policy + a `set_tenant_context` dep |
| **Optimistic locking (version column)** | Concurrent edits on Deal/Task corrupt data | `version int NOT NULL DEFAULT 0` + `If-Match` header |
| **Cursor pagination** | Lists grow past 10k rows | ADR-010; encode `(updated_at, id)` as base64 |
| **Database partitioning** | `audit_logs`/`activities` > 100M rows | `PARTITION BY RANGE (created_at)` monthly, drop old |
| **Read replica routing** | Dashboard slows down writes | Route `SELECT`-heavy endpoints to a `read_engine` |
| **Per-tenant token bucket (Redis)** | One customer hammers the API | `slowapi[redis]` keyed by `org_id` |
| **Outbox poller with checkpoints** | Backfills crash and resume mid-run | Track `last_processed_id` per worker |
| **Shadow reads during migration** | Cutting over a schema change | Run new + old query, log mismatches before flipping |
| **Feature flags** | Risky launches need a kill switch | Unleash (self-hosted) or simple DB-backed flags |
| **Canary deploys** | Avoid blast-radius on a bad release | Route 5% traffic, watch p95+error, promote |
| **Chaos drills** | Confirm graceful degradation works | Kill Redis/worker/LLM in staging weekly |
| **Contract tests (Pact)** | Front + back drift silently | Generate consumer contract from FE; verify in BE CI |
| **Synthetic monitoring** | Catch regressions before users | External probe on `/ready` + an auth flow every 60s |
| **Backfill scripts with checkpoints** | Backfilling 10M rows after a model change | Process in batches, store `last_id`, log progress |
| **GDPR data export/erasure** | EU customer asks for their data | Cascade-aware: dump JSON + delete with soft + audit |

---

## 13. How to use this document

- **Resuming the project cold:** read §2 (Current state) and §3 P0. That's the next action.
- **Closing a PR:** tick the box in the relevant section; update §2 if state changes.
- **Adding a new direction:** add to §3 with a P-level (and justify the rank).
- **Making a non-obvious tech choice:** add a new ADR to §5 with date + rationale + consequence.
- **Discovering tech debt:** add a row to §4 with cost estimate.

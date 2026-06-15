# Changelog

All notable changes to Gallo CRM. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) from its first
public release.

## [Unreleased]

Pre-launch hardening and polish toward an Enterprise-grade, commercial release:
multi-currency display layer, a corporate design-system pass (square radii,
lucide icons), landing-page honesty + SEO (sitemap/robots/hreflang), full
frontend loading/error states, AI cost controls, and a complete backend
integration-coverage audit.

### Added
- **Per-user display currency** (EUR/CHF/USD/GBP) backed by a live FX layer:
  ECB rates (frankfurter.dev) refreshed daily by a worker cron, cached in
  `fx_rates`, with honest as-of stamping. `GET /api/fx/rates`.
- **Per-org LLM usage tracking** — token usage per org/user/use-case with an
  admin summary endpoint (`GET /api/llm-usage/summary`).
- **Outgoing-webhook follow-ups** — `POST /{id}/rotate-secret`,
  synchronous `POST /{id}/test`, delivery metrics (`GET /{id}/metrics`), and a
  90-day delivery-retention prune.
- **Public API v1 reference** (`docs/api/v1.md`) and a **post-deploy smoke**
  script (`scripts/post_deploy_smoke.py`).

### Changed
- **Per-use-case LLM temperature** — deterministic (0.0) lead scoring and
  summaries; warmer conversational assistant.
- FX conversion replaces the previously hardcoded rates in the dashboard;
  money stays EUR-canonical (display-only conversion, per ADR-015).

### Security
- Row-Level Security closed on six previously app-filtered tenant tables
  (defense-in-depth: ENABLE + FORCE + tenant-isolation policy).

---

## [0.1.0] - 2026-06-15 — Pre-launch baseline

The feature-complete core in production (Railway), built over the June 2026
sprint. Highlights of what shipped, by area:

### Added — Sales core
- **Leads / Customers / Companies** — full CRUD, cursor pagination, full-text
  search with pg_trgm typo fallback, owner assignment, optimistic locking,
  and atomic **Lead → Customer/Company/Deal conversion**.
- **Deals** — kanban drag-and-drop + a deal detail page (notes, attachments,
  activity, stage switcher); per-deal currency.
- **Follow-up engine** — `next_action` on deals, follow-up states on kanban
  cards, and a **"Hoje" action center** (`/hoje`) surfacing overdue/today
  follow-ups, stalled deals, and tasks.
- **Tasks** (list + month view), **Activity timeline**, **Notes**,
  **Notifications** (header bell).
- **Quotes & Contracts** — quote → contract → e-signature → PDF (WeasyPrint),
  merge-field templates, and a **Products/Services catalog** feeding quote
  line items.
- **Imports/Exports** (CSV/XLSX, validation, dedup, streaming export) and
  **WhatsApp omnichannel** (Cloud API, webhook, inbox, read receipts).

### Added — AI (locale-aware, single provider)
- Lead scoring, customer summaries, an in-app assistant (SSE streaming +
  history), and a public landing chatbot — all through one Groq endpoint.

### Added — Platform
- **Multi-tenant** — Organizations + Postgres RLS (ENABLE + FORCE + GUC,
  transaction-scoped); memberships, invites, per-org seat enforcement.
- **Auth** — JWT in httpOnly cookies + double-submit CSRF, refresh rotation
  with reuse detection, **mandatory MFA** for admins/managers (Fernet-encrypted
  secrets), password reset, sessions page, **Microsoft OAuth**, Turnstile on
  register, and rate limits on sensitive endpoints.
- **GDPR** — per-contact consent, anonymize-in-place forget + export, per-org
  retention sweep, and a settings card.
- **Billing** — Stripe (live), monthly/yearly plans (−20% yearly), multi-currency
  price points, seats, trial; webhook as source of truth.
- **Onboarding** — computed checklist, 7 sector pipeline templates,
  empty-states-with-CTA.
- **Public API + API keys**, **outgoing webhooks** (HMAC, outbox, retry,
  auto-pause), **no-code automations**, a **performance/KPI** screen, and an
  **audit log** (RLS-strict).
- **Observability** — Sentry (EU), PostHog (EU), Prometheus metrics, `/ready`
  probes, Arq dead-letter queue, outbox-lag gauge.
- **Frontend** — toast system, list skeletons, responsive-first layouts,
  7 locales with CI key-parity.
- **CI/CD** — backend (ruff/pytest/pip-audit/alembic), frontend
  (tsc/eslint/vitest/i18n-parity), docker (Trivy), e2e (Playwright smoke),
  security (gitleaks/trufflehog), db-backup, Dependabot.

[Unreleased]: https://github.com/kallebesiqueira-dev/crm_gallo/compare/main...HEAD

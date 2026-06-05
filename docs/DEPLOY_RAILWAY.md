# Deploy plan — Railway (initial test phase)

> **Saved plan / runbook** for the next working session. This captures the
> decisions + step-by-step so nothing is lost. Complements the generic
> [`docs/DEPLOY.md`](DEPLOY.md); this one is Railway-specific.

## Decision (2026-06-05)
Deploy on **Railway first** to get a real test environment up fast. **Migrate to
an EU‑owned provider (Scaleway / Hetzner) later** — before onboarding paying EU
customers, or when scale demands it. The Docker setup makes that migration
straightforward. For the test phase (no real customer PII yet) Railway is fine;
the EU‑data‑sovereignty positioning matters once real customer data lands.

## Domain & accounts
- **Domain:** `gallo-crm.com` — registered at **Namecheap** → **DNS managed at Namecheap**.
- **Subdomains:** `app.gallo-crm.com` (frontend) · `api.gallo-crm.com` (backend).
- **Accounts needed:** Railway, Resend (email), Anthropic (AI); optional Cloudflare (R2 for attachments).

## Architecture on Railway (one project)
| Service | What | Notes |
| --- | --- | --- |
| Postgres | managed DB | pgvector **not** required yet (no migration uses it). |
| Redis | managed | sessions, rate limits, Arq queue. |
| backend | FastAPI (Dockerfile) | start: `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"`. Public domain `api.gallo-crm.com`. |
| worker | Arq (same image) | start: `arq app.worker.settings.WorkerSettings`. No public domain. |
| frontend | Next.js (Dockerfile `runner` stage) | build-arg `NEXT_PUBLIC_API_URL=https://api.gallo-crm.com`. Public domain `app.gallo-crm.com`. |
| Object storage | **Cloudflare R2** (S3-compatible) | optional in the first pass; attachments degrade gracefully without it. |
| Email | **Resend** | **REQUIRED now** — signup requires email verification (PR #6), so new users can't confirm without it. |

## Phases (execute together next session)
- **Phase 0 — accounts + domain.** Domain bought ✅. Create Railway / Resend / Anthropic accounts.
- **Phase 1 — Railway: add Postgres + Redis** (managed).
- **Phase 2 — Cloudflare R2** (optional first pass): one bucket `gallo-crm-attachments` (EU jurisdiction) + an API token scoped to **that bucket only** (Object Read & Write). Capture access key / secret / `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
- **Phase 3 — Resend:** add + verify domain `gallo-crm.com` → add the **SPF / DKIM / DMARC** records **at Namecheap**; create an API key; sender `no-reply@gallo-crm.com`.
- **Phase 4 — backend + worker services** (root dir `backend`, Dockerfile). Set env (matrix below). After the first deploy runs migrations and creates the `crm_app` role, **rotate its password** (see below) and update `APP_DATABASE_URL`.
- **Phase 5 — frontend service** (root dir `frontend`, Dockerfile). Pass `NEXT_PUBLIC_API_URL` as a **build arg** (it's inlined at build time).
- **Phase 6 — custom domains + DNS:** add `api.gallo-crm.com` to the backend service and `app.gallo-crm.com` to the frontend service in Railway; add the **CNAME records Railway shows, at Namecheap**. Then set `CORS_ORIGINS` / `FRONTEND_BASE_URL` / Stripe URLs to the real frontend origin.
- **Phase 7 — smoke test:** `curl https://api.gallo-crm.com/ready` → 200; register (founder = auto-verified) → dashboard; invite a teammate → email arrives (Resend); create lead + AI score (Anthropic); generate a quote PDF (worker + R2).

## Env matrix (backend + worker)
```
ENVIRONMENT=production
JWT_SECRET=<openssl rand -hex 48>
DATABASE_URL=postgresql+asyncpg://<owner>:<pwd>@<host>:<port>/<db>     # Railway PG owner role (Alembic)
SYNC_DATABASE_URL=postgresql://<owner>:<pwd>@<host>:<port>/<db>
APP_DATABASE_URL=postgresql+asyncpg://crm_app:<rotated>@<host>:<port>/<db>   # runtime (RLS)
REDIS_URL=<Railway Redis URL>
CORS_ORIGINS=https://app.gallo-crm.com
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=<key>
S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com   # if R2
S3_ACCESS_KEY_ID=<r2 key>
S3_SECRET_ACCESS_KEY=<r2 secret>
S3_BUCKET=gallo-crm-attachments
S3_REGION=auto
EMAIL_PROVIDER=resend
RESEND_API_KEY=<key>
EMAIL_FROM=no-reply@gallo-crm.com
EMAIL_FROM_NAME=GALLO CRM
FRONTEND_BASE_URL=https://app.gallo-crm.com
```
Frontend (build arg/var): `NEXT_PUBLIC_API_URL=https://api.gallo-crm.com`, `NEXT_PUBLIC_DEFAULT_LOCALE=it` (or preference).

## crm_app password rotation (TD-31 — deploy blocker)
After the first `alembic upgrade head` creates the `crm_app` role (dev password
`crm_app_dev_2026`), in the Railway Postgres console:
```sql
ALTER ROLE crm_app PASSWORD '<a strong random password>';
```
then update `APP_DATABASE_URL` and redeploy. Leaving `APP_DATABASE_URL` unset
falls back to the owner role = **RLS off** (unsafe for multi-tenant).

## DNS records to add at Namecheap (Phase 6 + 3)
- `app.gallo-crm.com` → CNAME → (target Railway shows for the frontend service)
- `api.gallo-crm.com` → CNAME → (target Railway shows for the backend service)
- Resend: SPF (TXT), DKIM (CNAME/TXT), DMARC (TXT) — exactly as Resend lists them.

## Already done (merged to `main`)
- Production multi-stage frontend image + deploy guide + TD-44 (PR #1)
- `.trivyignore` cleanup (PR #2)
- Switzerland → **Italy** conversion (PR #3)
- Purple "CRM" logo (PR #4)
- **4 pricing tiers**: Free / Standard €19 / Business €39 / Premium €59 (PR #5)
- **Email verification on signup** (PR #6) — *requires Resend in production*
- **Real footer company data** (PR #7): GALLO CRM S.r.l. · P.IVA `IT03270000777` ·
  `gallo-crm@hotmail.com` (contact) · `www.gallo-crm.com` · WhatsApp `wa.me/393717403464`

## Notes / gotchas
- **Email verification ⇒ Resend is mandatory in prod**: without a working sender, new self-signups can't confirm (the first user / founder + invited users are auto-verified, so you can still get in).
- **Contact email vs sending email:** `gallo-crm@hotmail.com` is the public *contact* address (footer). Transactional email is *sent* by Resend from `no-reply@gallo-crm.com` on the verified domain — different things.
- **pgvector** isn't needed until RAG ships; plain Railway Postgres works now.
- For attachments storage, swapping R2 → another S3-compatible endpoint is an env change (no code).

## Next-session checklist
1. (optional) adjust 4-plan grid layout — **user said it's fine as-is**, skip unless asked.
2. Execute Phases 0–7 above, guided step by step.

# Deploy guide — first real tests (pilot)

> **Scope.** This is the runbook to get CRM Gallo onto a **real URL over HTTPS**
> so actual people can use it with real data — a *pilot*. It is intentionally
> lighter than the full paying-customer gate in
> [`skills.md` §10](../skills.md) (MFA-mandatory, GDPR export/erasure, on-call,
> Stripe live, restore drill…). Do the pilot first; graduate to §10 before you
> charge anyone.

---

## 1. What you are deploying

| Service | What it is | Pilot note |
| ------- | ---------- | ---------- |
| **frontend** | Next.js 15 (standalone) | Build the default `runner` stage of `frontend/Dockerfile`. |
| **backend** | FastAPI (uvicorn) | Runs `alembic upgrade head` on boot, then serves :8000. |
| **worker** | Arq background worker | Same image as backend, command `arq app.worker.settings.WorkerSettings`. Needed for PDF, email, webhooks, imports, lead scoring. |
| **Postgres 16 + pgvector** | Primary DB | Must support the `vector` extension (image is `pgvector/pgvector:pg16`). |
| **Redis 7** | Sessions, rate limits, Arq queue | — |
| **Object storage (S3 API)** | File attachments | Use **Cloudflare R2** or AWS S3 in prod — the code already speaks the S3 protocol via boto3. |

**Two pilot simplifications (do these — they remove a lot of ops):**

1. **Use Anthropic, not self-hosted Ollama.** Set `LLM_PROVIDER=anthropic` +
   `ANTHROPIC_API_KEY`. This drops the `ollama` + `ollama-pull` services
   entirely (they need a big/GPU container to be useful). AI scoring, summaries
   and the assistant all work through the cloud API.
2. **Managed Postgres + Redis + R2** instead of the compose sidecars, so backups
   and durability are someone else's problem.

---

## 2. Path A — Single VPS + Docker Compose + Caddy (fastest to a URL)

Best if you want speed and already trust the compose stack. ~1–2 days.

1. **Provision a small VPS** (Hetzner CX22 / DigitalOcean 2GB+). Install Docker
   + Compose. Point a domain `crm.<you>.app` (and `api.crm.<you>.app`) at its IP.
2. **Put `.env` on the box** (NOT in git) filled from §4 below.
3. **Add a production compose override** that uses built images instead of the
   dev bind-mounts. Minimal `docker-compose.prod.yml`:
   ```yaml
   services:
     frontend:
       build:
         context: ./frontend
         target: runner          # the slim standalone stage
         args:
           NEXT_PUBLIC_API_URL: https://api.crm.you.app
           NEXT_PUBLIC_DEFAULT_LOCALE: pt
       command: ["node", "server.js"]   # override the dev `npm run dev`
       volumes: []                       # drop the source bind-mounts
     backend:
       volumes: []                       # use the baked image, not the host source
     worker:
       volumes: []
   ```
   Run with: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
4. **TLS** — put **Caddy** in front (auto Let's Encrypt). A 12-line `Caddyfile`:
   ```
   crm.you.app      { reverse_proxy localhost:3030 }
   api.crm.you.app  { reverse_proxy localhost:8001 }
   ```
5. Migrations run automatically (backend boots with `alembic upgrade head`).
6. Run the smoke test in §6.

> Storage on a VPS: you can keep the MinIO sidecar (give it a persisted volume +
> strong `S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY`) or point at R2. R2 is the
> safer pilot choice — no blob to back up yourself.

---

## 3. Path B — Managed PaaS (Render / Railway / Fly)

More robust, less ops. ~2–4 days. Example with **Render** (Railway/Fly are
analogous):

- **Postgres**: create a managed Postgres; enable the `vector` extension
  (`CREATE EXTENSION IF NOT EXISTS vector;`). Confirm your role can `CREATE ROLE`
  and `CREATE EXTENSION` (needed because migrations create the `crm_app` role and
  the pgvector/RLS objects).
- **Redis**: managed Redis (Render Key Value / Upstash).
- **backend**: Web Service from `./backend/Dockerfile`. Start command stays the
  image default. Set all env from §4.
- **worker**: Background Worker, **same image/repo**, start command
  `arq app.worker.settings.WorkerSettings`, same env.
- **frontend**: Web Service from `./frontend/Dockerfile` (default `runner`
  stage). Pass `NEXT_PUBLIC_API_URL` as a **build arg** (it is inlined into the
  browser bundle at build time — a runtime env var is too late).
- **Object storage**: Cloudflare R2 bucket; set the `S3_*` vars to the R2
  endpoint + token.
- HTTPS + domains are provided by the platform.

---

## 4. Production env / secrets (what MUST change from the dev defaults)

Copy `.env.example` → `.env` and override at least these. Everything not listed
can keep its `.env.example` value for a pilot.

| Var | Dev default | Pilot value |
| --- | ----------- | ----------- |
| `ENVIRONMENT` | `development` | **`production`** (turns on strict secret validation) |
| `JWT_SECRET` | placeholder | **`openssl rand -hex 48`**, stored in the host's secrets manager — never in git |
| `DATABASE_URL` | local `crm` | managed Postgres **owner** role (runs Alembic/DDL) |
| `SYNC_DATABASE_URL` | local `crm` | same DB, `postgresql://` (no `+asyncpg`) |
| `APP_DATABASE_URL` | `crm_app:crm_app_dev_2026@…` | **rotate the `crm_app` password** after first migration: `ALTER ROLE crm_app PASSWORD '<new>'` then update this URL |
| `REDIS_URL` | local | managed Redis URL (use `rediss://` if TLS) |
| `CORS_ORIGINS` | `http://localhost:3030` | `https://crm.you.app` (the browser origin) |
| `LLM_PROVIDER` | `ollama` | `anthropic` |
| `ANTHROPIC_API_KEY` | empty | your key |
| `S3_ENDPOINT_URL` / `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` / `S3_BUCKET` | MinIO | R2/S3 endpoint + creds + bucket |
| `EMAIL_PROVIDER` | `console` | `resend` (or `smtp`) |
| `RESEND_API_KEY` | empty | your key — **and verify a sending domain (SPF + DKIM + DMARC)** or invites/resets land in spam |
| `EMAIL_FROM` / `FRONTEND_BASE_URL` | localhost | `no-reply@crm.you.app` / `https://crm.you.app` |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8001` | `https://api.crm.you.app` (**build arg**, see above) |
| `STRIPE_SUCCESS_URL` / `STRIPE_CANCEL_URL` | localhost | your real billing/pricing URLs |

**Stripe for a pilot:** leave the keys **empty** (the Free plan works without
Stripe) or use **test-mode** keys. Don't go Live until you're at the §10 gate.

---

## 5. The two-role database model (don't skip)

The app uses RLS for tenant isolation, which requires two DB roles:

- `crm` (owner, via `DATABASE_URL`) — runs Alembic migrations (DDL bypasses RLS).
- `crm_app` (`NOSUPERUSER NOBYPASSRLS`, via `APP_DATABASE_URL`) — the FastAPI +
  worker runtime, so RLS policies actually enforce.

Migration `f5fde59e0dc8` **creates `crm_app`** with the hardcoded dev password
`crm_app_dev_2026`. On a real deploy, after the first `alembic upgrade head`:
```sql
ALTER ROLE crm_app PASSWORD '<a strong random password>';
```
then update `APP_DATABASE_URL`. If `APP_DATABASE_URL` is unset the app falls back
to `DATABASE_URL` — **single-role mode = RLS off**, which is unsafe for
multi-tenant. Always set it.

---

## 6. Post-deploy smoke test

```bash
# 1. Readiness — expect 200 with db + redis "ok"
curl -s https://api.crm.you.app/ready | jq

# 2. Register the first account (becomes admin) via the UI:
#    https://crm.you.app  → register → confirm you land in the dashboard

# 3. Invite flow proves email actually delivers:
#    Settings → invite a teammate → confirm the email arrives (not spam)

# 4. Create a lead → run AI scoring → confirm a score comes back (Anthropic)

# 5. Generate a quote PDF → confirm the worker renders + the file downloads
#    (this exercises worker + Redis + S3/R2 together)
```
If all five pass, the pilot stack is live. The repo's Playwright `@smoke` suite
(`frontend/e2e/`) can be pointed at the deployed URL for a repeatable check.

---

## 7. Known red CI: the `docker` workflow

The `docker` workflow's **frontend Trivy gate** has been failing on HIGH CVEs in
the **dev** toolchain (playwright/vitest/eslint + node-tar/glob/cross-spawn
transitives — TD-44), because the old `frontend/Dockerfile` shipped a *dev*
container. The production multi-stage `frontend/Dockerfile` in this repo builds a
slim `runner` stage that contains **only the traced runtime deps**, so those
dev-only CVEs are no longer in the scanned image. Once that Dockerfile is on
`main`, the `docker` workflow should go green without new `.trivyignore` entries.

---

## 8. Pilot → paying customer

Before opening to a paying customer, work the full hard gate in
[`skills.md` §10](../skills.md): MFA mandatory for admin/manager, GDPR
export/erasure, monitoring alerts + Grafana dashboard, runbooks, on-call,
DB restore drill, and Stripe **Live** mode end-to-end.

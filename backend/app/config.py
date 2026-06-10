from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SECRETS = {"change-me", "change-me-in-production-use-a-long-random-string"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    database_url: str = "postgresql+asyncpg://crm:crm@localhost:5432/crm"
    sync_database_url: str = "postgresql://crm:crm@localhost:5432/crm"
    # Runtime role for the FastAPI process. Separate from `database_url`
    # so Alembic continues to use the owner role (crm) for DDL while
    # the app connects as a non-superuser (crm_app) that respects RLS
    # policies. When unset, falls back to `database_url` (single-role
    # mode — RLS is bypassed; pre-Phase-6 behaviour).
    app_database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    # Short access token + long refresh = standard split. Access is the
    # one attached to every authenticated request — keep it short so a
    # leaked access token has a small useful lifetime. Refresh is sent
    # ONLY to /api/auth/refresh (cookie path-scoped) and is server-side
    # revocable via Redis on logout.
    jwt_access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    cors_origins: str = "http://localhost:3000"

    # Domain attribute for the auth cookies. Empty => host-only (cookie scoped
    # to the exact API host — fine when the SPA and API share an origin). Set to
    # a shared parent like ".gallo-crm.com" when the frontend and API live on
    # DIFFERENT subdomains (app.gallo-crm.com ↔ api.gallo-crm.com) so the
    # JS-readable csrf cookie is visible to the SPA and the auth cookie is sent
    # to both — without it the SPA can't tell it's logged in after login.
    cookie_domain: str = ""

    rate_limit_login_per_minute: int = 5
    rate_limit_register_per_minute: int = 5
    rate_limit_password_reset_per_minute: int = 3

    # ---- MFA policy ----
    # When true, any user who holds an admin/manager role in ANY org is
    # required to enroll in TOTP MFA. Until they do, every tenant-data
    # endpoint returns 403 `mfa_enrollment_required` (the choke point is
    # `get_current_org_id`); only the MFA-enrollment + session endpoints
    # stay reachable so they can complete setup. Off by default so a
    # fresh install / dev never gets locked out — flip it on per deploy.
    mfa_required_for_privileged: bool = False
    # LLM-cost protection — per-user (see app.rate_limit.user_or_ip_key).
    rate_limit_score_per_hour: int = 10
    rate_limit_assistant_per_minute: int = 30
    # Public, unauthenticated landing chatbot — keyed per-IP. Generous enough
    # for a real visitor conversation, low enough to blunt scraping/abuse of
    # the (cost-bearing) LLM from an anonymous endpoint.
    rate_limit_chatbot_per_minute: int = 20
    # Public, unauthenticated Web-to-Lead form submit — keyed per-IP. Blunts
    # automated lead-spam while staying generous for a legitimate visitor who
    # fat-fingers and resubmits a couple of times.
    rate_limit_form_submit_per_minute: int = 10

    # ---- CAPTCHA (Cloudflare Turnstile) ----
    # Anti-bot on registration + public form submits. Empty = disabled (the
    # honeypot + per-IP rate limits still apply). Set the secret to enforce it;
    # the matching site key is served to the browser as
    # NEXT_PUBLIC_TURNSTILE_SITE_KEY.
    turnstile_secret_key: str = ""

    # ---- S3-compatible object storage (FileAttachments) ----
    # Defaults match the MinIO sidecar in docker-compose; swap the
    # endpoint + creds to point at real AWS S3 / R2 / etc. without
    # touching app code. `s3_bucket` is created on startup if missing
    # (idempotent).
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin"
    s3_bucket: str = "crm-gallo-attachments"
    s3_region: str = "us-east-1"
    # Presigned-download URL TTL (seconds). 5 minutes is enough for
    # a click-through; longer leaves the link useful out-of-band
    # (which we don't want — attachments should be re-fetched via
    # the app, not shared via leaked URLs).
    s3_download_url_ttl: int = 300
    # Hard cap on a single upload, bytes. 25 MB is plenty for the
    # typical CRM attachment (deck, contract, invoice). Larger files
    # belong on a dedicated DMS, not the CRM record.
    attachment_max_bytes: int = 25 * 1024 * 1024

    # ---- Bulk imports (ADR-016) ----
    # Hard cap on an uploaded import file, bytes. 10 MB comfortably holds
    # the MAX_ROWS (50k) contact CSV/XLSX the parser accepts; bigger files
    # are almost always a wrong-file mistake, so we reject at the edge
    # before paying for an S3 round-trip + a worker dispatch.
    import_max_upload_bytes: int = 10 * 1024 * 1024
    # Per-org cap on import jobs started in a rolling 24h window. Stops a
    # script (or a stuck retry loop) from flooding the worker; a human
    # doing real imports never approaches it.
    import_daily_cap: int = 50

    # ---- Public API & API keys (ADR-016) ----
    # Per-key request budget for the bearer-authenticated /api/v1
    # surface, fixed-window per minute in Redis. Separate from the
    # per-IP login limit (different threat: a key is one integrator's
    # automation, not anonymous login attempts). Generous default —
    # a normal sync job stays well under it; a runaway loop trips 429.
    api_key_rate_limit_per_minute: int = 120
    # Don't write `last_used_at` on every request — that's a row write
    # on every API call. Only refresh it when the stored value is older
    # than this many seconds, so the "last used" telemetry stays useful
    # without turning every GET into a write.
    api_key_last_used_throttle_seconds: int = 60

    # ---- Sentry ----
    # Empty DSN = SDK disabled (no init, no network calls). The smoke
    # path is "deploy with an empty DSN and nothing changes"; pasting
    # a real DSN turns on exception capture + performance traces in
    # production without a code change.
    sentry_dsn: str = ""
    # Fraction of transactions sampled for performance traces.
    # Default low so a dev DSN doesn't burn quota; bump per env.
    sentry_traces_sample_rate: float = 0.1
    # Tag every event with the runtime env (development / staging /
    # production) so Sentry can split inbox by deployment.
    sentry_environment: str = ""

    # ---- Crypto / secrets-at-rest ----
    # Fernet key (urlsafe-base64, 32 bytes) encrypting the TOTP MFA
    # secret in `users.mfa_secret`. Leave empty to derive a key from
    # JWT_SECRET automatically (always-on encryption, zero ops); set a
    # dedicated key in production to decouple MFA secrets from JWT
    # rotation. Generate one with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    mfa_encryption_key: str = ""

    # ---- Ops / metrics ----
    # Bearer token guarding GET /metrics. In production the endpoint is
    # private: unset → /metrics returns 404; set → callers must send
    # `Authorization: Bearer <token>`. Outside production /metrics stays
    # open so a local Prometheus / `curl` works with zero config.
    metrics_token: str = ""

    llm_provider: str = "ollama"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:3b"

    # ---- Generic OpenAI-compatible LLM (Groq / Mistral / Cerebras / OpenRouter / vLLM) ----
    # Set llm_provider="openai_compat" + these three to use ANY provider whose
    # API speaks the OpenAI `POST /chat/completions` shape. Keeps the AI layer
    # vendor-neutral: swap Groq (fast, free — good for tests) → Mistral (EU /
    # GDPR for production) → a self-hosted vLLM by changing env vars only, no
    # code change. Empty key → the provider raises a clear "not configured"
    # error and chat_completion falls back to another configured provider.
    llm_base_url: str = ""  # e.g. https://api.groq.com/openai/v1
    llm_api_key: str = ""
    llm_model: str = ""  # e.g. openai/gpt-oss-120b  (Groq) / mistral-small-latest

    # Google Gemini key. Gemini exposes an OpenAI-compatible endpoint, so it is
    # wired through the generic `openai_compat` provider (LLM_BASE_URL=
    # https://generativelanguage.googleapis.com/v1beta/openai , LLM_API_KEY=
    # this key, LLM_MODEL=gemini-2.0-flash). Kept as a named env var so the
    # value is discoverable in deploy config.
    gemini_api_key: str = ""

    # ---- Public landing chatbot (ADR: pre-sales assistant) ----
    # Master switch for the unauthenticated POST /api/public/chatbot endpoint.
    # When false the endpoint always returns the static fallback (source=
    # "fallback") so the marketing site keeps working with the AI turned off.
    public_chatbot_enabled: bool = True

    # ---- Stripe ----
    # When STRIPE_SECRET_KEY is empty, paid plans surface a clear error
    # and the Free plan keeps working. Set these for staging/production.
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""

    # Price IDs — create one per (plan, cycle) in your Stripe dashboard.
    stripe_price_standard_monthly: str = ""
    stripe_price_standard_yearly: str = ""
    stripe_price_business_monthly: str = ""
    stripe_price_business_yearly: str = ""
    stripe_price_premium_monthly: str = ""
    stripe_price_premium_yearly: str = ""

    # Landing-checkout price aliases. The public landing CTA addresses the three
    # paid tiers by simple names (starter→Standard, pro→Business, enterprise→
    # Premium). These take precedence for the public checkout; when unset it
    # falls back to the monthly price IDs above, so a single set of IDs works.
    stripe_starter_price_id: str = ""
    stripe_pro_price_id: str = ""
    stripe_enterprise_price_id: str = ""

    # Where Stripe redirects after checkout. Must point to the frontend.
    stripe_success_url: str = "http://localhost:3030/en/billing?stripe=success"
    stripe_cancel_url: str = "http://localhost:3030/en/pricing?stripe=cancel"

    # ---- Transactional email (ADR-017) ----
    # Provider is swappable so the SAME app code serves a SaaS deploy
    # (Resend) and a self-hosted / EU-sovereignty deploy (own SMTP) —
    # the product's data-residency wedge means we can't hard-wire a US
    # SaaS sender. `console` is the dev default: it logs the rendered
    # email and needs zero secrets, so a fresh clone sends "email"
    # without any setup.
    email_provider: str = "console"  # console | resend | smtp
    # Envelope sender. Use a dedicated subdomain (mail.crmgallo.app)
    # with SPF/DKIM/DMARC in prod — see ADR-017 consequences.
    email_from: str = "no-reply@crmgallo.app"
    email_from_name: str = "CRM Gallo"
    # Frontend origin used to build links in emails (invite / reset / verify).
    # Single source of truth instead of deriving from the Stripe URL.
    frontend_base_url: str = "http://localhost:3030"
    # How long an email-verification link stays valid. 24h is generous —
    # the link is sent the moment someone self-registers, so a same-day
    # confirmation is the norm; a day of slack covers "I'll do it tonight".
    email_verification_ttl_hours: int = 24
    # Resend (SaaS). Empty key + provider=resend → send() raises and
    # the worker retries; the call-site fallback log still has the URL.
    resend_api_key: str = ""
    # SMTP (self-host). STARTTLS on 587 is the safe default; set
    # smtp_use_tls=false only for a local relay like MailHog.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    # ---- Product analytics (PostHog) ----
    # Server-side event capture. Same PostHog project key as the frontend's
    # NEXT_PUBLIC_POSTHOG_KEY; EU cloud by default for GDPR. Empty key ⇒ off,
    # so a fresh clone / dev runs with analytics disabled and zero setup.
    posthog_api_key: str = ""
    posthog_host: str = "https://eu.i.posthog.com"

    # ---- OAuth / social login (Microsoft Entra ID) ----
    # Empty client id/secret ⇒ social login is OFF (endpoints 404, button hides).
    # Match is by verified email — no oauth-account table, so NO migration.
    # Client id + tenant are public identifiers; the secret is set on the backend
    # service only and never committed.
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant_id: str = "common"
    # Public base URL of THIS backend (e.g. https://api.gallo-crm.com) used to
    # build the OAuth redirect URI; falls back to the request's base URL.
    oauth_redirect_base: str = ""

    # ---- E-signature (ADR-016) ----
    # Which signing backend `app.signing.get_provider()` selects. `manual`
    # is the dev/low-stakes default: it signs in-app via an opaque token
    # link and needs zero vendor config, so a fresh clone has a working
    # signing flow. Switch to `skribble` / `scrive` (QES/eIDAS) for
    # legally-binding signatures — those adapters need a vendor account.
    signing_provider: str = "manual"  # manual | skribble | scrive
    # Vendor API credentials for the real providers. Empty → that provider
    # raises a clear "not configured" error instead of half-working.
    skribble_api_key: str = ""
    scrive_api_key: str = ""
    # HMAC secret the inbound signature webhook verifies (vendor-configured
    # signing secret). Empty → the webhook returns 503 (not configured)
    # rather than accepting unverified state changes.
    signing_webhook_secret: str = ""

    # ---- WhatsApp Business Cloud API (omnichannel inbox, phase 1) ----
    # One Meta app fronts the whole SaaS (Tech-Provider model): the
    # app-level secret + verify-token are GLOBAL here, while each tenant
    # connects its OWN WhatsApp number (phone_number_id + access_token)
    # stored per-org in `whatsapp_accounts`. Inbound messages route to a
    # tenant by the `phone_number_id` in Meta's payload.
    #
    # `whatsapp_verify_token` — the string Meta echoes during the one-time
    # GET webhook verification handshake (you set the same value in the
    # Meta app dashboard). Empty → the GET challenge always 403s, so the
    # webhook can't be (mis)configured against an unconfigured deploy.
    whatsapp_verify_token: str = ""
    # `whatsapp_app_secret` — the Meta App Secret. Every inbound POST is
    # signed by Meta with `X-Hub-Signature-256 = HMAC-SHA256(app_secret,
    # raw_body)`; empty → inbound POSTs are rejected 503 (we refuse to
    # accept unverified messages rather than trust the network).
    whatsapp_app_secret: str = ""
    # Graph API version + host. Pinned so a Meta-side default bump can't
    # silently change request/response shapes under us.
    whatsapp_api_version: str = "v21.0"
    whatsapp_graph_url: str = "https://graph.facebook.com"

    @property
    def runtime_database_url(self) -> str:
        """URL the FastAPI process should connect with. Defaults to the
        owner role if the dedicated runtime role isn't configured."""
        return self.app_database_url or self.database_url

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    def validate_for_runtime(self) -> None:
        """Refuse to start with insecure defaults in production."""
        if self.jwt_secret in _DEFAULT_SECRETS or len(self.jwt_secret) < 32:
            msg = (
                f"Insecure JWT_SECRET (length={len(self.jwt_secret)}). "
                "Set JWT_SECRET to a long random string (>=32 chars)."
            )
            if self.is_production:
                raise RuntimeError(msg)
            import logging

            logging.getLogger(__name__).warning("SECURITY: %s", msg)


@lru_cache
def get_settings() -> Settings:
    return Settings()

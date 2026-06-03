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

    rate_limit_login_per_minute: int = 5
    rate_limit_register_per_minute: int = 5
    rate_limit_password_reset_per_minute: int = 3

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

    llm_provider: str = "ollama"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:3b"

    # ---- Stripe ----
    # When STRIPE_SECRET_KEY is empty, paid plans surface a clear error
    # and the Free plan keeps working. Set these for staging/production.
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""

    # Price IDs — create one per (plan, cycle) in your Stripe dashboard.
    stripe_price_standard_monthly: str = ""
    stripe_price_standard_yearly: str = ""
    stripe_price_premium_monthly: str = ""
    stripe_price_premium_yearly: str = ""

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
    # Frontend origin used to build links in emails (invite / reset).
    # Single source of truth instead of deriving from the Stripe URL.
    frontend_base_url: str = "http://localhost:3030"
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

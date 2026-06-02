import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api import (
    activities,
    assistant,
    attachments,
    audit,
    auth,
    billing,
    customers,
    dashboard,
    deals,
    invites,
    leads,
    notes,
    notifications,
    orgs,
    outbox,
    pipelines,
    quotes,
    signatures,
    tasks,
    teams,
    trash,
    webhooks,
)
from app.config import get_settings
from app.cookies import (
    ACCESS_TOKEN_COOKIE,
    CSRF_HEADER,
    CSRF_PROTECTED_METHODS,
    CSRF_TOKEN_COOKIE,
)
from app.database import engine
from app.logging_setup import configure_logging, get_logger
from app.metrics import PrometheusMiddleware, metrics_response
from app.rate_limit import limiter
from app.sentry_setup import init_sentry

settings = get_settings()
configure_logging()
# Sentry MUST init before the FastAPI app is constructed so its ASGI
# integration wraps the application from the outside. Returns False
# silently when SENTRY_DSN is empty — no overhead in dev.
_sentry_enabled = init_sentry()
log = get_logger("crm.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_for_runtime()
    # Schema is owned by Alembic — see backend/alembic/. The compose
    # backend service runs `alembic upgrade head` before launching uvicorn,
    # so by the time we get here the DB is at the right revision. We log
    # which revision is live so anyone tailing the startup output can
    # confirm at a glance.
    async with engine.begin() as conn:
        rev = (
            await conn.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one_or_none()

    # Ensure the S3 bucket for file attachments exists. Idempotent —
    # safe to run on every boot. If MinIO/S3 is unreachable we LOG
    # the failure and keep going: attachments will error at upload
    # time with a clear message, but the rest of the app is fine
    # without object storage.
    s3_ready = False
    try:
        from app.storage import ensure_bucket

        await ensure_bucket()
        s3_ready = True
    except Exception as e:
        log.warning("s3_bucket_bootstrap_failed", error=str(e)[:200])

    log.info(
        "startup_complete",
        env=settings.environment,
        provider=settings.llm_provider,
        db_revision=rev,
        sentry=_sentry_enabled,
        s3=s3_ready,
    )
    yield
    await engine.dispose()


app = FastAPI(
    title="CRM Gallo API",
    description="AI-powered multilingual CRM backend",
    version="0.2.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", CSRF_HEADER],
    expose_headers=["X-Request-ID"],
)


def _consteq(a: str, b: str) -> bool:
    """Constant-time string compare so the CSRF check doesn't leak the
    nonce one byte at a time. `secrets.compare_digest` is the
    stdlib-blessed version."""
    import secrets as _s

    return _s.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def _parse_cookies(scope) -> dict[str, str]:
    """Pull cookies out of a raw ASGI scope. Starlette's `Request`
    object would do this for us, but constructing a Request inside
    pure ASGI middleware defeats the purpose of being pure ASGI."""
    for k, v in scope.get("headers", []):
        if k == b"cookie":
            raw = v.decode("latin-1")
            out: dict[str, str] = {}
            for part in raw.split("; "):
                if "=" in part:
                    name, _, value = part.partition("=")
                    out[name] = value
            return out
    return {}


def _get_header(scope, name: str) -> str | None:
    key = name.lower().encode("latin-1")
    for k, v in scope.get("headers", []):
        if k == key:
            return v.decode("latin-1")
    return None


class CSRFMiddleware:
    """Double-submit cookie CSRF protection — pure-ASGI implementation.

    Only enforced when the request carries an `access_token` cookie:
      - GET/HEAD/OPTIONS are exempt (HTTP semantics — no side effects).
      - Mutating methods without the auth cookie are exempt — they
        have no cookie-based credential to abuse.
      - Mutating methods WITH the auth cookie must echo `csrf_token`
        in the `X-CSRF-Token` header. Constant-time compare.

    Pure ASGI (no `BaseHTTPMiddleware`) so it composes cleanly with
    asyncpg under `httpx.TestClient` — see `tests/conftest.py` for
    the loop-binding issue that made the old `@app.middleware("http")`
    decorator unworkable in tests.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope["method"]
        if method in CSRF_PROTECTED_METHODS:
            cookies = _parse_cookies(scope)
            if cookies.get(ACCESS_TOKEN_COOKIE):
                cookie_csrf = cookies.get(CSRF_TOKEN_COOKIE, "")
                header_csrf = _get_header(scope, CSRF_HEADER) or ""
                if not cookie_csrf or not _consteq(cookie_csrf, header_csrf):
                    response = JSONResponse(
                        {"detail": "CSRF token missing or invalid"},
                        status_code=403,
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)


class RequestContextMiddleware:
    """Per-request request-id, structlog binding, timing, and
    last-resort exception → 500 with the request id surfaced. Pure
    ASGI: wraps `send` to inject `X-Request-ID` into the response
    headers and to record the response status for logging.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Pull request_id from header or mint a fresh one.
        request_id = _get_header(scope, "X-Request-ID") or uuid.uuid4().hex
        method = scope["method"]
        path = scope.get("path", "")

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, method=method, path=path)
        start = time.perf_counter()

        # Captured-by-closure state for the send wrapper.
        status_holder: dict[str, int] = {"status": 500}
        rid_bytes = request_id.encode("latin-1")

        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message.get("status", 0)
                # Inject X-Request-ID into the outgoing response headers.
                headers = list(message.get("headers") or [])
                # Replace any pre-existing X-Request-ID to keep one value.
                headers = [h for h in headers if h[0].lower() != b"x-request-id"]
                headers.append((b"x-request-id", rid_bytes))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            log.exception("unhandled_error")
            # We can only synthesize a 500 here if the response hasn't
            # started yet. If headers were already sent the client
            # gets a truncated response; the log line above is the
            # only record left, which is the standard ASGI contract.
            response = JSONResponse(
                {"detail": "Internal server error", "request_id": request_id},
                status_code=500,
            )
            try:
                await response(scope, receive, send_with_request_id)
            except Exception:
                pass  # headers already sent — nothing we can do
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            log.info("request", status=500, duration_ms=elapsed_ms)
            return

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        log.info("request", status=status_holder["status"], duration_ms=elapsed_ms)


# Order matters: outer middleware runs first on the request path AND
# last on the response path. We want request-context (logging) to be
# the OUTERMOST so it sees every request and every response status,
# including 403 short-circuits from CSRF. add_middleware prepends, so
# the LAST add becomes the outermost layer.
app.add_middleware(CSRFMiddleware)
# Prometheus instrumentation outside CSRF so we count even 403'd
# requests (operationally interesting — a spike in CSRF rejections
# is a useful signal). Inside the request-context layer though so
# /metrics scrapes themselves get the request-id logging.
app.add_middleware(PrometheusMiddleware)
app.add_middleware(RequestContextMiddleware)


app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(leads.router)
app.include_router(customers.router)
app.include_router(deals.router)
app.include_router(quotes.router)
app.include_router(signatures.router)
app.include_router(tasks.router)
app.include_router(dashboard.router)
app.include_router(assistant.router)
app.include_router(trash.router)
app.include_router(audit.router)
app.include_router(outbox.router)
app.include_router(webhooks.router)
app.include_router(activities.router)
app.include_router(notes.router)
app.include_router(attachments.router)
app.include_router(teams.router)
app.include_router(pipelines.router)
app.include_router(notifications.router)
# Org membership / switch / create — feeds the org switcher UI.
# Mounted BEFORE invites so its /api/orgs/me and /api/orgs/me/switch
# routes are matched first against the more general /api/orgs prefix.
app.include_router(orgs.router)
# Invites split into three routers because the auth surface differs:
# admin-protected create/list/revoke, public preview by token, public
# accept-and-register.
app.include_router(invites.admin_router)
app.include_router(invites.public_router)
app.include_router(invites.accept_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — process is up."""
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus scrape endpoint. Hidden from the OpenAPI schema
    because it's an ops-facing surface, not an API consumer one."""
    return metrics_response()


@app.get("/ready")
async def ready():
    """Readiness probe — fails fast if any required dep is unhealthy.

    Components:
      * `db`     — required. Postgres is fatal; without it nothing works.
      * `redis`  — required. Sessions and refresh-tokens live there;
                   without it auth itself starts failing within minutes.
      * `llm`    — optional. We probe Ollama (or the configured LLM
                   provider) for completeness, but a missing LLM
                   degrades AI features rather than killing the
                   service. Marked `degraded`, not `down`, on miss.

    Returns 503 when any REQUIRED component is down. The body always
    surfaces a per-component map so monitoring can attribute outages
    without re-probing each dep.
    """
    components: dict[str, dict[str, str]] = {}

    # ----- DB (required) -----
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        components["db"] = {"status": "ok"}
    except Exception as e:
        components["db"] = {"status": "down", "detail": str(e)[:200]}

    # ----- Redis (required) -----
    try:
        from app.redis_client import get_redis

        await get_redis().ping()
        components["redis"] = {"status": "ok"}
    except Exception as e:
        components["redis"] = {"status": "down", "detail": str(e)[:200]}

    # ----- LLM (optional, best-effort) -----
    # We don't `await` heavy generation; a TCP-level probe to the
    # provider's base URL is enough to know "is it reachable?".
    try:
        import httpx

        if settings.llm_provider == "ollama":
            async with httpx.AsyncClient(timeout=2.0) as http:
                await http.get(f"{settings.ollama_url}/api/tags")
            components["llm"] = {"status": "ok", "provider": "ollama"}
        elif settings.llm_provider == "anthropic":
            # Reachability only — don't burn API credit. The presence
            # of a non-empty key signals the operator intended to use
            # Anthropic; we leave deep health checks to the actual
            # generation paths.
            if settings.anthropic_api_key:
                components["llm"] = {"status": "ok", "provider": "anthropic"}
            else:
                components["llm"] = {
                    "status": "degraded",
                    "detail": "ANTHROPIC_API_KEY empty",
                }
        else:
            components["llm"] = {
                "status": "degraded",
                "detail": f"unknown provider {settings.llm_provider!r}",
            }
    except Exception as e:
        components["llm"] = {"status": "degraded", "detail": str(e)[:200]}

    required_down = any(components[k]["status"] == "down" for k in ("db", "redis"))
    overall = "down" if required_down else "ready"
    payload = {"status": overall, "components": components}
    return JSONResponse(payload, status_code=503 if required_down else 200)

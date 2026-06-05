"""Pytest fixtures for the backend test suite.

Design choices:

* **Same DB as dev.** Tests run against `crm`, not a separate database.
  Test rows are namespaced (`pytest-org*` slug + `pytest-*@example.com`
  emails); an autouse cleanup fixture truncates them before AND after
  each test so a crash mid-test doesn't poison the next run.

* **Two engines.** `admin_engine` uses the owner role (`crm`,
  SUPERUSER, BYPASSRLS) — exclusively for direct fixture setup and
  teardown. The FastAPI app continues to use the runtime engine
  (`crm_app`, NOSUPERUSER NOBYPASSRLS) so every HTTP test exercises
  RLS the same way production will.

* **httpx ASGITransport.** Drives the FastAPI app in-process — no
  network, no separate uvicorn. `asgi_lifespan.LifespanManager`
  ensures startup/shutdown events fire so the redis pool, etc., are
  ready.

* **CSRF auto-attach.** A custom `AuthedClient` wrapper reads the
  `csrf_token` cookie and injects `X-CSRF-Token` on every mutating
  request, mirroring what the real frontend does. Without it the
  CSRF middleware would 403 every POST.

* **Rate limiter.** Reset between tests so a test with several
  /login calls doesn't trip the 5/min/IP guard.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.main import app

# We KEEP the runtime engine's default QueuePool — production's RLS
# depends on session-level GUCs surviving commits, which only the
# real pool guarantees. NullPool destroys the connection between
# transactions, wiping the GUC.
from app.models import Organization, OrgMembership, User, UserRole
from app.rate_limit import limiter
from app.security import hash_password

settings = get_settings()

# Seed/teardown engine is SYNC (psycopg2) on purpose: tests run the
# app inside `httpx.TestClient`'s BlockingPortal (one anyio loop)
# while pytest-asyncio fixtures use a different loop. Mixing two
# async engines across those loops triggers "Future attached to a
# different loop" errors deep in asyncpg. A sync engine has no loop
# at all, so it composes cleanly with both contexts. It connects as
# the owner role (`crm`, BYPASSRLS) so seed/teardown can write
# across orgs.
admin_engine = create_engine(settings.sync_database_url, future=True)
AdminSession = sessionmaker(admin_engine, expire_on_commit=False, class_=Session)

TEST_PASSWORD = "PytestPass2026!"

# Deterministic slugs / emails so the cleanup fixture can wipe them
# without nuking real dev data.
PYTEST_PREFIX = "pytest-"


# ---------- Per-test cleanup ----------


def _wipe_test_rows() -> None:
    """Delete every row tagged with the pytest prefix. CASCADE on
    organizations FK takes care of memberships, leads, etc.
    Synchronous: see admin_engine comment for why."""
    with AdminSession() as s:
        s.execute(
            text("DELETE FROM organizations WHERE slug LIKE :pat"),
            {"pat": f"{PYTEST_PREFIX}%"},
        )
        s.execute(
            text("DELETE FROM users WHERE email LIKE :pat"),
            {"pat": f"{PYTEST_PREFIX}%"},
        )
        s.commit()


@pytest.fixture(autouse=True)
def clean_db():
    """Wipe pytest-namespaced rows before AND after each test.

    Belt-and-suspenders: the "before" wipe handles the case where a
    previous run crashed without teardown; the "after" wipe handles
    the normal happy path.
    """
    _wipe_test_rows()
    # Reset the slowapi limiter so per-test /login budgets are fresh.
    try:
        limiter.reset()
    except Exception:
        pass
    yield
    _wipe_test_rows()


# ---------- Direct DB session (owner role, RLS-bypassing) ----------


@pytest.fixture
def db():
    """Owner-role SYNC session for fixture-style DB writes inside
    tests. Use this for seeding rows; use the HTTP client for
    exercising the actual endpoints."""
    with AdminSession() as session:
        yield session


# ---------- Org + user factories ----------


@pytest.fixture
def test_org(db: Session) -> Organization:
    org = Organization(name="Pytest Org", slug=f"{PYTEST_PREFIX}org")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def other_org(db: Session) -> Organization:
    """A SECOND org used for cross-org negative tests (kalle can't
    see the other org's data)."""
    org = Organization(name="Pytest Other Org", slug=f"{PYTEST_PREFIX}other")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(
    db: Session,
    org: Organization,
    *,
    email: str,
    role: UserRole = UserRole.sales_agent,
) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=hash_password(TEST_PASSWORD),
        role=role,
        locale="en",
        last_active_org_id=org.id,
        # Seeded directly (out-of-band, like the first user / an invitee),
        # so treat as already email-verified — otherwise login would 403
        # with email_not_verified. The verification flow is exercised
        # explicitly in test_auth.py.
        email_verified=True,
    )
    db.add(user)
    db.flush()
    db.add(OrgMembership(user_id=user.id, organization_id=org.id, role=role))
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_user(db: Session, test_org: Organization) -> User:
    return _make_user(db, test_org, email=f"{PYTEST_PREFIX}admin@example.com", role=UserRole.admin)


@pytest.fixture
def other_user(db: Session, test_org: Organization) -> User:
    """A second user in the SAME org used for ownership negative
    tests (non-owner non-admin gets 403 on mutate)."""
    return _make_user(
        db, test_org, email=f"{PYTEST_PREFIX}other@example.com", role=UserRole.sales_agent
    )


@pytest.fixture
def foreign_user(db: Session, other_org: Organization) -> User:
    """A user in a DIFFERENT org used for cross-org negative tests."""
    return _make_user(
        db, other_org, email=f"{PYTEST_PREFIX}foreign@example.com", role=UserRole.admin
    )


# ---------- HTTP client ----------


class CsrfAwareClient(TestClient):
    """Auto-attach `X-CSRF-Token` from the `csrf_token` cookie on every
    mutating request, just like the real SPA does. Without this every
    POST/PATCH/DELETE/PUT trips the CSRF middleware.

    We use the SYNC TestClient (which manages its own anyio
    BlockingPortal under the hood) instead of httpx.AsyncClient.
    AsyncClient + ASGITransport + BaseHTTPMiddleware-style middleware
    + asyncpg pool is a known-bad combo: the middleware spawns its
    task on a different anyio task than the asyncpg connection was
    opened on, and asyncpg refuses cross-loop ops. TestClient
    sidesteps this by running the app on its own loop in a worker
    thread.
    """

    _MUTATING: ClassVar[set[str]] = {"POST", "PUT", "PATCH", "DELETE"}

    def request(self, method: str, url, **kwargs):  # type: ignore[override]
        if method.upper() in self._MUTATING:
            csrf = self.cookies.get("csrf_token")
            if csrf:
                headers = dict(kwargs.pop("headers", None) or {})
                headers.setdefault("X-CSRF-Token", csrf)
                kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


@pytest.fixture(scope="session")
def _client_session():
    """Session-scoped TestClient. One BlockingPortal (and one anyio
    event loop) for the whole suite — required so the runtime
    engine's asyncpg pool can stay bound to a single loop. A
    function-scoped client would create a new portal per test and
    invalidate the engine pool from test #2 on."""
    with CsrfAwareClient(app, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def client(_client_session: CsrfAwareClient):
    """Per-test view of the session client. Wipes cookies before
    yielding so each test starts unauthenticated — the actual login
    fixtures populate cookies again."""
    _client_session.cookies.clear()
    yield _client_session
    _client_session.cookies.clear()


def _login(client: CsrfAwareClient, email: str, password: str = TEST_PASSWORD) -> None:
    r = client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"


@pytest.fixture
def admin_client(client: CsrfAwareClient, admin_user: User) -> CsrfAwareClient:
    """Client already logged-in as the test admin (cookies set)."""
    _login(client, admin_user.email)
    return client


@pytest.fixture
def other_client(client: CsrfAwareClient, other_user: User) -> CsrfAwareClient:
    """A SECOND client logged in as the non-admin user in the same
    org — used for ownership negative tests."""
    _login(client, other_user.email)
    return client


# ---------- Misc ----------


@pytest.fixture(autouse=True)
def _no_dep_overrides():
    """Make sure no test leaks dep overrides into the next one."""
    yield
    app.dependency_overrides.clear()

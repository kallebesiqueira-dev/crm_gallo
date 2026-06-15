#!/usr/bin/env python3
"""Post-deploy smoke test for Gallo CRM (launch roadmap: post-deploy smoke).

Black-box checks against a LIVE deployment - run it right after
`railway redeploy` to catch a broken ship before users do. Stdlib only (no
pip install), so it runs anywhere: a laptop, CI, or a deploy hook.

    python scripts/post_deploy_smoke.py                 # prod (default)
    python scripts/post_deploy_smoke.py --api http://localhost:8000 \
                                        --app http://localhost:3000

Exit code 0 = all checks passed, 1 = at least one failed (CI-friendly).

It only exercises the UNAUTHENTICATED surface (health, security headers,
route gating, error handling, SEO) - it never needs credentials and never
mutates anything, so it's safe to run against production on every deploy.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request

DEFAULT_API = "https://api.gallo-crm.com"
DEFAULT_APP = "https://app.gallo-crm.com"
TIMEOUT = 15

_failures: list[str] = []
_passes = 0


def _request(method: str, url: str) -> tuple[int, dict[str, str], str]:
    """Return (status, headers_lower, body) without following redirects so
    307/401/404 can be asserted exactly."""

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):  # noqa: D401
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, method=method)
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            body = resp.read(8192).decode("utf-8", "replace")
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body
    except urllib.error.HTTPError as e:
        body = e.read(8192).decode("utf-8", "replace") if e.fp else ""
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, body


def check(name: str, ok: bool, detail: str = "") -> None:
    global _passes
    if ok:
        _passes += 1
        print(f"  PASS  {name}")
    else:
        _failures.append(name)
        print(f"  FAIL  {name}  {detail}")


def expect_status(name: str, method: str, url: str, want: int | set[int]) -> None:
    want_set = {want} if isinstance(want, int) else want
    try:
        status, _, _ = _request(method, url)
    except Exception as e:  # network/DNS/timeout
        check(name, False, f"request error: {type(e).__name__}: {e}")
        return
    check(name, status in want_set, f"got {status}, want {sorted(want_set)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Gallo CRM post-deploy smoke test")
    ap.add_argument("--api", default=DEFAULT_API, help="API base URL")
    ap.add_argument("--app", default=DEFAULT_APP, help="frontend base URL")
    args = ap.parse_args()
    api = args.api.rstrip("/")
    app = args.app.rstrip("/")

    print(f"Smoke test - api={api} app={app}")

    print("API - health")
    expect_status("GET /ready -> 200", "GET", f"{api}/ready", 200)
    expect_status("GET /health -> 200", "GET", f"{api}/health", 200)

    print("API - security headers (/ready)")
    try:
        _, headers, _ = _request("GET", f"{api}/ready")
        check("HSTS present", "strict-transport-security" in headers)
        check("CSP present", "content-security-policy" in headers)
        check(
            "X-Content-Type-Options: nosniff",
            headers.get("x-content-type-options", "").lower() == "nosniff",
        )
        check(
            "X-Frame-Options: DENY",
            headers.get("x-frame-options", "").upper() == "DENY",
        )
    except Exception as e:
        check("security headers", False, str(e))

    print("API - auth gating (no creds -> 401)")
    for path in (
        "/api/leads",
        "/api/dashboard/stats",
        "/api/fx/rates",
        "/api/llm-usage/summary",
        "/api/v1/leads",
    ):
        expect_status(f"GET {path} -> 401", "GET", f"{api}{path}", 401)

    print("API - error handling")
    expect_status("unknown route -> 404", "GET", f"{api}/api/nope", 404)
    expect_status("/docs not exposed -> 404", "GET", f"{api}/docs", 404)
    expect_status("/openapi.json not exposed -> 404", "GET", f"{api}/openapi.json", 404)
    expect_status(
        "OAuth start -> 307", "GET", f"{api}/api/auth/oauth/microsoft/start", {302, 307}
    )

    print("APP - pages + SEO")
    expect_status("GET / -> 200/307", "GET", f"{app}/", {200, 307, 308})
    expect_status("GET /en -> 200", "GET", f"{app}/en", 200)
    try:
        status, _, body = _request("GET", f"{app}/robots.txt")
        check(
            "robots.txt -> 200 + Sitemap",
            status == 200 and "Sitemap:" in body,
            f"status={status}",
        )
        status, _, body = _request("GET", f"{app}/sitemap.xml")
        check(
            "sitemap.xml -> 200 + <urlset",
            status == 200 and "<urlset" in body,
            f"status={status}",
        )
    except Exception as e:
        check("SEO files", False, str(e))

    total = _passes + len(_failures)
    print(f"\n{_passes}/{total} checks passed.")
    if _failures:
        print("FAILED: " + ", ".join(_failures))
        return 1
    print("All smoke checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Prometheus metrics — request count, latency histogram, error rate.

Exposed at `/metrics` in the Prometheus text exposition format. A
Prometheus server (or any compatible scraper) hits this endpoint
every N seconds and stores the deltas as time series.

Cardinality choices:
  * Route is the FastAPI route template (e.g. `/api/leads/{lead_id}`),
    NOT the rendered path. Otherwise one label per UUID would explode
    cardinality and OOM the Prometheus store.
  * Status is the integer status code as a string. ~6 distinct values
    in practice (200, 201, 204, 400, 401, 403, 404, 500).
  * Method is the HTTP verb. Bounded.

We deliberately don't label by user / org — that's PII for log
storage, not for an open metrics endpoint.
"""

from __future__ import annotations

import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests processed.",
    labelnames=("method", "route", "status"),
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Latency of HTTP requests, in seconds.",
    labelnames=("method", "route"),
    # Buckets chosen for a typical CRUD API: sub-10ms = good, 100ms
    # is the eyebrow-raiser, anything >1s = paging the operator.
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


OUTBOX_PENDING = Gauge(
    "outbox_events_pending_total",
    "Number of outbox_events rows not yet processed (processed_at IS NULL).",
)

REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently being processed.",
    labelnames=("method",),
)


class PrometheusMiddleware:
    """Pure-ASGI middleware: time every HTTP request and increment the
    counters / observe the histogram. Same pattern as the other
    middlewares in `main.py` (avoids `BaseHTTPMiddleware` + asyncpg
    loop-binding issues).

    Route template extraction: Starlette stashes the matched route on
    `scope["route"]` after routing — but routing happens INSIDE the
    middleware chain. We can read `scope["route"].path` after the
    downstream app has matched, OR fall back to the raw path. We use
    the fallback for unmatched paths (404s on unknown URLs) so we
    don't accumulate one label per typo.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Skip /metrics itself — would create a self-incrementing loop
        # and confuse rate() calculations on the scraper side.
        path = scope.get("path", "")
        if path == "/metrics":
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        start = time.perf_counter()
        status_holder = {"status": 500}
        REQUESTS_IN_PROGRESS.labels(method=method).inc()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            REQUESTS_IN_PROGRESS.labels(method=method).dec()
            elapsed = time.perf_counter() - start
            # Prefer the matched route template; fall back to the raw
            # path if routing didn't run (e.g. middleware short-
            # circuited with a 403 before reaching the router).
            route_obj = scope.get("route")
            route_label = (
                getattr(route_obj, "path", None) if route_obj is not None else path
            ) or path
            REQUEST_COUNT.labels(
                method=method, route=route_label, status=str(status_holder["status"])
            ).inc()
            REQUEST_LATENCY.labels(method=method, route=route_label).observe(elapsed)


def metrics_response() -> Response:
    """Return the Prometheus exposition payload for the default
    registry. Wired into FastAPI as `GET /metrics`."""
    data = generate_latest(REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

"""Per-user rate limit on the LLM-cost endpoints (§327-328).

`/api/leads/{id}/score` is capped at 10/hour/user to protect against a
runaway client racking up Ollama/Anthropic spend. The cap is keyed on
the JWT `sub` (see `app/rate_limit.py::user_or_ip_key`), not the client
IP, so an office behind one NAT doesn't share a bucket.

The test exploits a cheap fact: `score` runs `_get_lead_or_404` BEFORE
the LLM call, so scoring a non-existent lead returns 404 without ever
touching Ollama — yet each attempt still consumes a rate-limit slot.
That lets us exhaust the bucket deterministically (10×404) and assert
the 11th call is rejected with 429, with no LLM in the loop.

(The `clean_db` autouse fixture resets the slowapi limiter between
tests, so the bucket starts empty here.)
"""

from __future__ import annotations

import uuid

from tests.conftest import CsrfAwareClient


def test_score_rate_limit_returns_429_after_cap(admin_client: CsrfAwareClient):
    ghost = uuid.uuid4()  # never exists → 404 before the LLM call

    # The default cap is 10/hour. The first 10 attempts get past the
    # limiter (and 404 on the missing lead); the 11th trips it.
    for _ in range(10):
        r = admin_client.post(f"/api/leads/{ghost}/score")
        assert r.status_code == 404, r.text

    r = admin_client.post(f"/api/leads/{ghost}/score")
    assert r.status_code == 429, r.text

"""Coverage for the admin dead-letter-queue inspector (/api/admin/dlq).

Admin-only Redis-backed view of terminally-failed jobs. These cover the
authz gate and the list/count/purge contract; seeding a real dead job needs
the worker, so the happy path asserts the empty/purged state deterministically.
"""

from __future__ import annotations


def test_dlq_requires_auth(client):
    assert client.get("/api/admin/dlq").status_code == 401
    assert client.get("/api/admin/dlq/count").status_code == 401


def test_dlq_non_admin_forbidden(other_client):
    # sales_agent is below admin → blocked during dependency resolution.
    assert other_client.get("/api/admin/dlq").status_code == 403
    assert other_client.get("/api/admin/dlq/count").status_code == 403
    assert other_client.delete("/api/admin/dlq").status_code == 403


def test_dlq_list_count_and_purge(admin_client):
    # Purge first so the view is deterministic regardless of prior state.
    assert admin_client.delete("/api/admin/dlq").status_code == 204

    listed = admin_client.get("/api/admin/dlq")
    assert listed.status_code == 200
    assert listed.json() == []

    count = admin_client.get("/api/admin/dlq/count")
    assert count.status_code == 200
    assert count.json() == {"count": 0}

"""Activities must be emitted by customer + deal mutations so the
detail-page timelines have something to render. Lead already wired;
this covers the customer/deal gap."""

from __future__ import annotations

from tests.conftest import CsrfAwareClient


def _types(client: CsrfAwareClient, entity_type: str, entity_id: str) -> list[str]:
    r = client.get(f"/api/activities?entity_type={entity_type}&entity_id={entity_id}")
    assert r.status_code == 200, r.text
    return [a["type"] for a in r.json()]


def test_customer_mutations_emit_activities(admin_client: CsrfAwareClient):
    r = admin_client.post(
        "/api/customers",
        json={"first_name": "Acme", "last_name": "Co", "email": "acme@example.com"},
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    r = admin_client.patch(f"/api/customers/{cid}", json={"company": "Acme Inc"})
    assert r.status_code == 200, r.text

    types = _types(admin_client, "customer", cid)
    assert "created" in types
    assert "updated" in types


def test_deal_mutations_emit_activities(admin_client: CsrfAwareClient):
    r = admin_client.post(
        "/api/deals",
        json={"title": "Big deal", "stage": "new", "value": "1000.00"},
    )
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    version = r.json()["version"]

    r = admin_client.patch(
        f"/api/deals/{did}",
        json={"title": "Bigger deal"},
        headers={"If-Match": str(version)},
    )
    assert r.status_code == 200, r.text
    version = r.json()["version"]

    r = admin_client.post(
        f"/api/deals/{did}/move",
        json={"stage": "qualified", "sort_index": 0},
        headers={"If-Match": str(version)},
    )
    assert r.status_code == 200, r.text

    types = _types(admin_client, "deal", did)
    assert "created" in types
    assert "updated" in types
    assert "stage_change" in types

"""Coverage for file attachments (/api/attachments).

Multipart upload → S3 (MinIO in the test stack), metadata row in Postgres,
then list / presigned-download / soft-delete. `entity_id` is a polymorphic
pointer with no FK, so a random uuid is a valid attach target.
"""

from __future__ import annotations

import uuid


def test_list_requires_auth(client):
    eid = uuid.uuid4()
    # Valid query params so only the missing auth can fail it.
    r = client.get(f"/api/attachments?entity_type=lead&entity_id={eid}")
    assert r.status_code == 401


def test_upload_list_download_delete(admin_client):
    eid = str(uuid.uuid4())
    files = {"file": ("note.txt", b"hello world", "text/plain")}
    created = admin_client.post(
        "/api/attachments", data={"entity_type": "lead", "entity_id": eid}, files=files
    )
    assert created.status_code == 201, created.text
    att = created.json()
    aid = att["id"]
    assert att["filename"] == "note.txt"
    assert att["size_bytes"] == len(b"hello world")
    assert att["content_type"] == "text/plain"

    # Shows up in the entity's attachment list.
    listed = admin_client.get(f"/api/attachments?entity_type=lead&entity_id={eid}").json()
    assert any(a["id"] == aid for a in listed)

    # Presigned download URL is fetched on demand.
    dl = admin_client.get(f"/api/attachments/{aid}/download")
    assert dl.status_code == 200
    assert dl.json()["url"]
    assert dl.json()["expires_in"] > 0

    # Soft-delete → gone from the list.
    assert admin_client.delete(f"/api/attachments/{aid}").status_code == 204
    after = admin_client.get(f"/api/attachments?entity_type=lead&entity_id={eid}").json()
    assert not any(a["id"] == aid for a in after)


def test_upload_empty_file_is_400(admin_client):
    files = {"file": ("empty.txt", b"", "text/plain")}
    r = admin_client.post(
        "/api/attachments",
        data={"entity_type": "lead", "entity_id": str(uuid.uuid4())},
        files=files,
    )
    assert r.status_code == 400


def test_download_unknown_is_404(admin_client):
    assert admin_client.get(f"/api/attachments/{uuid.uuid4()}/download").status_code == 404

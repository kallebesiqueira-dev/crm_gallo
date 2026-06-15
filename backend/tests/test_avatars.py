"""Coverage for avatars (/api/avatars/{entity_type}/{entity_id}).

Image-only upload to S3 (MinIO in the test stack) for user/customer/company.
The `user` entity is locked to the caller; customer/company are org-scoped
and 404 when absent. Upload validates the content-type is an image.
"""

from __future__ import annotations

import uuid

_PNG = ("a.png", b"\x89PNG\r\n\x1a\n fake-but-typed-png", "image/png")


def test_get_requires_auth(client):
    assert client.get(f"/api/avatars/user/{uuid.uuid4()}").status_code == 401


def test_get_own_user_avatar_empty(admin_client, admin_user):
    r = admin_client.get(f"/api/avatars/user/{admin_user.id}")
    assert r.status_code == 200
    assert r.json()["url"] is None  # none uploaded yet


def test_get_other_user_avatar_404(admin_client):
    # The `user` entity is locked to the caller's own id.
    assert admin_client.get(f"/api/avatars/user/{uuid.uuid4()}").status_code == 404


def test_upload_user_avatar_then_get_returns_url(admin_client, admin_user):
    files = {"file": _PNG}
    up = admin_client.post(f"/api/avatars/user/{admin_user.id}", files=files)
    assert up.status_code == 200, up.text
    assert up.json()["url"]
    # A subsequent GET now returns a presigned URL.
    assert admin_client.get(f"/api/avatars/user/{admin_user.id}").json()["url"]


def test_upload_non_image_is_400(admin_client, admin_user):
    files = {"file": ("a.txt", b"not an image", "text/plain")}
    r = admin_client.post(f"/api/avatars/user/{admin_user.id}", files=files)
    assert r.status_code == 400


def test_customer_avatar_unknown_is_404(admin_client):
    files = {"file": _PNG}
    r = admin_client.post(f"/api/avatars/customer/{uuid.uuid4()}", files=files)
    assert r.status_code == 404

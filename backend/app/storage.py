"""S3-compatible object storage adapter for FileAttachments.

Why boto3 (sync) wrapped in `run_in_executor`:
  * `aioboto3` exists but adds a dep + its API drifts behind boto3.
  * Uploads/downloads from a CRM are typically a few MB at a time,
    not enough to justify async streaming overhead.
  * We use `asyncio.to_thread` so the asyncpg event loop is never
    blocked by a slow S3 RTT.

Bucket bootstrap: `ensure_bucket()` is called from FastAPI's
lifespan startup. Idempotent — creates the bucket if missing,
no-ops if it already exists. This lets a fresh `docker compose up`
work without a manual MinIO console step.

Object key layout: `org-{org_id}/{entity_type}/{entity_id}/{attachment_uuid}`.
Tenant-prefixed so a misconfigured bucket policy at least keeps the
blast radius per-org instead of per-install; the attachment UUID is
the last segment so listing one entity's blobs is a single S3
`list-objects-v2` with that prefix.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import IO

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import get_settings

_settings = get_settings()
_client = None


def _s3():
    """Lazy singleton client. boto3 clients are thread-safe."""
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=_settings.s3_endpoint_url or None,
            aws_access_key_id=_settings.s3_access_key_id,
            aws_secret_access_key=_settings.s3_secret_access_key,
            region_name=_settings.s3_region,
            # Path-style addressing — MinIO requires it, real AWS S3
            # supports it; virtual-host style needs DNS for every
            # bucket so we just standardise on path.
            config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
    return _client


def object_key(
    organization_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> str:
    """Build the canonical S3 object key for an attachment."""
    return f"org-{organization_id}/{entity_type}/{entity_id}/{attachment_id}"


async def ensure_bucket() -> None:
    """Create the configured bucket if it doesn't exist. Called from
    `main.lifespan` so the app boots straight into a working state on
    a fresh MinIO volume.

    Tolerates `BucketAlreadyOwnedByYou` (the second startup race) and
    `BucketAlreadyExists` (someone-else-took-the-name; in real AWS
    this would 503 our deploy — for MinIO it's a no-op).
    """

    def _sync():
        s3 = _s3()
        try:
            s3.head_bucket(Bucket=_settings.s3_bucket)
            return
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code not in ("404", "NoSuchBucket", "NotFound"):
                raise
        try:
            s3.create_bucket(Bucket=_settings.s3_bucket)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise

    await asyncio.to_thread(_sync)


async def put_object(key: str, body: bytes | IO[bytes], content_type: str) -> None:
    """Upload `body` to `key`. `content_type` controls what the
    presigned-download URL serves as Content-Type — important for
    inline-view of PDFs / images in the browser."""

    def _sync():
        _s3().put_object(
            Bucket=_settings.s3_bucket,
            Key=key,
            Body=body,
            ContentType=content_type or "application/octet-stream",
        )

    await asyncio.to_thread(_sync)


async def delete_object(key: str) -> None:
    """Hard-delete from the bucket. Called from the attachment soft-
    delete endpoint — the DB row stays (audit + restore), the blob
    goes immediately to free storage. Trade-off: restore would
    require a fresh upload."""

    def _sync():
        _s3().delete_object(Bucket=_settings.s3_bucket, Key=key)

    await asyncio.to_thread(_sync)


async def presigned_download_url(key: str, filename: str | None = None) -> str:
    """Time-limited URL the browser can hit directly to download the
    file. We override `Content-Disposition` so the browser uses the
    original filename instead of the opaque attachment UUID."""

    def _sync():
        params: dict[str, str] = {"Bucket": _settings.s3_bucket, "Key": key}
        if filename:
            # `attachment; filename="…"` forces a save-as with the
            # original name. Without it the browser saves as the
            # last path segment (the attachment UUID).
            safe = filename.replace('"', "")
            params["ResponseContentDisposition"] = f'attachment; filename="{safe}"'
        return _s3().generate_presigned_url(
            "get_object", Params=params, ExpiresIn=_settings.s3_download_url_ttl
        )

    return await asyncio.to_thread(_sync)

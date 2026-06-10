"""message media storage key

Adds `messages.media_storage_key` — the S3 object key where an INBOUND WhatsApp
media message's bytes are mirrored (off Meta's short-lived CDN) by the
`mirror_whatsapp_media` worker job. Null for text / not-yet-mirrored rows.

Plain nullable column add — no backfill, no rewrite.

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4
Create Date: 2026-06-09 16:30:00.000000+00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("media_storage_key", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "media_storage_key")

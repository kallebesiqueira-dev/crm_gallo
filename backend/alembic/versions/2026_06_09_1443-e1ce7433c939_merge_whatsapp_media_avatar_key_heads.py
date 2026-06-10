"""merge whatsapp media + avatar_key heads

Revision ID: e1ce7433c939
Revises: aa11bb22cc33, a0b1c2d3e4f5
Create Date: 2026-06-09 14:43:56.264073+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1ce7433c939'
down_revision: Union[str, None] = ('aa11bb22cc33', 'a0b1c2d3e4f5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

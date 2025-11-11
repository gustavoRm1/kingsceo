"""add spoiler flag to categories

Revision ID: 20251111_0005
Revises: 20251110_0004
Create Date: 2025-11-11 01:25:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20251111_0005"
down_revision: Union[str, None] = "20251110_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "category",
        sa.Column("use_spoiler_media", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("category", "use_spoiler_media")



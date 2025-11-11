"""category randomization flags

Revision ID: 20251110_0003
Revises: 20251110_0002
Create Date: 2025-11-10 23:15:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20251110_0003"
down_revision: Union[str, None] = "20251110_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "category",
        sa.Column("use_random_copy", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "category",
        sa.Column("use_random_media", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "category",
        sa.Column("use_spoiler_media", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("category", "use_spoiler_media")
    op.drop_column("category", "use_random_media")
    op.drop_column("category", "use_random_copy")


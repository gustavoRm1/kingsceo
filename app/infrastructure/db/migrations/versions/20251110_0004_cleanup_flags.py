"""service cleanup flags

Revision ID: 20251110_0004
Revises: 20251110_0003
Create Date: 2025-11-10 23:35:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20251110_0004"
down_revision: Union[str, None] = "20251110_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "\"group\"",
        sa.Column("clean_service_messages", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "media_repository",
        sa.Column("clean_service_messages", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("media_repository", "clean_service_messages")
    op.drop_column("\"group\"", "clean_service_messages")


"""media repository mapping

Revision ID: 20251110_0002
Revises: 20251110_0001
Create Date: 2025-11-10 22:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20251110_0002"
down_revision: Union[str, None] = "20251110_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_repository",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["category.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id"),
    )
    op.create_index("ix_media_repository_category_id", "media_repository", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_media_repository_category_id", table_name="media_repository")
    op.drop_table("media_repository")


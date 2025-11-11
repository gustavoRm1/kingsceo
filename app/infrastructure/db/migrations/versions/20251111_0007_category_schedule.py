"""Adiciona campos de agendamento na categoria."""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251111_0007_category_schedule"
down_revision: str = "20251111_0006_group_category_nullable"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "category",
        sa.Column("dispatch_interval_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "category",
        sa.Column("next_dispatch_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("category", "next_dispatch_at")
    op.drop_column("category", "dispatch_interval_minutes")
"""add scheduling fields to category

Revision ID: 20251111_0007
Revises: 20251111_0006
Create Date: 2025-11-11 02:55:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20251111_0007"
down_revision: Union[str, None] = "20251111_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "category",
        sa.Column("dispatch_interval_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "category",
        sa.Column("next_dispatch_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("category", "next_dispatch_at")
    op.drop_column("category", "dispatch_interval_minutes")


"""make group.category_id nullable

Revision ID: 20251111_0006
Revises: 20251111_0005
Create Date: 2025-11-11 02:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20251111_0006"
down_revision: Union[str, None] = "20251111_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("group", "category_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.execute(
        "DELETE FROM \"group\" WHERE category_id IS NULL"
    )
    op.alter_column("group", "category_id", existing_type=sa.Integer(), nullable=False)


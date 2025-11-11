"""Make group.category_id nullable."""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251111_0006"
down_revision: str = "20251111_0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("group", "category_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.execute('DELETE FROM "group" WHERE category_id IS NULL')
    op.alter_column("group", "category_id", existing_type=sa.Integer(), nullable=False)

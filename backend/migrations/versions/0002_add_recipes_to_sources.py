"""Add sources.recipe and recipe_learned_at, for recipes the AI learns (Phase 2).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-31 22:16:48.313661

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sources", sa.Column("recipe", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        "sources", sa.Column("recipe_learned_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("sources", "recipe_learned_at")
    op.drop_column("sources", "recipe")

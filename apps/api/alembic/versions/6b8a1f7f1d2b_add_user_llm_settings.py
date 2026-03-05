"""add user llm settings

Revision ID: 6b8a1f7f1d2b
Revises: 626926e59353
Create Date: 2026-03-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6b8a1f7f1d2b"
down_revision: Union[str, Sequence[str], None] = "626926e59353"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add per-user LLM settings columns."""
    op.add_column("users", sa.Column("llm_provider", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("llm_api_key", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove per-user LLM settings columns."""
    op.drop_column("users", "llm_api_key")
    op.drop_column("users", "llm_provider")

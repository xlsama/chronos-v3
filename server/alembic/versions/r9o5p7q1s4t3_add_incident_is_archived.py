"""add incident is_archived

Revision ID: r9o5p7q1s4t3
Revises: q8n4o6p9r3s2
Create Date: 2026-03-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "r9o5p7q1s4t3"
down_revision: Union[str, None] = "q8n4o6p9r3s2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column("is_archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("incidents", "is_archived")

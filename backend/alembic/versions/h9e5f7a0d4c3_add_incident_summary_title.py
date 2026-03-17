"""add_incident_summary_title

Revision ID: h9e5f7a0d4c3
Revises: g8d4e6f9c3b2
Create Date: 2026-03-17 23:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "h9e5f7a0d4c3"
down_revision: Union[str, None] = "g8d4e6f9c3b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("summary_title", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("incidents", "summary_title")

"""remove_incident_summary_md

Revision ID: q8n4o6p9r3s2
Revises: p7m3n5o8q2r1
Create Date: 2026-03-19 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q8n4o6p9r3s2"
down_revision: Union[str, None] = "p7m3n5o8q2r1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("incidents", "summary_md")


def downgrade() -> None:
    op.add_column("incidents", sa.Column("summary_md", sa.Text(), nullable=True))

"""make connection project_id nullable

Revision ID: a44ec3a5b020
Revises: 0001_initial_topology_schema
Create Date: 2026-03-16 14:58:34.348668
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a44ec3a5b020'
down_revision: Union[str, None] = '0001_initial_topology_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('connections', 'project_id',
               existing_type=sa.UUID(),
               nullable=True)


def downgrade() -> None:
    op.alter_column('connections', 'project_id',
               existing_type=sa.UUID(),
               nullable=False)

"""add plan_md to incidents

Revision ID: 630239cc59e8
Revises: 341072b1e81a
Create Date: 2026-03-26 13:31:33.765171
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '630239cc59e8'
down_revision: Union[str, None] = '341072b1e81a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('incidents', sa.Column('plan_md', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('incidents', 'plan_md')

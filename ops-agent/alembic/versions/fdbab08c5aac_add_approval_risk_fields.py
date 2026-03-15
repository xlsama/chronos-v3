"""add approval risk fields

Revision ID: fdbab08c5aac
Revises: 5753c5ea1af7
Create Date: 2026-03-16 01:10:20.096088
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'fdbab08c5aac'
down_revision: Union[str, None] = '5753c5ea1af7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('approval_requests', sa.Column('risk_level', sa.String(length=20), nullable=True))
    op.add_column('approval_requests', sa.Column('risk_detail', sa.Text(), nullable=True))
    op.add_column('approval_requests', sa.Column('explanation', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('approval_requests', 'explanation')
    op.drop_column('approval_requests', 'risk_detail')
    op.drop_column('approval_requests', 'risk_level')

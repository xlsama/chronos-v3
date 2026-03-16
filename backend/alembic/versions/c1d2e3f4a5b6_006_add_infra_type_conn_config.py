"""006_add_infra_type_conn_config

Revision ID: c1d2e3f4a5b6
Revises: 319e15e52adb
Create Date: 2026-03-16 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = '319e15e52adb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('infrastructures', sa.Column('type', sa.String(length=50), nullable=False, server_default='ssh'))
    op.add_column('infrastructures', sa.Column('conn_config', sa.Text(), nullable=True))
    # Backfill existing rows
    op.execute("UPDATE infrastructures SET type = 'ssh' WHERE type IS NULL OR type = 'ssh'")


def downgrade() -> None:
    op.drop_column('infrastructures', 'conn_config')
    op.drop_column('infrastructures', 'type')

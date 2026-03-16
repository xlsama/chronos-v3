"""003 incident_history table + incidents.saved_to_memory

Revision ID: a1b2c3d4e5f6
Revises: fdbab08c5aac
Create Date: 2026-03-16 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'fdbab08c5aac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'incident_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('incident_id', sa.UUID(), nullable=True),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('summary_md', sa.Text(), nullable=False),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('embedding', Vector(1024), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_incident_history_project_id', 'incident_history', ['project_id'])
    op.add_column('incidents', sa.Column('saved_to_memory', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('incidents', 'saved_to_memory')
    op.drop_index('ix_incident_history_project_id', table_name='incident_history')
    op.drop_table('incident_history')

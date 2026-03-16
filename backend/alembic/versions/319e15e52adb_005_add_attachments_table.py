"""005_add_attachments_table

Revision ID: 319e15e52adb
Revises: b2c3d4e5f6a7
Create Date: 2026-03-16 02:00:42.565678
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '319e15e52adb'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('attachments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('incident_id', sa.UUID(), nullable=True),
    sa.Column('filename', sa.String(length=500), nullable=False),
    sa.Column('stored_filename', sa.String(length=500), nullable=False),
    sa.Column('content_type', sa.String(length=255), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_attachments_incident_id'), 'attachments', ['incident_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_attachments_incident_id'), table_name='attachments')
    op.drop_table('attachments')

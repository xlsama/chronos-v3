"""007_services_tables

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-03-16 12:01:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('services',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('infrastructure_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('service_type', sa.String(length=50), nullable=False),
        sa.Column('port', sa.Integer(), nullable=True),
        sa.Column('namespace', sa.String(length=255), nullable=True),
        sa.Column('config_json', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='unknown'),
        sa.Column('discovery_method', sa.String(length=20), nullable=False, server_default='manual'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['infrastructure_id'], ['infrastructures.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_services_infrastructure_id'), 'services', ['infrastructure_id'], unique=False)

    op.create_table('service_dependencies',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('service_id', sa.UUID(), nullable=False),
        sa.Column('depends_on_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['depends_on_id'], ['services.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_service_dependencies_service_id'), 'service_dependencies', ['service_id'], unique=False)
    op.create_index(op.f('ix_service_dependencies_depends_on_id'), 'service_dependencies', ['depends_on_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_service_dependencies_depends_on_id'), table_name='service_dependencies')
    op.drop_index(op.f('ix_service_dependencies_service_id'), table_name='service_dependencies')
    op.drop_table('service_dependencies')
    op.drop_index(op.f('ix_services_infrastructure_id'), table_name='services')
    op.drop_table('services')

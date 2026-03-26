"""add_bastion_fields_remove_k8s

Revision ID: c4e8f2a91b03
Revises: 9af756bfed57
Create Date: 2026-03-17 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e8f2a91b03"
down_revision: Union[str, None] = "b3c7e1a2d456"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("connections", sa.Column("bastion_host", sa.String(255), nullable=True))
    op.add_column("connections", sa.Column("bastion_port", sa.Integer, nullable=True))
    op.add_column("connections", sa.Column("bastion_username", sa.String(100), nullable=True))
    op.add_column("connections", sa.Column("encrypted_bastion_password", sa.Text, nullable=True))
    op.add_column("connections", sa.Column("encrypted_bastion_private_key", sa.Text, nullable=True))
    op.drop_column("connections", "type")
    op.drop_column("connections", "conn_config")


def downgrade() -> None:
    op.add_column("connections", sa.Column("conn_config", sa.Text, nullable=True))
    op.add_column(
        "connections", sa.Column("type", sa.String(50), server_default="ssh", nullable=False)
    )
    op.drop_column("connections", "encrypted_bastion_private_key")
    op.drop_column("connections", "encrypted_bastion_password")
    op.drop_column("connections", "bastion_username")
    op.drop_column("connections", "bastion_port")
    op.drop_column("connections", "bastion_host")

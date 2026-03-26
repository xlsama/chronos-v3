"""add_content_versions

Revision ID: p7m3n5o8q2r1
Revises: o6l2m4n7k1j0
Create Date: 2026-03-19 10:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p7m3n5o8q2r1"
down_revision: Union[str, None] = "o6l2m4n7k1j0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_versions",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("change_source", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_content_versions_entity",
        "content_versions",
        ["entity_type", "entity_id", "version_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_versions_entity", table_name="content_versions")
    op.drop_table("content_versions")

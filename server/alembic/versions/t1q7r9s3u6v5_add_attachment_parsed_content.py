"""add attachment parsed_content

Revision ID: t1q7r9s3u6v5
Revises: s0p6q8r2t5u4
Create Date: 2026-03-23
"""

import sqlalchemy as sa
from alembic import op

revision = "t1q7r9s3u6v5"
down_revision = "s0p6q8r2t5u4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("attachments", sa.Column("parsed_content", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("attachments", "parsed_content")

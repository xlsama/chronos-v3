"""add updated_at to project_documents

Revision ID: 341072b1e81a
Revises: c78eb593d15e
Create Date: 2026-03-24 15:16:11.337403
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "341072b1e81a"
down_revision: Union[str, None] = "c78eb593d15e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_documents",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("project_documents", "updated_at")

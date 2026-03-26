"""drop_incident_title

Revision ID: i0f6g8h1e5d4
Revises: h9e5f7a0d4c3
Create Date: 2026-03-17 23:45:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "i0f6g8h1e5d4"
down_revision: Union[str, None] = "h9e5f7a0d4c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("incidents", "title")


def downgrade() -> None:
    op.add_column(
        "incidents",
        sa.Column("title", sa.String(500), nullable=False, server_default=""),
    )

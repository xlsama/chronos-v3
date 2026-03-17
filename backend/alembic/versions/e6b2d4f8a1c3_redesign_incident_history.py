"""redesign_incident_history

Revision ID: e6b2d4f8a1c3
Revises: d5a1b3c7e9f0
Create Date: 2026-03-17 20:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e6b2d4f8a1c3"
down_revision: Union[str, None] = "d5a1b3c7e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("incident_history_incident_id_fkey", "incident_history", type_="foreignkey")
    op.drop_column("incident_history", "incident_id")
    op.add_column(
        "incident_history",
        sa.Column("occurrence_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "incident_history",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("incident_history", "last_seen_at")
    op.drop_column("incident_history", "occurrence_count")
    op.add_column(
        "incident_history",
        sa.Column("incident_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "incident_history_incident_id_fkey",
        "incident_history",
        "incidents",
        ["incident_id"],
        ["id"],
    )

"""remove_incident_project_id

Revision ID: m4j0k2l5i9h8
Revises: l3i9j1k4h8g7
Create Date: 2026-03-18 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "m4j0k2l5i9h8"
down_revision: Union[str, None] = "l3i9j1k4h8g7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("incidents_project_id_fkey", "incidents", type_="foreignkey")
    op.drop_index("ix_incidents_project_id", "incidents")
    op.drop_column("incidents", "project_id")

    op.drop_constraint("incident_history_project_id_fkey", "incident_history", type_="foreignkey")
    op.drop_index("ix_incident_history_project_id", "incident_history")
    op.drop_column("incident_history", "project_id")


def downgrade() -> None:
    op.add_column("incidents", sa.Column("project_id", UUID(as_uuid=True), nullable=True))
    op.create_index("ix_incidents_project_id", "incidents", ["project_id"])
    op.create_foreign_key(
        "incidents_project_id_fkey", "incidents", "projects", ["project_id"], ["id"]
    )

    op.add_column("incident_history", sa.Column("project_id", UUID(as_uuid=True), nullable=True))
    op.create_index("ix_incident_history_project_id", "incident_history", ["project_id"])
    op.create_foreign_key(
        "incident_history_project_id_fkey", "incident_history", "projects", ["project_id"], ["id"]
    )

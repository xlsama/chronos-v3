"""010_add_incident_fk_indexes

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-03-16 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_incidents_project_id", "incidents", ["project_id"])
    op.create_index("ix_incidents_infrastructure_id", "incidents", ["infrastructure_id"])


def downgrade() -> None:
    op.drop_index("ix_incidents_infrastructure_id", table_name="incidents")
    op.drop_index("ix_incidents_project_id", table_name="incidents")

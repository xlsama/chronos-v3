"""add_messages_incident_created_index

Revision ID: 9af756bfed57
Revises: 31fa70554859
Create Date: 2026-03-17 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9af756bfed57"
down_revision: Union[str, None] = "31fa70554859"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_messages_incident_created", "messages", ["incident_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_messages_incident_created", table_name="messages")

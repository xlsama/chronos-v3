"""project_servers_table_and_metadata_jsonb

Revision ID: k2h8i0j3g7f6
Revises: j1g7h9i2f6e5
Create Date: 2026-03-17 23:55:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "k2h8i0j3g7f6"
down_revision: Union[str, None] = "j1g7h9i2f6e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create project_servers junction table
    op.create_table(
        "project_servers",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "server_id",
            UUID(as_uuid=True),
            sa.ForeignKey("servers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "server_id", name="uq_project_server"),
    )

    # 2. Migrate data from projects.linked_server_ids JSONB to project_servers
    op.execute("""
        INSERT INTO project_servers (id, project_id, server_id)
        SELECT gen_random_uuid(), p.id, s.id::uuid
        FROM projects p,
             jsonb_array_elements_text(p.linked_server_ids) AS s(id)
        WHERE p.linked_server_ids IS NOT NULL
          AND jsonb_array_length(p.linked_server_ids) > 0
          AND EXISTS (SELECT 1 FROM servers WHERE servers.id = s.id::uuid)
    """)

    # 3. Drop linked_server_ids column
    op.drop_column("projects", "linked_server_ids")

    # 4. Alter messages.metadata_json from Text to JSONB
    op.execute(
        "ALTER TABLE messages ALTER COLUMN metadata_json TYPE jsonb USING metadata_json::jsonb"
    )


def downgrade() -> None:
    # Restore metadata_json to Text
    op.execute(
        "ALTER TABLE messages ALTER COLUMN metadata_json TYPE text USING metadata_json::text"
    )

    # Restore linked_server_ids column
    op.add_column("projects", sa.Column("linked_server_ids", JSONB, server_default=sa.text("'[]'")))

    # Migrate data back
    op.execute("""
        UPDATE projects SET linked_server_ids = (
            SELECT COALESCE(jsonb_agg(ps.server_id::text), '[]'::jsonb)
            FROM project_servers ps
            WHERE ps.project_id = projects.id
        )
    """)

    # Drop project_servers table
    op.drop_table("project_servers")

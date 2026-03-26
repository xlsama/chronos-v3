"""rename_connections_to_servers

Revision ID: f7c3d5e8b2a1
Revises: e6b2d4f8a1c3
Create Date: 2026-03-17 22:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f7c3d5e8b2a1"
down_revision: Union[str, None] = "e6b2d4f8a1c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop columns from connections
    op.drop_column("connections", "capabilities")
    op.drop_column("connections", "scope_metadata")

    # 2. Rename table connections → servers
    op.rename_table("connections", "servers")

    # 3. Update unique constraint name
    op.drop_constraint("uq_connections_name", "servers", type_="unique")
    op.create_unique_constraint("uq_servers_name", "servers", ["name"])

    # 4. Drop connection_id from incidents
    op.drop_constraint("incidents_connection_id_fkey", "incidents", type_="foreignkey")
    op.drop_index("ix_incidents_connection_id", table_name="incidents")
    op.drop_column("incidents", "connection_id")

    # 5. Rename column in projects
    op.alter_column("projects", "linked_connection_ids", new_column_name="linked_server_ids")


def downgrade() -> None:
    # 5. Rename column back
    op.alter_column("projects", "linked_server_ids", new_column_name="linked_connection_ids")

    # 4. Re-add connection_id to incidents
    op.add_column(
        "incidents",
        sa.Column("connection_id", sa.UUID(), nullable=True),
    )
    op.create_index("ix_incidents_connection_id", "incidents", ["connection_id"])
    op.create_foreign_key(
        "incidents_connection_id_fkey",
        "incidents",
        "servers",
        ["connection_id"],
        ["id"],
    )

    # 3. Update constraint name back
    op.drop_constraint("uq_servers_name", "servers", type_="unique")
    op.create_unique_constraint("uq_connections_name", "servers", ["name"])

    # 2. Rename table back
    op.rename_table("servers", "connections")

    # 1. Re-add columns
    op.add_column(
        "connections",
        sa.Column(
            "capabilities",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    op.add_column(
        "connections",
        sa.Column(
            "scope_metadata",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )

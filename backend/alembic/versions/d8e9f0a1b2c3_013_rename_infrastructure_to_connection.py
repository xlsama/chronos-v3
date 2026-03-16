"""013 rename infrastructure to connection

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-03-16
"""

from alembic import op

revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rename table
    op.rename_table("infrastructures", "connections")

    # 2. incidents.infrastructure_id → connection_id
    op.drop_constraint(
        "incidents_infrastructure_id_fkey", "incidents", type_="foreignkey"
    )
    op.drop_index("ix_incidents_infrastructure_id", table_name="incidents")
    op.alter_column("incidents", "infrastructure_id", new_column_name="connection_id")
    op.create_index("ix_incidents_connection_id", "incidents", ["connection_id"])
    op.create_foreign_key(
        "incidents_connection_id_fkey",
        "incidents",
        "connections",
        ["connection_id"],
        ["id"],
    )

    # 3. services.infrastructure_id → connection_id
    op.drop_constraint(
        "services_infrastructure_id_fkey", "services", type_="foreignkey"
    )
    op.drop_index("ix_services_infrastructure_id", table_name="services")
    op.alter_column("services", "infrastructure_id", new_column_name="connection_id")
    op.create_index("ix_services_connection_id", "services", ["connection_id"])
    op.create_foreign_key(
        "services_connection_id_fkey",
        "services",
        "connections",
        ["connection_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # 3. services.connection_id → infrastructure_id
    op.drop_constraint(
        "services_connection_id_fkey", "services", type_="foreignkey"
    )
    op.drop_index("ix_services_connection_id", table_name="services")
    op.alter_column("services", "connection_id", new_column_name="infrastructure_id")
    op.create_index("ix_services_infrastructure_id", "services", ["infrastructure_id"])
    op.create_foreign_key(
        "services_infrastructure_id_fkey",
        "services",
        "infrastructures",
        ["infrastructure_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 2. incidents.connection_id → infrastructure_id
    op.drop_constraint(
        "incidents_connection_id_fkey", "incidents", type_="foreignkey"
    )
    op.drop_index("ix_incidents_connection_id", table_name="incidents")
    op.alter_column("incidents", "connection_id", new_column_name="infrastructure_id")
    op.create_index("ix_incidents_infrastructure_id", "incidents", ["infrastructure_id"])
    op.create_foreign_key(
        "incidents_infrastructure_id_fkey",
        "incidents",
        "infrastructures",
        ["infrastructure_id"],
        ["id"],
    )

    # 1. Rename table back
    op.rename_table("connections", "infrastructures")

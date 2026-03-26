"""drop_service_topology_tables

Revision ID: d5a1b3c7e9f0
Revises: c4e8f2a91b03
Create Date: 2026-03-17 18:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d5a1b3c7e9f0"
down_revision: Union[str, None] = "c4e8f2a91b03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("service_connection_bindings")
    op.drop_table("service_dependencies")
    op.drop_table("services")


def downgrade() -> None:
    op.create_table(
        "services",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("service_type", sa.String(50), server_default="custom", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("business_context", sa.Text(), nullable=True),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("keywords", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("status", sa.String(20), server_default="unknown", nullable=False),
        sa.Column("source", sa.String(20), server_default="manual", nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "slug", name="uq_services_project_slug"),
    )
    op.create_index("ix_services_project_id", "services", ["project_id"])

    op.create_table(
        "service_dependencies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("from_service_id", sa.UUID(), nullable=False),
        sa.Column("to_service_id", sa.UUID(), nullable=False),
        sa.Column("dependency_type", sa.String(50), server_default="api_call", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Integer(), server_default="100", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_service_id"], ["services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_service_id"], ["services.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_id",
            "from_service_id",
            "to_service_id",
            "dependency_type",
            name="uq_service_dependencies_edge",
        ),
        sa.CheckConstraint(
            "from_service_id <> to_service_id", name="ck_service_dependencies_no_self_ref"
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 100", name="ck_service_dependencies_confidence"
        ),
    )
    op.create_index("ix_service_dependencies_project_id", "service_dependencies", ["project_id"])
    op.create_index(
        "ix_service_dependencies_from_service_id", "service_dependencies", ["from_service_id"]
    )
    op.create_index(
        "ix_service_dependencies_to_service_id", "service_dependencies", ["to_service_id"]
    )

    op.create_table(
        "service_connection_bindings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("usage_type", sa.String(50), server_default="runtime_inspect", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_id",
            "service_id",
            "connection_id",
            "usage_type",
            name="uq_service_connection_bindings_scope",
        ),
        sa.CheckConstraint("priority >= 0", name="ck_service_connection_bindings_priority"),
    )
    op.create_index(
        "ix_service_connection_bindings_project_id", "service_connection_bindings", ["project_id"]
    )
    op.create_index(
        "ix_service_connection_bindings_service_id", "service_connection_bindings", ["service_id"]
    )
    op.create_index(
        "ix_service_connection_bindings_connection_id",
        "service_connection_bindings",
        ["connection_id"],
    )

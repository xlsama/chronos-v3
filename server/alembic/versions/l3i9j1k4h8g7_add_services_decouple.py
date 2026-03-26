"""add_services_table_decouple_project_servers

Revision ID: l3i9j1k4h8g7
Revises: k2h8i0j3g7f6
Create Date: 2026-03-18 10:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "l3i9j1k4h8g7"
down_revision: Union[str, None] = "k2h8i0j3g7f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create services table
    op.create_table(
        "services",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("service_type", sa.String(50), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer, nullable=False),
        sa.Column("config", JSONB, server_default=sa.text("'{}'"), nullable=False),
        sa.Column("encrypted_password", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), server_default="unknown", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_services_name"),
    )

    # 2. Drop project_servers table
    op.drop_table("project_servers")

    # 3. SERVICE.md → Agents.md
    op.execute("""
        DELETE FROM document_chunks WHERE document_id IN (
            SELECT id FROM project_documents WHERE doc_type = 'service_map'
        )
    """)
    op.execute("""
        UPDATE project_documents
        SET filename = 'Agents.md', doc_type = 'agents_config', content = ''
        WHERE doc_type = 'service_map'
    """)


def downgrade() -> None:
    # Restore SERVICE.md
    op.execute("""
        UPDATE project_documents
        SET filename = 'SERVICE.md', doc_type = 'service_map'
        WHERE doc_type = 'agents_config'
    """)

    # Recreate project_servers table
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

    # Drop services table
    op.drop_table("services")

"""012 simplify services

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

revision = "c7d8e9f0a1b2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("service_dependencies")
    op.drop_column("services", "service_type")
    op.drop_column("services", "config_json")


def downgrade() -> None:
    op.add_column("services", sa.Column("config_json", sa.Text(), nullable=True))
    op.add_column("services", sa.Column("service_type", sa.String(50), nullable=False, server_default="custom"))
    op.create_table(
        "service_dependencies",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("service_id", sa.UUID(), sa.ForeignKey("services.id", ondelete="CASCADE"), nullable=False),
        sa.Column("depends_on_id", sa.UUID(), sa.ForeignKey("services.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_service_dependencies_service_id", "service_dependencies", ["service_id"])
    op.create_index("ix_service_dependencies_depends_on_id", "service_dependencies", ["depends_on_id"])

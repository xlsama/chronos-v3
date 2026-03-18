"""add_notification_settings

Revision ID: g8d4e6f9c3b2
Revises: f7c3d5e8b2a1
Create Date: 2026-03-17 23:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "g8d4e6f9c3b2"
down_revision: Union[str, None] = "f7c3d5e8b2a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_settings",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("encrypted_webhook_url", sa.Text(), nullable=False),
        sa.Column("encrypted_sign_key", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("platform", name="uq_notification_settings_platform"),
    )


def downgrade() -> None:
    op.drop_table("notification_settings")

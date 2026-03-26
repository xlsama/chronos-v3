"""add sudo password fields to servers

Revision ID: 5f4a6bcb7b98
Revises: t1q7r9s3u6v5
Create Date: 2026-03-24 14:10:34.306354
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "5f4a6bcb7b98"
down_revision: Union[str, None] = "t1q7r9s3u6v5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("servers", sa.Column("encrypted_sudo_password", sa.Text(), nullable=True))
    op.add_column(
        "servers",
        sa.Column(
            "use_ssh_password_for_sudo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("servers", "use_ssh_password_for_sudo")
    op.drop_column("servers", "encrypted_sudo_password")

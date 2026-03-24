"""use_ssh_password_for_sudo default true

Revision ID: c78eb593d15e
Revises: 5f4a6bcb7b98
Create Date: 2026-03-24 15:03:58.703646
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c78eb593d15e"
down_revision: Union[str, None] = "5f4a6bcb7b98"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update existing servers to use SSH password for sudo by default
    op.execute("UPDATE servers SET use_ssh_password_for_sudo = true")
    # Change column default
    op.alter_column(
        "servers",
        "use_ssh_password_for_sudo",
        server_default="true",
    )


def downgrade() -> None:
    op.alter_column(
        "servers",
        "use_ssh_password_for_sudo",
        server_default="false",
    )
    op.execute("UPDATE servers SET use_ssh_password_for_sudo = false")

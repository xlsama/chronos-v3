"""rename_error_to_index_failed

Revision ID: o6l2m4n7k1j0
Revises: n5k1l3m6j0i9
Create Date: 2026-03-18 20:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "o6l2m4n7k1j0"
down_revision: Union[str, None] = "n5k1l3m6j0i9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE project_documents SET status = 'index_failed' WHERE status = 'error'")


def downgrade() -> None:
    op.execute("UPDATE project_documents SET status = 'error' WHERE status = 'index_failed'")

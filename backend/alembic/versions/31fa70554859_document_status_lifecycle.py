"""document_status_lifecycle

Revision ID: 31fa70554859
Revises: a44ec3a5b020
Create Date: 2026-03-16 17:07:31.313313
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '31fa70554859'
down_revision: Union[str, None] = 'a44ec3a5b020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('project_documents', sa.Column('error_message', sa.Text(), nullable=True))
    op.execute("UPDATE project_documents SET status = 'indexed' WHERE status = 'ready'")
    op.execute("UPDATE project_documents SET status = 'error', error_message = 'Interrupted during previous indexing' WHERE status = 'processing'")


def downgrade() -> None:
    op.execute("UPDATE project_documents SET status = 'ready' WHERE status = 'indexed'")
    op.execute("UPDATE project_documents SET status = 'processing' WHERE status IN ('pending', 'indexing', 'error')")
    op.drop_column('project_documents', 'error_message')

"""rename_agents_md

Revision ID: n5k1l3m6j0i9
Revises: m4j0k2l5i9h8
Create Date: 2026-03-18 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n5k1l3m6j0i9"
down_revision: Union[str, None] = "m4j0k2l5i9h8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE project_documents SET filename = 'AGENTS.md' WHERE doc_type = 'agents_config'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE project_documents SET filename = 'Agents.md' WHERE doc_type = 'agents_config'"
    )

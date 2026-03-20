"""rename tool_call to tool_use

Revision ID: s0p6q8r2t5u4
Revises: r9o5p7q1s4t3
Create Date: 2026-03-21
"""

from alembic import op

revision = "s0p6q8r2t5u4"
down_revision = "r9o5p7q1s4t3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE messages SET event_type = 'tool_use' WHERE event_type = 'tool_call'")


def downgrade() -> None:
    op.execute("UPDATE messages SET event_type = 'tool_call' WHERE event_type = 'tool_use'")

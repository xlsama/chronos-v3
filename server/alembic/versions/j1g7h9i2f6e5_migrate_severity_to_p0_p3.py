"""migrate_severity_to_p0_p3

Revision ID: j1g7h9i2f6e5
Revises: i0f6g8h1e5d4
Create Date: 2026-03-17 23:50:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "j1g7h9i2f6e5"
down_revision: Union[str, None] = "i0f6g8h1e5d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Map old severity values to P0-P3
    op.execute("""
        UPDATE incidents SET severity = CASE
            WHEN lower(severity) = 'critical' THEN 'P0'
            WHEN lower(severity) = 'high'     THEN 'P1'
            WHEN lower(severity) = 'medium'   THEN 'P2'
            WHEN lower(severity) = 'low'      THEN 'P3'
            ELSE 'P3'
        END
        WHERE severity NOT IN ('P0', 'P1', 'P2', 'P3')
    """)
    # Update column default
    op.alter_column("incidents", "severity", server_default="P3")


def downgrade() -> None:
    # Map P0-P3 back to old values
    op.execute("""
        UPDATE incidents SET severity = CASE
            WHEN severity = 'P0' THEN 'critical'
            WHEN severity = 'P1' THEN 'high'
            WHEN severity = 'P2' THEN 'medium'
            WHEN severity = 'P3' THEN 'low'
            ELSE 'medium'
        END
        WHERE severity IN ('P0', 'P1', 'P2', 'P3')
    """)
    op.alter_column("incidents", "severity", server_default="medium")

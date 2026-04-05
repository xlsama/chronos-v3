"""rename agents md to memory md

Revision ID: 6b7c56b2f8d2
Revises: abb90aea4e95
Create Date: 2026-04-02 13:30:00.000000
"""

import os
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


# revision identifiers, used by Alembic.
revision: str = "6b7c56b2f8d2"
down_revision: Union[str, None] = "abb90aea4e95"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _data_dir() -> Path:
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    if data_dir.is_absolute():
        return data_dir
    return Path(__file__).resolve().parents[2] / data_dir


def _rename_memory_files(bind: Connection, src_name: str, dst_name: str) -> None:
    project_rows = bind.execute(sa.text("SELECT slug FROM projects")).fetchall()
    knowledge_root = _data_dir() / "knowledge"
    for row in project_rows:
        slug = row[0]
        if not slug:
            continue
        project_dir = knowledge_root / slug
        src_path = project_dir / src_name
        dst_path = project_dir / dst_name
        if src_path.exists() and not dst_path.exists():
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            src_path.rename(dst_path)


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            UPDATE project_documents
            SET doc_type = 'memory_config'
            WHERE doc_type = 'agents_config'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE project_documents
            SET filename = 'MEMORY.md'
            WHERE filename = 'AGENTS.md'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE content_versions
            SET entity_type = 'memory_md'
            WHERE entity_type = 'agents_md'
            """
        )
    )

    _rename_memory_files(bind, "AGENTS.md", "MEMORY.md")


def downgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            UPDATE project_documents
            SET doc_type = 'agents_config'
            WHERE doc_type = 'memory_config'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE project_documents
            SET filename = 'AGENTS.md'
            WHERE filename = 'MEMORY.md'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE content_versions
            SET entity_type = 'agents_md'
            WHERE entity_type = 'memory_md'
            """
        )
    )

    _rename_memory_files(bind, "MEMORY.md", "AGENTS.md")

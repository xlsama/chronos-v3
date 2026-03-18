"""migrate connection project_id to project linked_connection_ids

Revision ID: b3c7e1a2d456
Revises: 9af756bfed57
Create Date: 2026-03-17 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'b3c7e1a2d456'
down_revision: Union[str, None] = '9af756bfed57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add linked_connection_ids to projects
    op.add_column('projects', sa.Column('linked_connection_ids', JSONB, server_default=sa.text("'[]'"), nullable=False))

    # 2. Data migration: move connection.project_id → project.linked_connection_ids
    conn = op.get_bind()
    # Get all connections that have a project_id
    rows = conn.execute(sa.text(
        "SELECT id, project_id FROM connections WHERE project_id IS NOT NULL"
    )).fetchall()

    # Group connection IDs by project_id
    project_conns: dict[str, list[str]] = {}
    for row in rows:
        pid = str(row[1])
        cid = str(row[0])
        project_conns.setdefault(pid, []).append(cid)

    # Update each project's linked_connection_ids
    for pid, cids in project_conns.items():
        import json
        conn.execute(
            sa.text("UPDATE projects SET linked_connection_ids = :ids WHERE id = :pid"),
            {"ids": json.dumps(cids), "pid": pid},
        )

    # 3. Handle duplicate connection names before adding unique constraint
    # Find duplicates: same name across different projects
    dupes = conn.execute(sa.text(
        "SELECT name, COUNT(*) FROM connections GROUP BY name HAVING COUNT(*) > 1"
    )).fetchall()

    for dupe_name, _ in dupes:
        # Get all connections with this name, ordered by created_at (keep first as-is)
        dupe_conns = conn.execute(sa.text(
            "SELECT c.id, p.slug FROM connections c "
            "LEFT JOIN projects p ON c.project_id = p.id "
            "WHERE c.name = :name ORDER BY c.created_at ASC"
        ), {"name": dupe_name}).fetchall()

        # Skip the first one, rename the rest
        for cid, slug in dupe_conns[1:]:
            suffix = f"-{slug}" if slug else f"-{str(cid)[:8]}"
            new_name = f"{dupe_name}{suffix}"
            conn.execute(
                sa.text("UPDATE connections SET name = :new_name WHERE id = :cid"),
                {"new_name": new_name, "cid": str(cid)},
            )

    # 4. Drop old constraint, FK, column
    op.drop_constraint('uq_connections_project_name', 'connections', type_='unique')
    op.drop_constraint('connections_project_id_fkey', 'connections', type_='foreignkey')
    op.drop_index('ix_connections_project_id', table_name='connections')
    op.drop_column('connections', 'project_id')

    # 5. Add new unique constraint on name only
    op.create_unique_constraint('uq_connections_name', 'connections', ['name'])


def downgrade() -> None:
    # Remove new unique constraint
    op.drop_constraint('uq_connections_name', 'connections', type_='unique')

    # Re-add project_id column + FK
    op.add_column('connections', sa.Column('project_id', sa.UUID(), nullable=True))
    op.create_index('ix_connections_project_id', 'connections', ['project_id'])
    op.create_foreign_key(
        'connections_project_id_fkey', 'connections', 'projects',
        ['project_id'], ['id'], ondelete='CASCADE'
    )

    # Restore data from linked_connection_ids
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, linked_connection_ids FROM projects WHERE linked_connection_ids != '[]'"
    )).fetchall()

    for pid, cids in rows:
        import json
        conn_ids = json.loads(cids) if isinstance(cids, str) else cids
        for cid in conn_ids:
            conn.execute(
                sa.text("UPDATE connections SET project_id = :pid WHERE id = :cid"),
                {"pid": str(pid), "cid": cid},
            )

    # Restore old unique constraint
    op.create_unique_constraint('uq_connections_project_name', 'connections', ['project_id', 'name'])

    # Drop linked_connection_ids
    op.drop_column('projects', 'linked_connection_ids')

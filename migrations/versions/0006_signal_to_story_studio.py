"""Signal intelligence and multi-agent writing studio.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app.domain import studio  # noqa: F401

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_STUDIO_TABLES = (
    "monitor_targets",
    "metric_snapshots",
    "score_records",
    "content_analyses",
    "pattern_cards",
    "style_profiles",
    "writing_projects",
    "writing_artifacts",
    "agent_runs",
    "writing_feedback",
)

# SQLite permits ADD COLUMN with a constant default, but rejects expressions
# such as CURRENT_TIMESTAMP on an existing table. The application always
# supplies available_at for new jobs, so this value is only a safe migration
# placeholder for pre-existing rows and is immediately replaced below.
_SQLITE_AVAILABLE_AT_PLACEHOLDER = "1970-01-01 00:00:00"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _upgrade_jobs_table() -> None:
    bind = op.get_bind()
    inspector = _inspector()
    if "jobs" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("jobs")}
    constant_additions = {
        "max_attempts": sa.Column(
            "max_attempts", sa.Integer(), nullable=False, server_default="3"
        ),
        "priority": sa.Column(
            "priority", sa.Integer(), nullable=False, server_default="100"
        ),
        "dedupe_key": sa.Column(
            "dedupe_key", sa.String(length=255), nullable=False, server_default=""
        ),
        "locked_by": sa.Column(
            "locked_by", sa.String(length=120), nullable=False, server_default=""
        ),
    }
    for name, column in constant_additions.items():
        if name not in columns:
            op.add_column("jobs", column)

    # This branch also recovers databases where the original 0006 migration
    # already added max_attempts/priority/dedupe_key and then failed at
    # available_at. Alembic still reports revision 0005 in that state.
    if "available_at" not in columns:
        server_default: str | sa.ClauseElement
        if bind.dialect.name == "sqlite":
            server_default = _SQLITE_AVAILABLE_AT_PLACEHOLDER
        else:
            server_default = sa.func.current_timestamp()
        op.add_column(
            "jobs",
            sa.Column(
                "available_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=server_default,
            ),
        )

    # Preserve the original scheduling semantics for old jobs: they become
    # available at their creation time, not at an arbitrary migration time.
    # The placeholder predicate is harmless on non-SQLite databases.
    op.execute(
        sa.text(
            "UPDATE jobs "
            "SET available_at = COALESCE(created_at, CURRENT_TIMESTAMP) "
            "WHERE available_at IS NULL "
            "OR available_at = '1970-01-01 00:00:00'"
        )
    )

    indexes = {index["name"] for index in _inspector().get_indexes("jobs")}
    for name, index_columns in {
        "ix_jobs_priority": ["priority"],
        "ix_jobs_dedupe_key": ["dedupe_key"],
        "ix_jobs_available_at": ["available_at"],
    }.items():
        if name not in indexes:
            op.create_index(name, "jobs", index_columns, unique=False)


def upgrade() -> None:
    _upgrade_jobs_table()

    bind = op.get_bind()
    for table_name in _STUDIO_TABLES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(_STUDIO_TABLES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=True)

    inspector = _inspector()
    if "jobs" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("jobs")}
    for name in ("ix_jobs_available_at", "ix_jobs_dedupe_key", "ix_jobs_priority"):
        if name in indexes:
            op.drop_index(name, table_name="jobs")
    columns = {column["name"] for column in _inspector().get_columns("jobs")}
    removable = [
        name
        for name in ("locked_by", "available_at", "dedupe_key", "priority", "max_attempts")
        if name in columns
    ]
    if removable:
        with op.batch_alter_table("jobs") as batch:
            for name in removable:
                batch.drop_column(name)

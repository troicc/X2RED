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


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    if "jobs" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("jobs")}
        additions = {
            "max_attempts": sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
            "priority": sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            "dedupe_key": sa.Column(
                "dedupe_key", sa.String(length=255), nullable=False, server_default=""
            ),
            "available_at": sa.Column(
                "available_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            "locked_by": sa.Column(
                "locked_by", sa.String(length=120), nullable=False, server_default=""
            ),
        }
        for name, column in additions.items():
            if name not in columns:
                op.add_column("jobs", column)

        indexes = {index["name"] for index in _inspector().get_indexes("jobs")}
        for name, index_columns in {
            "ix_jobs_priority": ["priority"],
            "ix_jobs_dedupe_key": ["dedupe_key"],
            "ix_jobs_available_at": ["available_at"],
        }.items():
            if name not in indexes:
                op.create_index(name, "jobs", index_columns, unique=False)

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

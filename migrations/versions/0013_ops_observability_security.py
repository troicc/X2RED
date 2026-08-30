"""Add OPS1 cost telemetry, job leases, and publish audit events.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _columns(table_name: str) -> set[str]:
    if table_name not in _inspector().get_table_names():
        return set()
    return {str(item["name"]) for item in _inspector().get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    if table_name not in _inspector().get_table_names():
        return set()
    return {
        str(item.get("name") or "")
        for item in _inspector().get_indexes(table_name)
    }


def _add_job_columns() -> None:
    columns = _columns("jobs")
    if not columns:
        return
    additions: dict[str, sa.Column] = {
        "lease_expires_at": sa.Column(
            "lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        "heartbeat_at": sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        "last_worker_id": sa.Column(
            "last_worker_id",
            sa.String(length=160),
            nullable=False,
            server_default="",
        ),
        "last_error_code": sa.Column(
            "last_error_code",
            sa.String(length=80),
            nullable=False,
            server_default="",
        ),
        "dead_lettered_at": sa.Column(
            "dead_lettered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("jobs", column)

    indexes = _indexes("jobs")
    for name, fields in (
        ("ix_jobs_lease_expires_at", ["lease_expires_at"]),
        ("ix_jobs_dead_lettered_at", ["dead_lettered_at"]),
    ):
        if name not in indexes:
            op.create_index(name, "jobs", fields, unique=False)

    bind = op.get_bind()
    active = bind.execute(
        sa.text(
            "SELECT id, dedupe_key FROM jobs "
            "WHERE dedupe_key <> '' AND state IN ('pending', 'running') "
            "ORDER BY created_at, id"
        )
    ).mappings()
    seen: set[str] = set()
    duplicate_ids: list[str] = []
    for row in active:
        key = str(row["dedupe_key"])
        if key in seen:
            duplicate_ids.append(str(row["id"]))
        else:
            seen.add(key)
    for job_id in duplicate_ids:
        bind.execute(
            sa.text(
                "UPDATE jobs SET state = 'canceled', locked_by = '', "
                "error = 'OPS1 migration canceled duplicate active dedupe key', "
                "last_error_code = 'duplicate_dedupe_key', "
                "finished_at = CURRENT_TIMESTAMP WHERE id = :job_id"
            ),
            {"job_id": job_id},
        )

    indexes = _indexes("jobs")
    if "uq_jobs_active_dedupe" not in indexes:
        predicate = sa.text("dedupe_key <> '' AND state IN ('pending', 'running')")
        dialect = bind.dialect.name
        if dialect == "sqlite":
            op.create_index(
                "uq_jobs_active_dedupe",
                "jobs",
                ["dedupe_key"],
                unique=True,
                sqlite_where=predicate,
            )
        elif dialect == "postgresql":
            op.create_index(
                "uq_jobs_active_dedupe",
                "jobs",
                ["dedupe_key"],
                unique=True,
                postgresql_where=predicate,
            )


def _add_writing_cost() -> None:
    columns = _columns("writing_projects")
    if columns and "spent_cost_usd" not in columns:
        op.add_column(
            "writing_projects",
            sa.Column(
                "spent_cost_usd",
                sa.Float(),
                nullable=False,
                server_default="0",
            ),
        )


def _create_publish_audit() -> None:
    if "publish_audit_events" not in _inspector().get_table_names():
        op.create_table(
            "publish_audit_events",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("task_id", sa.String(length=64), nullable=True),
            sa.Column("draft_id", sa.String(length=64), nullable=True),
            sa.Column("action", sa.String(length=60), nullable=False),
            sa.Column("outcome", sa.String(length=30), nullable=False),
            sa.Column("actor", sa.String(length=80), nullable=False, server_default="local-user"),
            sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["task_id"],
                ["publish_tasks.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["draft_id"],
                ["draft_revisions.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    indexes = _indexes("publish_audit_events")
    for name, fields in (
        ("ix_publish_audit_events_task_id", ["task_id"]),
        ("ix_publish_audit_events_draft_id", ["draft_id"]),
        ("ix_publish_audit_events_action", ["action"]),
        ("ix_publish_audit_events_outcome", ["outcome"]),
        ("ix_publish_audit_events_created_at", ["created_at"]),
    ):
        if name not in indexes:
            op.create_index(name, "publish_audit_events", fields, unique=False)


def upgrade() -> None:
    _add_job_columns()
    _add_writing_cost()
    _create_publish_audit()


def downgrade() -> None:
    if "publish_audit_events" in _inspector().get_table_names():
        op.drop_table("publish_audit_events")
    if "writing_projects" in _inspector().get_table_names() and "spent_cost_usd" in _columns(
        "writing_projects"
    ):
        with op.batch_alter_table("writing_projects") as batch:
            batch.drop_column("spent_cost_usd")
    if "jobs" not in _inspector().get_table_names():
        return
    for index_name in (
        "uq_jobs_active_dedupe",
        "ix_jobs_dead_lettered_at",
        "ix_jobs_lease_expires_at",
    ):
        if index_name in _indexes("jobs"):
            op.drop_index(index_name, table_name="jobs")
    removable = [
        name
        for name in (
            "dead_lettered_at",
            "last_error_code",
            "last_worker_id",
            "heartbeat_at",
            "lease_expires_at",
        )
        if name in _columns("jobs")
    ]
    if removable:
        with op.batch_alter_table("jobs") as batch:
            for name in removable:
                batch.drop_column(name)

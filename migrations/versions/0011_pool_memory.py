"""Add task-scoped pool-memory snapshots and append-only usage records.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table_name: str) -> set[str]:
    if table_name not in _table_names():
        return set()
    return {
        str(item.get("name") or "") for item in sa.inspect(op.get_bind()).get_indexes(table_name)
    }


def _create_index_if_missing(
    name: str,
    table_name: str,
    columns: list[str],
) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns, unique=False)


def upgrade() -> None:
    if "pool_memory_snapshots" not in _table_names():
        op.create_table(
            "pool_memory_snapshots",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("target_type", sa.String(length=60), nullable=False),
            sa.Column("target_id", sa.String(length=64), nullable=False),
            sa.Column("query_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("memory_ids_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("prompt_payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
            sa.Column("model_configured", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("model_name", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    for name, columns in (
        ("ix_pool_memory_snapshots_target_type", ["target_type"]),
        ("ix_pool_memory_snapshots_target_id", ["target_id"]),
        ("ix_pool_memory_snapshots_snapshot_hash", ["snapshot_hash"]),
        ("ix_pool_memory_snapshots_applied", ["applied"]),
    ):
        _create_index_if_missing(name, "pool_memory_snapshots", columns)

    if "pool_memory_usages" not in _table_names():
        op.create_table(
            "pool_memory_usages",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("memory_id", sa.String(length=64), nullable=False),
            sa.Column("snapshot_id", sa.String(length=64), nullable=False),
            sa.Column("target_type", sa.String(length=60), nullable=False),
            sa.Column("target_id", sa.String(length=64), nullable=False),
            sa.Column("agent_role", sa.String(length=60), nullable=False, server_default=""),
            sa.Column("stage", sa.String(length=60), nullable=False, server_default=""),
            sa.Column("selected_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["memory_id"],
                ["review_artifacts.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["snapshot_id"],
                ["pool_memory_snapshots.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "memory_id",
                "snapshot_id",
                "agent_role",
                "stage",
                name="uq_pool_memory_usage_role_stage",
            ),
        )
    for name, columns in (
        ("ix_pool_memory_usages_memory_id", ["memory_id"]),
        ("ix_pool_memory_usages_snapshot_id", ["snapshot_id"]),
        ("ix_pool_memory_usages_target_type", ["target_type"]),
        ("ix_pool_memory_usages_target_id", ["target_id"]),
        ("ix_pool_memory_usages_agent_role", ["agent_role"]),
        ("ix_pool_memory_usages_stage", ["stage"]),
    ):
        _create_index_if_missing(name, "pool_memory_usages", columns)


def _drop_index_if_present(name: str, table_name: str) -> None:
    if name in _index_names(table_name):
        op.drop_index(name, table_name=table_name)


def downgrade() -> None:
    if "pool_memory_usages" in _table_names():
        for name in (
            "ix_pool_memory_usages_stage",
            "ix_pool_memory_usages_agent_role",
            "ix_pool_memory_usages_target_id",
            "ix_pool_memory_usages_target_type",
            "ix_pool_memory_usages_snapshot_id",
            "ix_pool_memory_usages_memory_id",
        ):
            _drop_index_if_present(name, "pool_memory_usages")
        op.drop_table("pool_memory_usages")
    if "pool_memory_snapshots" in _table_names():
        for name in (
            "ix_pool_memory_snapshots_applied",
            "ix_pool_memory_snapshots_snapshot_hash",
            "ix_pool_memory_snapshots_target_id",
            "ix_pool_memory_snapshots_target_type",
        ):
            _drop_index_if_present(name, "pool_memory_snapshots")
        op.drop_table("pool_memory_snapshots")

"""Add source archive state scoped to each content workbench.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table_name: str) -> set[str]:
    if table_name not in _table_names():
        return set()
    return {
        str(item.get("name") or "")
        for item in sa.inspect(op.get_bind()).get_indexes(table_name)
    }


def _create_index_if_missing(
    name: str,
    table_name: str,
    columns: list[str],
) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns, unique=False)


def upgrade() -> None:
    if "source_workbench_states" not in _table_names():
        op.create_table(
            "source_workbench_states",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("source_id", sa.String(length=64), nullable=False),
            sa.Column("workbench", sa.String(length=40), nullable=False),
            sa.Column("state", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["source_id"],
                ["source_items.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "source_id",
                "workbench",
                name="uq_source_workbench_state_source_workbench",
            ),
        )
    for name, columns in (
        ("ix_source_workbench_states_source_id", ["source_id"]),
        ("ix_source_workbench_states_workbench", ["workbench"]),
        ("ix_source_workbench_states_state", ["state"]),
    ):
        _create_index_if_missing(name, "source_workbench_states", columns)


def _drop_index_if_present(name: str, table_name: str) -> None:
    if name in _index_names(table_name):
        op.drop_index(name, table_name=table_name)


def downgrade() -> None:
    if "source_workbench_states" not in _table_names():
        return
    for name in (
        "ix_source_workbench_states_state",
        "ix_source_workbench_states_workbench",
        "ix_source_workbench_states_source_id",
    ):
        _drop_index_if_present(name, "source_workbench_states")
    op.drop_table("source_workbench_states")

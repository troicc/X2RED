"""Add reusable corpus pools and generation batches.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
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
    if "corpus_pools" not in _table_names():
        op.create_table(
            "corpus_pools",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False, server_default="正在整理"),
            sa.Column("name_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("state", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("batch_size", sa.Integer(), nullable=False, server_default="6"),
            sa.Column("topic_keywords_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("profile_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_chars", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_compiled_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_corpus_pools_state",
        "corpus_pools",
        ["state"],
    )

    if "corpus_pool_sources" not in _table_names():
        op.create_table(
            "corpus_pool_sources",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("pool_id", sa.String(length=64), nullable=False),
            sa.Column("source_id", sa.String(length=64), nullable=False),
            sa.Column("normalized_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("keywords_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["pool_id"], ["corpus_pools.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_id"], ["source_items.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("pool_id", "source_id"),
        )
    _create_index_if_missing(
        "ix_corpus_pool_sources_pool_id",
        "corpus_pool_sources",
        ["pool_id"],
    )
    _create_index_if_missing(
        "ix_corpus_pool_sources_source_id",
        "corpus_pool_sources",
        ["source_id"],
    )

    if "corpus_batches" not in _table_names():
        op.create_table(
            "corpus_batches",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("pool_id", sa.String(length=64), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("focus", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_ids_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("source_fingerprint", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("profile_revision", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("anchor_source_id", sa.String(length=64), nullable=True),
            sa.Column("draft_id", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["anchor_source_id"], ["source_items.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["pool_id"], ["corpus_pools.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("pool_id", "sequence"),
        )
    _create_index_if_missing(
        "ix_corpus_batches_pool_id",
        "corpus_batches",
        ["pool_id"],
    )
    _create_index_if_missing(
        "ix_corpus_batches_source_fingerprint",
        "corpus_batches",
        ["source_fingerprint"],
    )
    _create_index_if_missing(
        "ix_corpus_batches_anchor_source_id",
        "corpus_batches",
        ["anchor_source_id"],
    )
    _create_index_if_missing(
        "ix_corpus_batches_draft_id",
        "corpus_batches",
        ["draft_id"],
    )


def _drop_index_if_present(name: str, table_name: str) -> None:
    if name in _index_names(table_name):
        op.drop_index(name, table_name=table_name)


def downgrade() -> None:
    if "corpus_batches" in _table_names():
        _drop_index_if_present("ix_corpus_batches_draft_id", "corpus_batches")
        _drop_index_if_present("ix_corpus_batches_anchor_source_id", "corpus_batches")
        _drop_index_if_present("ix_corpus_batches_source_fingerprint", "corpus_batches")
        _drop_index_if_present("ix_corpus_batches_pool_id", "corpus_batches")
        op.drop_table("corpus_batches")
    if "corpus_pool_sources" in _table_names():
        _drop_index_if_present("ix_corpus_pool_sources_source_id", "corpus_pool_sources")
        _drop_index_if_present("ix_corpus_pool_sources_pool_id", "corpus_pool_sources")
        op.drop_table("corpus_pool_sources")
    if "corpus_pools" in _table_names():
        _drop_index_if_present("ix_corpus_pools_state", "corpus_pools")
        op.drop_table("corpus_pools")

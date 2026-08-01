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


def upgrade() -> None:
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
    op.create_index("ix_corpus_pools_state", "corpus_pools", ["state"], unique=False)

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
    op.create_index(
        "ix_corpus_pool_sources_pool_id",
        "corpus_pool_sources",
        ["pool_id"],
        unique=False,
    )
    op.create_index(
        "ix_corpus_pool_sources_source_id",
        "corpus_pool_sources",
        ["source_id"],
        unique=False,
    )

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
    op.create_index("ix_corpus_batches_pool_id", "corpus_batches", ["pool_id"], unique=False)
    op.create_index(
        "ix_corpus_batches_source_fingerprint",
        "corpus_batches",
        ["source_fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_corpus_batches_anchor_source_id",
        "corpus_batches",
        ["anchor_source_id"],
        unique=False,
    )
    op.create_index("ix_corpus_batches_draft_id", "corpus_batches", ["draft_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_corpus_batches_draft_id", table_name="corpus_batches")
    op.drop_index("ix_corpus_batches_anchor_source_id", table_name="corpus_batches")
    op.drop_index("ix_corpus_batches_source_fingerprint", table_name="corpus_batches")
    op.drop_index("ix_corpus_batches_pool_id", table_name="corpus_batches")
    op.drop_table("corpus_batches")
    op.drop_index("ix_corpus_pool_sources_source_id", table_name="corpus_pool_sources")
    op.drop_index("ix_corpus_pool_sources_pool_id", table_name="corpus_pool_sources")
    op.drop_table("corpus_pool_sources")
    op.drop_index("ix_corpus_pools_state", table_name="corpus_pools")
    op.drop_table("corpus_pools")

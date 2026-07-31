"""discovery candidate inbox

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("discovery_runs"):
        op.create_table(
            "discovery_runs",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("provider", sa.String(length=40), nullable=False),
            sa.Column("kind", sa.String(length=40), nullable=False),
            sa.Column("query", sa.Text(), nullable=False),
            sa.Column("params_json", sa.Text(), nullable=False),
            sa.Column("cursor_json", sa.Text(), nullable=False),
            sa.Column("raw_snapshot_id", sa.String(length=64), nullable=True),
            sa.Column("candidate_count", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["raw_snapshot_id"],
                ["raw_snapshots.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_discovery_runs_provider", "discovery_runs", ["provider"])
        op.create_index("ix_discovery_runs_kind", "discovery_runs", ["kind"])

    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("discovery_candidates"):
        op.create_table(
            "discovery_candidates",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("dedupe_key", sa.String(length=255), nullable=False),
            sa.Column("kind", sa.String(length=40), nullable=False),
            sa.Column("external_id", sa.String(length=80), nullable=False),
            sa.Column("canonical_url", sa.Text(), nullable=False),
            sa.Column("author_handle", sa.String(length=80), nullable=False),
            sa.Column("author_name", sa.String(length=160), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=False),
            sa.Column("state", sa.String(length=30), nullable=False),
            sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["discovery_runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("dedupe_key", name="uq_discovery_candidates_dedupe_key"),
        )
        op.create_index(
            "ix_discovery_candidates_dedupe_key",
            "discovery_candidates",
            ["dedupe_key"],
            unique=True,
        )
        op.create_index("ix_discovery_candidates_kind", "discovery_candidates", ["kind"])
        op.create_index(
            "ix_discovery_candidates_external_id",
            "discovery_candidates",
            ["external_id"],
        )
        op.create_index(
            "ix_discovery_candidates_author_handle",
            "discovery_candidates",
            ["author_handle"],
        )
        op.create_index("ix_discovery_candidates_state", "discovery_candidates", ["state"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("discovery_candidates"):
        indexes = {index["name"] for index in inspector.get_indexes("discovery_candidates")}
        for name in (
            "ix_discovery_candidates_state",
            "ix_discovery_candidates_author_handle",
            "ix_discovery_candidates_external_id",
            "ix_discovery_candidates_kind",
            "ix_discovery_candidates_dedupe_key",
        ):
            if name in indexes:
                op.drop_index(name, table_name="discovery_candidates")
        op.drop_table("discovery_candidates")

    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("discovery_runs"):
        indexes = {index["name"] for index in inspector.get_indexes("discovery_runs")}
        if "ix_discovery_runs_kind" in indexes:
            op.drop_index("ix_discovery_runs_kind", table_name="discovery_runs")
        if "ix_discovery_runs_provider" in indexes:
            op.drop_index("ix_discovery_runs_provider", table_name="discovery_runs")
        op.drop_table("discovery_runs")

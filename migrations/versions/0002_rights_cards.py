"""rights gate and card renders

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    source_columns = _columns("source_items")
    source_indexes = _indexes("source_items")
    with op.batch_alter_table("source_items") as batch:
        if "rights_status" not in source_columns:
            batch.add_column(
                sa.Column(
                    "rights_status",
                    sa.String(length=32),
                    nullable=False,
                    server_default="needs_review",
                )
            )
        if "rights_note" not in source_columns:
            batch.add_column(sa.Column("rights_note", sa.Text(), nullable=False, server_default=""))
        if "ix_source_items_rights_status" not in source_indexes:
            batch.create_index("ix_source_items_rights_status", ["rights_status"])

    asset_columns = _columns("assets")
    asset_indexes = _indexes("assets")
    with op.batch_alter_table("assets") as batch:
        if "rights_status" not in asset_columns:
            batch.add_column(
                sa.Column(
                    "rights_status",
                    sa.String(length=32),
                    nullable=False,
                    server_default="needs_review",
                )
            )
        if "rights_note" not in asset_columns:
            batch.add_column(sa.Column("rights_note", sa.Text(), nullable=False, server_default=""))
        if "ix_assets_rights_status" not in asset_indexes:
            batch.create_index("ix_assets_rights_status", ["rights_status"])

    review_columns = _columns("review_decisions")
    with op.batch_alter_table("review_decisions") as batch:
        if "facts_checked" not in review_columns:
            batch.add_column(
                sa.Column("facts_checked", sa.Boolean(), nullable=False, server_default=sa.false())
            )
        if "rights_checked" not in review_columns:
            batch.add_column(
                sa.Column("rights_checked", sa.Boolean(), nullable=False, server_default=sa.false())
            )

    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("card_renders"):
        op.create_table(
            "card_renders",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("draft_id", sa.String(length=64), nullable=False),
            sa.Column("template", sa.String(length=40), nullable=False),
            sa.Column("spec_json", sa.Text(), nullable=False),
            sa.Column("output_paths_json", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("error", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["draft_id"], ["draft_revisions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_card_renders_status", "card_renders", ["status"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("card_renders"):
        card_indexes = _indexes("card_renders")
        if "ix_card_renders_status" in card_indexes:
            op.drop_index("ix_card_renders_status", table_name="card_renders")
        op.drop_table("card_renders")

    review_columns = _columns("review_decisions")
    with op.batch_alter_table("review_decisions") as batch:
        if "rights_checked" in review_columns:
            batch.drop_column("rights_checked")
        if "facts_checked" in review_columns:
            batch.drop_column("facts_checked")

    asset_columns = _columns("assets")
    asset_indexes = _indexes("assets")
    with op.batch_alter_table("assets") as batch:
        if "ix_assets_rights_status" in asset_indexes:
            batch.drop_index("ix_assets_rights_status")
        if "rights_note" in asset_columns:
            batch.drop_column("rights_note")
        if "rights_status" in asset_columns:
            batch.drop_column("rights_status")

    source_columns = _columns("source_items")
    source_indexes = _indexes("source_items")
    with op.batch_alter_table("source_items") as batch:
        if "ix_source_items_rights_status" in source_indexes:
            batch.drop_index("ix_source_items_rights_status")
        if "rights_note" in source_columns:
            batch.drop_column("rights_note")
        if "rights_status" in source_columns:
            batch.drop_column("rights_status")

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


def upgrade() -> None:
    with op.batch_alter_table("source_items") as batch:
        batch.add_column(
            sa.Column("rights_status", sa.String(length=32), nullable=False, server_default="needs_review")
        )
        batch.add_column(sa.Column("rights_note", sa.Text(), nullable=False, server_default=""))
        batch.create_index("ix_source_items_rights_status", ["rights_status"])

    with op.batch_alter_table("assets") as batch:
        batch.add_column(
            sa.Column("rights_status", sa.String(length=32), nullable=False, server_default="needs_review")
        )
        batch.add_column(sa.Column("rights_note", sa.Text(), nullable=False, server_default=""))
        batch.create_index("ix_assets_rights_status", ["rights_status"])

    with op.batch_alter_table("review_decisions") as batch:
        batch.add_column(
            sa.Column("facts_checked", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column("rights_checked", sa.Boolean(), nullable=False, server_default=sa.false())
        )

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
    op.drop_index("ix_card_renders_status", table_name="card_renders")
    op.drop_table("card_renders")
    with op.batch_alter_table("review_decisions") as batch:
        batch.drop_column("rights_checked")
        batch.drop_column("facts_checked")
    with op.batch_alter_table("assets") as batch:
        batch.drop_index("ix_assets_rights_status")
        batch.drop_column("rights_note")
        batch.drop_column("rights_status")
    with op.batch_alter_table("source_items") as batch:
        batch.drop_index("ix_source_items_rights_status")
        batch.drop_column("rights_note")
        batch.drop_column("rights_status")

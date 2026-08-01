"""Add multi-platform content variants.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "platform_variants" in inspector.get_table_names():
        return

    op.create_table(
        "platform_variants",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("base_draft_id", sa.String(length=64), nullable=True),
        sa.Column("platform", sa.String(length=30), nullable=False),
        sa.Column("format", sa.String(length=30), nullable=False, server_default="article"),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("subtitle", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("body_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("body_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", sa.Text(), nullable=False, server_default=""),
        sa.Column("theme", sa.String(length=60), nullable=False, server_default="auto"),
        sa.Column("skill_profile_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("output_paths_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(length=40), nullable=False, server_default="system"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["base_draft_id"], ["draft_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["source_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "platform", "version"),
    )
    op.create_index("ix_platform_variants_source_id", "platform_variants", ["source_id"])
    op.create_index("ix_platform_variants_base_draft_id", "platform_variants", ["base_draft_id"])
    op.create_index("ix_platform_variants_platform", "platform_variants", ["platform"])
    op.create_index("ix_platform_variants_status", "platform_variants", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "platform_variants" not in inspector.get_table_names():
        return
    op.drop_index("ix_platform_variants_status", table_name="platform_variants")
    op.drop_index("ix_platform_variants_platform", table_name="platform_variants")
    op.drop_index("ix_platform_variants_base_draft_id", table_name="platform_variants")
    op.drop_index("ix_platform_variants_source_id", table_name="platform_variants")
    op.drop_table("platform_variants")

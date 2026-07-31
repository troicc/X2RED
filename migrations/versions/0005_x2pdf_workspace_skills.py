"""X2PDF documents, source lifecycle and skill settings.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("source_items") as batch:
        batch.add_column(
            sa.Column(
                "workspace_state",
                sa.String(length=20),
                nullable=False,
                server_default="active",
            )
        )
        batch.add_column(
            sa.Column(
                "content_kind",
                sa.String(length=30),
                nullable=False,
                server_default="post",
            )
        )
        batch.add_column(
            sa.Column(
                "structured_content_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
        batch.add_column(
            sa.Column("editor_note", sa.Text(), nullable=False, server_default="")
        )
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("last_published_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column("published_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.create_index(
            "ix_source_items_workspace_state", ["workspace_state"], unique=False
        )
        batch.create_index("ix_source_items_content_kind", ["content_kind"], unique=False)

    op.create_table(
        "skill_bindings",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("skill_name", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("model_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column(
            "reasoning_effort",
            sa.String(length=20),
            nullable=False,
            server_default="medium",
        ),
        sa.Column(
            "prompt_version", sa.String(length=40), nullable=False, server_default="v1"
        ),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_name"),
    )
    op.create_index(
        "ix_skill_bindings_skill_name",
        "skill_bindings",
        ["skill_name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_skill_bindings_skill_name", table_name="skill_bindings")
    op.drop_table("skill_bindings")
    with op.batch_alter_table("source_items") as batch:
        batch.drop_index("ix_source_items_content_kind")
        batch.drop_index("ix_source_items_workspace_state")
        batch.drop_column("published_count")
        batch.drop_column("last_published_at")
        batch.drop_column("archived_at")
        batch.drop_column("editor_note")
        batch.drop_column("structured_content_json")
        batch.drop_column("content_kind")
        batch.drop_column("workspace_state")

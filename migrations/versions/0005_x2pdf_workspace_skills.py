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

_SOURCE_COLUMNS: dict[str, sa.Column] = {
    "workspace_state": sa.Column(
        "workspace_state",
        sa.String(length=20),
        nullable=False,
        server_default="active",
    ),
    "content_kind": sa.Column(
        "content_kind",
        sa.String(length=30),
        nullable=False,
        server_default="post",
    ),
    "structured_content_json": sa.Column(
        "structured_content_json",
        sa.Text(),
        nullable=False,
        server_default="{}",
    ),
    "editor_note": sa.Column(
        "editor_note",
        sa.Text(),
        nullable=False,
        server_default="",
    ),
    "archived_at": sa.Column(
        "archived_at",
        sa.DateTime(timezone=True),
        nullable=True,
    ),
    "last_published_at": sa.Column(
        "last_published_at",
        sa.DateTime(timezone=True),
        nullable=True,
    ),
    "published_count": sa.Column(
        "published_count",
        sa.Integer(),
        nullable=False,
        server_default="0",
    ),
}


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    existing_columns = {
        column["name"] for column in inspector.get_columns("source_items")
    }
    for name, column in _SOURCE_COLUMNS.items():
        if name not in existing_columns:
            op.add_column("source_items", column)

    inspector = _inspector()
    existing_indexes = {
        index["name"] for index in inspector.get_indexes("source_items")
    }
    if "ix_source_items_workspace_state" not in existing_indexes:
        op.create_index(
            "ix_source_items_workspace_state",
            "source_items",
            ["workspace_state"],
            unique=False,
        )
    if "ix_source_items_content_kind" not in existing_indexes:
        op.create_index(
            "ix_source_items_content_kind",
            "source_items",
            ["content_kind"],
            unique=False,
        )

    inspector = _inspector()
    if "skill_bindings" not in inspector.get_table_names():
        op.create_table(
            "skill_bindings",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("skill_name", sa.String(length=100), nullable=False),
            sa.Column(
                "enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "model_name",
                sa.String(length=120),
                nullable=False,
                server_default="",
            ),
            sa.Column(
                "reasoning_effort",
                sa.String(length=20),
                nullable=False,
                server_default="medium",
            ),
            sa.Column(
                "prompt_version",
                sa.String(length=40),
                nullable=False,
                server_default="v1",
            ),
            sa.Column(
                "config_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("skill_name"),
        )

    inspector = _inspector()
    skill_indexes = {
        index["name"] for index in inspector.get_indexes("skill_bindings")
    }
    if "ix_skill_bindings_skill_name" not in skill_indexes:
        op.create_index(
            "ix_skill_bindings_skill_name",
            "skill_bindings",
            ["skill_name"],
            unique=True,
        )


def downgrade() -> None:
    inspector = _inspector()
    tables = set(inspector.get_table_names())
    if "skill_bindings" in tables:
        indexes = {
            index["name"] for index in inspector.get_indexes("skill_bindings")
        }
        if "ix_skill_bindings_skill_name" in indexes:
            op.drop_index(
                "ix_skill_bindings_skill_name",
                table_name="skill_bindings",
            )
        op.drop_table("skill_bindings")

    inspector = _inspector()
    indexes = {
        index["name"] for index in inspector.get_indexes("source_items")
    }
    if "ix_source_items_content_kind" in indexes:
        op.drop_index(
            "ix_source_items_content_kind",
            table_name="source_items",
        )
    if "ix_source_items_workspace_state" in indexes:
        op.drop_index(
            "ix_source_items_workspace_state",
            table_name="source_items",
        )

    existing_columns = {
        column["name"] for column in _inspector().get_columns("source_items")
    }
    removable = [
        name for name in reversed(tuple(_SOURCE_COLUMNS)) if name in existing_columns
    ]
    if removable:
        with op.batch_alter_table("source_items") as batch:
            for name in removable:
                batch.drop_column(name)

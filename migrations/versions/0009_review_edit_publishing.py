"""Versioned review/edit artifacts and publishing handoff.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "review_artifacts" not in tables:
        op.create_table(
            "review_artifacts",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("scope_type", sa.String(length=40), nullable=False),
            sa.Column("scope_id", sa.String(length=64), nullable=False),
            sa.Column("artifact_type", sa.String(length=60), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("parent_id", sa.String(length=64), server_default="", nullable=False),
            sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
            sa.Column("state", sa.String(length=30), server_default="draft", nullable=False),
            sa.Column("review_note", sa.Text(), server_default="", nullable=False),
            sa.Column("created_by", sa.String(length=40), server_default="system", nullable=False),
            sa.Column("applied_to_id", sa.String(length=64), server_default="", nullable=False),
            sa.Column("error", sa.Text(), server_default="", nullable=False),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "scope_type",
                "scope_id",
                "artifact_type",
                "version",
                name="uq_review_artifact_version",
            ),
        )
    inspector = sa.inspect(op.get_bind())
    indexes = {
        index["name"]
        for index in inspector.get_indexes("review_artifacts")
        if index.get("name")
    }
    for name, columns in (
        ("ix_review_artifacts_scope_type", ["scope_type"]),
        ("ix_review_artifacts_scope_id", ["scope_id"]),
        ("ix_review_artifacts_artifact_type", ["artifact_type"]),
        ("ix_review_artifacts_state", ["state"]),
        ("ix_review_artifacts_parent_id", ["parent_id"]),
        ("ix_review_artifacts_applied_to_id", ["applied_to_id"]),
    ):
        if name not in indexes:
            op.create_index(name, "review_artifacts", columns, unique=False)


def downgrade() -> None:
    op.drop_table("review_artifacts")

"""Freeze style profile rules per writing project.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app.domain import style_snapshot  # noqa: F401

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["writing_style_snapshots"].create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.tables["writing_style_snapshots"].drop(bind=op.get_bind(), checkfirst=True)

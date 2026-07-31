"""initial X2RED schema

Revision ID: 0001
Revises:
Create Date: 2026-07-31
"""
from __future__ import annotations

from alembic import op

from app.db.base import Base
from app.domain import models  # noqa: F401

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())

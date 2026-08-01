from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.models import new_id, utcnow


class ReviewArtifactState(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    changes_requested = "changes_requested"
    superseded = "superseded"
    applied = "applied"
    failed = "failed"


class ReviewArtifact(Base):
    """A durable, human-editable artifact between AI generation and rendering.

    The payload is deliberately platform-neutral JSON. Each edit creates a new
    immutable version so downstream renders can always identify exactly which
    reviewed storyboard/module tree/cover brief produced them.
    """

    __tablename__ = "review_artifacts"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", "artifact_type", "version"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("review_artifact")
    )
    scope_type: Mapped[str] = mapped_column(String(40), index=True)
    scope_id: Mapped[str] = mapped_column(String(64), index=True)
    artifact_type: Mapped[str] = mapped_column(String(60), index=True)
    version: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    state: Mapped[str] = mapped_column(
        String(30), default=ReviewArtifactState.draft.value, index=True
    )
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(40), default="system")
    applied_to_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

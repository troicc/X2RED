from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.models import new_id, utcnow


class WritingStyleSnapshot(Base):
    __tablename__ = "writing_style_snapshots"
    __table_args__ = (UniqueConstraint("project_id", name="uq_writing_style_snapshot_project"),)

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("style_snapshot")
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("writing_projects.id", ondelete="CASCADE"), index=True
    )
    style_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("style_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    style_profile_version: Mapped[int] = mapped_column(Integer, default=0)
    profile_name: Mapped[str] = mapped_column(String(120), default="Default")
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

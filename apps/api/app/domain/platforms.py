from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.models import new_id, utcnow


class PlatformVariantState(str, enum.Enum):
    draft = "draft"
    rendered = "rendered"
    packaged = "packaged"
    failed = "failed"


class PlatformVariant(Base):
    __tablename__ = "platform_variants"
    __table_args__ = (UniqueConstraint("source_id", "platform", "version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("variant"))
    source_id: Mapped[str] = mapped_column(
        ForeignKey("source_items.id", ondelete="CASCADE"), index=True
    )
    base_draft_id: Mapped[str | None] = mapped_column(
        ForeignKey("draft_revisions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    platform: Mapped[str] = mapped_column(String(30), index=True)
    format: Mapped[str] = mapped_column(String(30), default="article")
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160), default="")
    subtitle: Mapped[str] = mapped_column(String(240), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    body_markdown: Mapped[str] = mapped_column(Text, default="")
    body_html: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="")
    theme: Mapped[str] = mapped_column(String(60), default="auto")
    skill_profile_json: Mapped[str] = mapped_column(Text, default="{}")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    output_paths_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(
        String(30), default=PlatformVariantState.draft.value, index=True
    )
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(40), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

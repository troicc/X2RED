from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.models import new_id, utcnow


class CandidateState(str, enum.Enum):
    new = "new"
    saved = "saved"
    dismissed = "dismissed"
    imported = "imported"


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("discover"))
    provider: Mapped[str] = mapped_column(String(40), default="fxtwitter", index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    query: Mapped[str] = mapped_column(Text, default="")
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    cursor_json: Mapped[str] = mapped_column(Text, default="{}")
    raw_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("raw_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    candidates: Mapped[list[DiscoveryCandidate]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class DiscoveryCandidate(Base):
    __tablename__ = "discovery_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("candidate"))
    run_id: Mapped[str] = mapped_column(ForeignKey("discovery_runs.id", ondelete="CASCADE"))
    dedupe_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    external_id: Mapped[str] = mapped_column(String(80), default="", index=True)
    canonical_url: Mapped[str] = mapped_column(Text, default="")
    author_handle: Mapped[str] = mapped_column(String(80), default="", index=True)
    author_name: Mapped[str] = mapped_column(String(160), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    state: Mapped[str] = mapped_column(String(30), default=CandidateState.new.value, index=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    run: Mapped[DiscoveryRun] = relationship(back_populates="candidates")

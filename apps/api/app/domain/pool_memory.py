from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.models import new_id, utcnow


class PoolMemorySnapshot(Base):
    """Immutable memory selection frozen for one generation target.

    ``applied`` is an execution outcome rather than part of the selection.  It is
    finalized only after a configured model has actually consumed the snapshot;
    deterministic fallbacks therefore never pretend that personal memory shaped
    their output.
    """

    __tablename__ = "pool_memory_snapshots"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("memory_snapshot")
    )
    target_type: Mapped[str] = mapped_column(String(60), index=True)
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    query_json: Mapped[str] = mapped_column(Text, default="{}")
    memory_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    prompt_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    model_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    applied: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    model_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PoolMemoryUsage(Base):
    """Append-only record of one memory card affecting one generation role."""

    __tablename__ = "pool_memory_usages"
    __table_args__ = (
        UniqueConstraint(
            "memory_id",
            "snapshot_id",
            "agent_role",
            "stage",
            name="uq_pool_memory_usage_role_stage",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("memory_usage")
    )
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("review_artifacts.id", ondelete="CASCADE"), index=True
    )
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("pool_memory_snapshots.id", ondelete="CASCADE"), index=True
    )
    target_type: Mapped[str] = mapped_column(String(60), index=True)
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_role: Mapped[str] = mapped_column(String(60), default="", index=True)
    stage: Mapped[str] = mapped_column(String(60), default="", index=True)
    selected_reason: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

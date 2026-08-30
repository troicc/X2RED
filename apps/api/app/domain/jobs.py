from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.models import new_id, utcnow


class JobState(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    dead_letter = "dead_letter"
    canceled = "canceled"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index(
            "uq_jobs_active_dedupe",
            "dedupe_key",
            unique=True,
            sqlite_where=text(
                "dedupe_key <> '' AND state IN ('pending', 'running')"
            ),
            postgresql_where=text(
                "dedupe_key <> '' AND state IN ('pending', 'running')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("job"))
    kind: Mapped[str] = mapped_column(String(80), index=True)
    state: Mapped[str] = mapped_column(String(30), default=JobState.pending.value, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), default="", index=True)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    locked_by: Mapped[str] = mapped_column(String(120), default="")
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_worker_id: Mapped[str] = mapped_column(String(160), default="")
    last_error_code: Mapped[str] = mapped_column(String(80), default="")
    dead_lettered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

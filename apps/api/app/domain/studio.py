from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.models import new_id, utcnow


class MonitorKind(str, enum.Enum):
    profile = "profile"
    search = "search"
    quotes = "quotes"
    trends = "trends"


class AnalysisLevel(str, enum.Enum):
    l1 = "l1"
    l2 = "l2"


class AnalysisStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class WritingMode(str, enum.Enum):
    fast = "fast"
    studio = "studio"


class WritingState(str, enum.Enum):
    clarifying = "clarifying"
    awaiting_brief_approval = "awaiting_brief_approval"
    researching = "researching"
    outlining = "outlining"
    awaiting_outline_approval = "awaiting_outline_approval"
    drafting = "drafting"
    reviewing = "reviewing"
    awaiting_revision_approval = "awaiting_revision_approval"
    revising = "revising"
    claims_blocked = "claims_blocked"
    completed = "completed"
    canceled = "canceled"
    failed = "failed"


class AgentRunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    degraded = "degraded"
    failed = "failed"
    cached = "cached"


class MonitorTarget(Base):
    __tablename__ = "monitor_targets"
    __table_args__ = (UniqueConstraint("platform", "kind", "target", name="uq_monitor_target"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("monitor"))
    name: Mapped[str] = mapped_column(String(160), default="")
    platform: Mapped[str] = mapped_column(String(20), default="x", index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    target: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=360)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    cursor_json: Mapped[str] = mapped_column(Text, default="{}")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("metric"))
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("discovery_candidates.id", ondelete="CASCADE"), nullable=True, index=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"), nullable=True, index=True)
    target_id: Mapped[str | None] = mapped_column(ForeignKey("monitor_targets.id", ondelete="SET NULL"), nullable=True, index=True)
    author_handle: Mapped[str] = mapped_column(String(80), default="", index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    followers: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    reposts: Mapped[int] = mapped_column(Integer, default=0)
    quotes: Mapped[int] = mapped_column(Integer, default=0)
    replies: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    bookmarks: Mapped[int] = mapped_column(Integer, default=0)
    core_engagement: Mapped[float] = mapped_column(Float, default=0.0)
    content_age_hours: Mapped[float] = mapped_column(Float, default=0.0)
    raw_json: Mapped[str] = mapped_column(Text, default="{}")


class ScoreRecord(Base):
    __tablename__ = "score_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("score"))
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("discovery_candidates.id", ondelete="CASCADE"), nullable=True, index=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"), nullable=True, index=True)
    target_id: Mapped[str | None] = mapped_column(ForeignKey("monitor_targets.id", ondelete="SET NULL"), nullable=True, index=True)
    score_version: Mapped[str] = mapped_column(String(40), default="x-v1", index=True)
    grade: Mapped[str] = mapped_column(String(30), default="ordinary", index=True)
    label: Mapped[str] = mapped_column(String(40), default="普通")
    r_value: Mapped[float] = mapped_column(Float, default=0.0)
    m_value: Mapped[float] = mapped_column(Float, default=0.0)
    v_value: Mapped[float] = mapped_column(Float, default=0.0)
    velocity: Mapped[float] = mapped_column(Float, default=0.0)
    baseline_value: Mapped[float] = mapped_column(Float, default=1.0)
    followers_snapshot: Mapped[int] = mapped_column(Integer, default=0)
    baseline_sample_json: Mapped[str] = mapped_column(Text, default="[]")
    thresholds_json: Mapped[str] = mapped_column(Text, default="{}")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    first_scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ContentAnalysis(Base):
    __tablename__ = "content_analyses"
    __table_args__ = (UniqueConstraint("candidate_id", "level", "input_hash", name="uq_candidate_analysis"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("analysis"))
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("discovery_candidates.id", ondelete="CASCADE"), nullable=True, index=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"), nullable=True, index=True)
    level: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(30), default=AnalysisStatus.pending.value, index=True)
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    model_name: Mapped[str] = mapped_column(String(120), default="")
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PatternCard(Base):
    __tablename__ = "pattern_cards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("pattern"))
    name: Mapped[str] = mapped_column(String(180), index=True)
    category: Mapped[str] = mapped_column(String(80), default="general", index=True)
    source_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    hook_pattern: Mapped[str] = mapped_column(Text, default="")
    structure_pattern: Mapped[str] = mapped_column(Text, default="")
    audience_trigger: Mapped[str] = mapped_column(Text, default="")
    evidence_pattern: Mapped[str] = mapped_column(Text, default="")
    replicable_elements_json: Mapped[str] = mapped_column(Text, default="[]")
    non_replicable_context_json: Mapped[str] = mapped_column(Text, default="[]")
    suitable_topics_json: Mapped[str] = mapped_column(Text, default="[]")
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    success_feedback: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StyleProfile(Base):
    __tablename__ = "style_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("style"))
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    rules_json: Mapped[str] = mapped_column(Text, default="{}")
    forbidden_json: Mapped[str] = mapped_column(Text, default="[]")
    samples_json: Mapped[str] = mapped_column(Text, default="[]")
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class WritingProject(Base):
    __tablename__ = "writing_projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("writing"))
    source_id: Mapped[str] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(20), default=WritingMode.studio.value, index=True)
    state: Mapped[str] = mapped_column(String(40), default=WritingState.clarifying.value, index=True)
    current_stage: Mapped[str] = mapped_column(String(60), default="editorial_brief")
    reader: Mapped[str] = mapped_column(Text, default="")
    promise: Mapped[str] = mapped_column(Text, default="")
    main_thesis: Mapped[str] = mapped_column(Text, default="")
    style_profile_id: Mapped[str | None] = mapped_column(ForeignKey("style_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    budget_limit_cents: Mapped[int] = mapped_column(Integer, default=100)
    spent_estimate_cents: Mapped[int] = mapped_column(Integer, default=0)
    spent_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class WritingArtifact(Base):
    __tablename__ = "writing_artifacts"
    __table_args__ = (UniqueConstraint("project_id", "artifact_type", "version", name="uq_writing_artifact"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("artifact"))
    project_id: Mapped[str] = mapped_column(ForeignKey("writing_projects.id", ondelete="CASCADE"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(60), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content_json: Mapped[str] = mapped_column(Text, default="{}")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_by_role: Mapped[str] = mapped_column(String(60), default="system")
    approved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("agent"))
    project_id: Mapped[str] = mapped_column(ForeignKey("writing_projects.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(60), index=True)
    stage: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(30), default=AgentRunStatus.pending.value, index=True)
    model_name: Mapped[str] = mapped_column(String(120), default="")
    reasoning_effort: Mapped[str] = mapped_column(String(20), default="medium")
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    output_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("writing_artifacts.id", ondelete="SET NULL"), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    usage_json: Mapped[str] = mapped_column(Text, default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WritingFeedback(Base):
    __tablename__ = "writing_feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("feedback"))
    project_id: Mapped[str] = mapped_column(ForeignKey("writing_projects.id", ondelete="CASCADE"), index=True)
    draft_before_id: Mapped[str | None] = mapped_column(ForeignKey("draft_revisions.id", ondelete="SET NULL"), nullable=True)
    draft_after_id: Mapped[str | None] = mapped_column(ForeignKey("draft_revisions.id", ondelete="SET NULL"), nullable=True)
    diff_json: Mapped[str] = mapped_column(Text, default="{}")
    feedback_reason: Mapped[str] = mapped_column(Text, default="")
    affected_rules_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

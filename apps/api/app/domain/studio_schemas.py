from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MonitorTargetCreate(BaseModel):
    name: str = Field(default="", max_length=160)
    kind: Literal["profile", "search", "quotes", "trends"]
    target: str = Field(min_length=1, max_length=2000)
    interval_minutes: int = Field(default=360, ge=15, le=10080)
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class MonitorTargetUpdate(BaseModel):
    name: str = Field(default="", max_length=160)
    interval_minutes: int = Field(default=360, ge=15, le=10080)
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class MonitorTargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    platform: str
    kind: str
    target: str
    enabled: bool
    interval_minutes: int
    config_json: str
    cursor_json: str
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_error: str
    created_at: datetime
    updated_at: datetime


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str | None
    source_id: str | None
    target_id: str | None
    score_version: str
    grade: str
    label: str
    r_value: float
    m_value: float
    v_value: float
    velocity: float
    baseline_value: float
    followers_snapshot: int
    baseline_sample_json: str
    thresholds_json: str
    evidence_json: str
    first_scored_at: datetime
    last_refreshed_at: datetime


class SignalFeedItem(BaseModel):
    candidate_id: str
    canonical_url: str
    author_handle: str
    author_name: str
    text: str
    discovered_at: datetime
    metadata: dict[str, Any]
    score: ScoreOut | None = None
    l1_analysis: dict[str, Any] | None = None
    l2_analysis: dict[str, Any] | None = None
    l2_analysis_id: str = ""
    promoted_source_id: str = ""


class SignalDashboard(BaseModel):
    active_targets: int
    due_targets: int
    candidates: int
    grade_counts: dict[str, int]
    pending_l1: int
    pending_l2: int
    writing_projects: int


class AnalysisRequest(BaseModel):
    level: Literal["l1", "l2"] = "l1"


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str | None
    source_id: str | None
    level: str
    status: str
    result_json: str
    evidence_json: str
    model_name: str
    input_hash: str
    error: str
    created_at: datetime
    updated_at: datetime


class SignalPromoteRequest(BaseModel):
    mode: Literal["fast", "studio"] = "studio"
    reader: str = Field(default="", max_length=2000)
    promise: str = Field(default="", max_length=2000)
    main_thesis: str = Field(default="", max_length=2000)
    style_profile_id: str | None = None
    budget_limit_cents: int = Field(default=100, ge=0, le=10000)


class SignalPromoteResult(BaseModel):
    candidate_id: str
    analysis_id: str
    source_id: str
    project_id: str
    source_created: bool
    reader: str
    promise: str
    main_thesis: str


class PatternCardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    category: str = Field(default="general", max_length=80)
    source_ids: list[str] = Field(default_factory=list)
    hook_pattern: str = ""
    structure_pattern: str = ""
    audience_trigger: str = ""
    evidence_pattern: str = ""
    replicable_elements: list[str] = Field(default_factory=list)
    non_replicable_context: list[str] = Field(default_factory=list)
    suitable_topics: list[str] = Field(default_factory=list)


class PatternCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    category: str
    source_ids_json: str
    hook_pattern: str
    structure_pattern: str
    audience_trigger: str
    evidence_pattern: str
    replicable_elements_json: str
    non_replicable_context_json: str
    suitable_topics_json: str
    usage_count: int
    success_feedback: str
    created_at: datetime
    updated_at: datetime


class StyleProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    rules: dict[str, Any] = Field(default_factory=dict)
    forbidden: list[str] = Field(default_factory=list)
    samples: list[dict[str, Any] | str] = Field(default_factory=list)


class StyleProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    rules_json: str
    forbidden_json: str
    samples_json: str
    version: int
    active: bool
    created_at: datetime
    updated_at: datetime


class WritingProjectCreate(BaseModel):
    source_id: str
    supporting_source_ids: list[str] = Field(default_factory=list, max_length=12)
    material_refs: list[str] = Field(default_factory=list, max_length=32)
    mode: Literal["fast", "studio"] = "studio"
    reader: str = Field(default="", max_length=2000)
    promise: str = Field(default="", max_length=2000)
    main_thesis: str = Field(default="", max_length=2000)
    style_profile_id: str | None = None
    budget_limit_cents: int = Field(default=100, ge=0, le=10000)


class WritingMaterialOption(BaseModel):
    ref: str
    kind: Literal["source", "draft_revision", "platform_variant"]
    id: str
    source_id: str
    title: str
    excerpt: str
    author: str
    platform: str
    version: int | None = None
    status: str
    created_at: datetime | None


class WritingArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    artifact_type: str
    version: int
    content_json: str
    content_hash: str
    created_by_role: str
    approved: bool
    created_at: datetime


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    role: str
    stage: str
    status: str
    model_name: str
    reasoning_effort: str
    input_hash: str
    output_artifact_id: str | None
    attempts: int
    error: str
    usage_json: str
    started_at: datetime | None
    finished_at: datetime | None


class WritingProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    source_ids: list[str] = Field(default_factory=list)
    source_summaries: list[dict[str, Any]] = Field(default_factory=list)
    material_summaries: list[dict[str, Any]] = Field(default_factory=list)
    mode: str
    state: str
    current_stage: str
    reader: str
    promise: str
    main_thesis: str
    style_profile_id: str | None
    budget_limit_cents: int
    spent_estimate_cents: int
    error: str
    output_draft_id: str = ""
    output_draft_version: int | None = None
    output_draft_chars: int = 0
    wechat_variant_id: str = ""
    wechat_variant_version: int | None = None
    wechat_variant_status: str = ""
    created_at: datetime
    updated_at: datetime
    artifacts: list[WritingArtifactOut] = Field(default_factory=list)
    runs: list[AgentRunOut] = Field(default_factory=list)
    memory_snapshot: dict[str, Any] = Field(default_factory=dict)


class ArtifactApprovalRequest(BaseModel):
    approved: bool = True
    note: str = Field(default="", max_length=2000)


class WritingFeedbackCreate(BaseModel):
    draft_before_id: str | None = None
    draft_after_id: str | None = None
    diff: dict[str, Any] = Field(default_factory=dict)
    feedback_reason: str = Field(default="", max_length=4000)
    affected_rules: list[str] = Field(default_factory=list)


class WritingRunRequest(BaseModel):
    continuous: bool = True

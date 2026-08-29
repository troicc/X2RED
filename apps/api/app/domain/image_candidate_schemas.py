from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


CandidateOrigin = Literal[
    "api_generation",
    "manual_upload",
    "image_edit",
    "directed_regeneration",
]
CandidateStatus = Literal[
    "pending_review",
    "eligible",
    "kept",
    "rejected",
    "selected",
    "repair_failed",
]
ReviewDecision = Literal[
    "automatic_pass",
    "automatic_fail",
    "human_approved",
    "human_rejected",
]
PromptRunOperation = Literal[
    "generation",
    "manual_upload",
    "image_edit",
    "directed_regeneration",
]


class ProviderCapabilities(BaseModel):
    """Conservative capability snapshot frozen with every prompt run."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=160)
    candidate_count: bool = False
    max_candidate_count: int = Field(default=1, ge=1, le=4)
    image_reference: bool = False
    image_edit: bool = False
    multi_turn: bool = False
    usage: bool = False
    detection_mode: Literal["known-provider", "conservative-default", "runtime-fallback"]


class VisualCriticScores(BaseModel):
    """Ten review dimensions. Good dimensions are high; risk dimensions are low."""

    model_config = ConfigDict(extra="forbid")

    semantic_match: float = Field(ge=0, le=100)
    subject_clarity: float = Field(ge=0, le=100)
    composition: float = Field(ge=0, le=100)
    thumbnail_hook: float = Field(ge=0, le=100)
    series_consistency: float = Field(ge=0, le=100)
    texture: float = Field(ge=0, le=100)
    color_anchor: float = Field(ge=0, le=100)
    artifacts: float = Field(ge=0, le=100)
    text_safety: float = Field(ge=0, le=100)
    cliche_score: float = Field(ge=0, le=100)


class ImageCandidateReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scores: VisualCriticScores
    overall_score: float = Field(ge=0, le=100)
    passed: bool
    decision: ReviewDecision
    issues: list[str] = Field(default_factory=list, max_length=12)
    primary_defect: str = Field(default="", max_length=80)
    repair_instruction: str = Field(default="", max_length=360)
    reviewer_note: str = Field(default="", max_length=600)
    critic_version: str = Field(default="x2red-image-critic-v1", max_length=80)
    reviewed_at: str = Field(default_factory=utc_timestamp)


class ImageCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^imgcand_[a-f0-9]{24}$")
    page: int = Field(ge=1, le=6)
    candidate_index: int = Field(ge=1)
    prompt_run_id: str = Field(pattern=r"^imgrun_[a-f0-9]{24}$")
    origin: CandidateOrigin
    parent_candidate_id: str = ""
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=160)
    artifact_key: str = Field(pattern=r"^candidate_[0-9]{2}_[a-f0-9]{24}$")
    image_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    width: int = Field(ge=240, le=10_000)
    height: int = Field(ge=240, le=10_000)
    cost_usd: float | None = Field(default=None, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    status: CandidateStatus = "pending_review"
    review: ImageCandidateReview
    rejection_reason: str = Field(default="", max_length=600)
    repair_attempt: int = Field(default=0, ge=0, le=1)
    created_at: str = Field(default_factory=utc_timestamp)


class ImagePromptRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_run_id: str = Field(pattern=r"^imgrun_[a-f0-9]{24}$")
    page: int = Field(ge=1, le=6)
    operation: PromptRunOperation
    prompt: str = Field(min_length=1, max_length=20_000)
    prompt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=160)
    requested_count: int = Field(ge=1, le=4)
    actual_count: int = Field(ge=1, le=4)
    request_strategy: Literal["single-call", "sequential", "manual-upload", "edit"]
    call_count: int = Field(ge=0, le=5)
    capabilities: ProviderCapabilities
    reference_candidate_id: str = ""
    invariants: list[str] = Field(default_factory=list, max_length=12)
    primary_defect: str = Field(default="", max_length=80)
    usage: dict[str, Any] = Field(default_factory=dict)
    cost_usd: float | None = Field(default=None, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    created_at: str = Field(default_factory=utc_timestamp)


class CandidateAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal[
        "candidates_added",
        "candidate_selected",
        "candidate_kept",
        "candidate_rejected",
        "candidate_approved",
        "candidate_invalidated",
        "repair_started",
        "repair_completed",
        "repair_exhausted",
    ]
    page: int = Field(ge=1, le=6)
    candidate_id: str = ""
    detail: str = Field(default="", max_length=600)
    at: str = Field(default_factory=utc_timestamp)


class CandidatePageState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1, le=6)
    prompt_runs: list[ImagePromptRun] = Field(default_factory=list)
    candidates: list[ImageCandidate] = Field(default_factory=list)
    selected_candidate_id: str = ""
    contact_sheet_key: str = ""
    auto_repair_count: int = Field(default=0, ge=0, le=1)
    generation_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def selected_candidate_must_exist(self) -> CandidatePageState:
        if self.selected_candidate_id and self.selected_candidate_id not in {
            item.candidate_id for item in self.candidates
        }:
            raise ValueError("selected_candidate_id 必须指向当前页已有候选")
        return self


class ImageCandidateLifecycle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["image-candidates-v1"] = "image-candidates-v1"
    mode: Literal["production"] = "production"
    pages: dict[str, CandidatePageState] = Field(default_factory=dict)
    audit_events: list[CandidateAuditEvent] = Field(default_factory=list)
    total_api_calls: int = Field(default=0, ge=0)
    total_cost_usd: float | None = Field(default=None, ge=0)
    updated_at: str = Field(default_factory=utc_timestamp)

    @model_validator(mode="after")
    def page_keys_match_payload(self) -> ImageCandidateLifecycle:
        for key, value in self.pages.items():
            if key != str(value.page):
                raise ValueError("候选页键必须与 page 一致")
        return self

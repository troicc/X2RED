from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MemorySourceKind = Literal[
    "authorized_sample",
    "approved_output",
    "writing_feedback",
    "pattern_card",
    "manual_rule",
    "visual_reference",
    "negative_example",
    "positive_example",
    "draft_revision",
    "platform_variant",
    "writing_artifact",
    "review_artifact",
]
MemoryDimension = Literal[
    "identity",
    "reader_relationship",
    "tone",
    "sentence_rhythm",
    "paragraph_rhythm",
    "opening",
    "title",
    "structure",
    "transition",
    "judgment",
    "ending",
    "forbidden_expression",
    "positive_phrase",
    "visual_direction",
    "layout_preference",
]
MemoryUsagePolicy = Literal[
    "style_and_structure_only",
    "abstract_pattern_only",
    "visual_only",
]


class PoolMemoryScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platforms: list[str] = Field(default_factory=list, max_length=12)
    formats: list[str] = Field(default_factory=list, max_length=12)
    article_types: list[str] = Field(default_factory=list, max_length=20)
    style_profile_ids: list[str] = Field(default_factory=list, max_length=20)
    topics: list[str] = Field(default_factory=list, max_length=30)
    audiences: list[str] = Field(default_factory=list, max_length=20)
    recipes: list[str] = Field(default_factory=list, max_length=20)
    visual_routes: list[str] = Field(default_factory=list, max_length=20)

    @field_validator(
        "platforms",
        "formats",
        "article_types",
        "style_profile_ids",
        "topics",
        "audiences",
        "recipes",
        "visual_routes",
    )
    @classmethod
    def clean_values(cls, values: list[str]) -> list[str]:
        output: list[str] = []
        for raw in values:
            value = " ".join(str(raw).split())[:120]
            if value and value not in output:
                output.append(value)
        return output


class PoolMemoryExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=120)
    lesson: str = Field(default="", max_length=240)
    rhetorical_duty: Literal[
        "opening",
        "title",
        "transition",
        "judgment",
        "ending",
        "sentence_rhythm",
        "paragraph_rhythm",
        "positive_phrase",
    ] = "positive_phrase"


class PoolMemoryContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: list[str] = Field(default_factory=list, max_length=30)
    avoid: list[str] = Field(default_factory=list, max_length=30)
    prefer: list[str] = Field(default_factory=list, max_length=30)
    positive_examples: list[PoolMemoryExample] = Field(default_factory=list, max_length=12)
    structure: list[str] = Field(default_factory=list, max_length=20)
    visual_directions: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("rules", "avoid", "prefer", "structure", "visual_directions")
    @classmethod
    def clean_lines(cls, values: list[str]) -> list[str]:
        output: list[str] = []
        for raw in values:
            value = " ".join(str(raw).split())[:300]
            if value and value not in output:
                output.append(value)
        return output

    @model_validator(mode="after")
    def require_content(self) -> PoolMemoryContent:
        if not any(
            (
                self.rules,
                self.avoid,
                self.prefer,
                self.positive_examples,
                self.structure,
                self.visual_directions,
            )
        ):
            raise ValueError("记忆内容不能全部为空")
        return self


class PoolMemoryCandidateCreate(BaseModel):
    source_kind: MemorySourceKind
    source_id: str = Field(min_length=1, max_length=64)
    title: str = Field(default="", max_length=160)
    dimensions: list[MemoryDimension] = Field(min_length=1, max_length=15)
    scope: PoolMemoryScope = Field(default_factory=PoolMemoryScope)
    usage_policy: MemoryUsagePolicy = "style_and_structure_only"
    note: str = Field(default="", max_length=3000)


class PoolMemoryTargetCandidateRequest(BaseModel):
    title: str = Field(default="", max_length=160)
    dimensions: list[MemoryDimension] = Field(min_length=1, max_length=15)
    scope: PoolMemoryScope = Field(default_factory=PoolMemoryScope)
    usage_policy: MemoryUsagePolicy = "style_and_structure_only"
    note: str = Field(default="", max_length=3000)


class PoolMemoryCandidateUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    dimensions: list[MemoryDimension] = Field(min_length=1, max_length=15)
    scope: PoolMemoryScope = Field(default_factory=PoolMemoryScope)
    memory: PoolMemoryContent
    usage_policy: MemoryUsagePolicy = "style_and_structure_only"
    note: str = Field(default="", max_length=3000)


class PoolMemoryApproveRequest(BaseModel):
    review_note: str = Field(default="", max_length=3000)
    confirm_source_authorized: bool = False


class PoolMemoryManualCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    dimensions: list[MemoryDimension] = Field(min_length=1, max_length=15)
    scope: PoolMemoryScope = Field(default_factory=PoolMemoryScope)
    memory: PoolMemoryContent
    usage_policy: MemoryUsagePolicy = "style_and_structure_only"
    note: str = Field(default="", max_length=3000)
    confirm_original_or_authorized: bool = False


class PoolMemorySupersedeRequest(PoolMemoryCandidateUpdate):
    reason: str = Field(min_length=1, max_length=3000)


class PoolMemoryRevokeRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=3000)


class PoolMemoryRetrieveRequest(BaseModel):
    platform: str = Field(default="", max_length=40)
    format: str = Field(default="", max_length=40)
    article_type: str = Field(default="", max_length=80)
    style_profile_id: str = Field(default="", max_length=64)
    topics: list[str] = Field(default_factory=list, max_length=30)
    audience: str = Field(default="", max_length=500)
    recipe: str = Field(default="", max_length=80)
    visual_route: str = Field(default="", max_length=80)
    source_text: str = Field(default="", max_length=30000)
    dimensions: list[MemoryDimension] = Field(default_factory=list, max_length=15)
    limit: int = Field(default=6, ge=1, le=8)
    max_chars: int = Field(default=6000, ge=1000, le=7000)


class PoolMemoryArtifactOut(BaseModel):
    id: str
    state: str
    title: str
    source: dict[str, Any]
    dimensions: list[str]
    scope: dict[str, list[str]]
    memory: dict[str, Any]
    usage_policy: str
    created_by: str
    created_at: datetime
    approved_at: datetime | None
    extraction_mode: str = ""
    eligibility: dict[str, Any] = Field(default_factory=dict)
    legacy: bool = False
    superseded: bool = False
    revoked: bool = False
    usage_count: int = 0
    recent_targets: list[dict[str, Any]] = Field(default_factory=list)


class PoolMemoryCandidateOut(PoolMemoryArtifactOut):
    parent_id: str = ""
    note: str = ""


class PoolMemoryRetrieveItem(BaseModel):
    item: PoolMemoryArtifactOut
    score: float
    reasons: list[str]


class PoolMemoryRetrievePreview(BaseModel):
    query: dict[str, Any]
    items: list[PoolMemoryRetrieveItem]
    memory_ids: list[str]
    prompt_preview: str
    fact_boundary: str


class PoolMemorySnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_type: str
    target_id: str
    query_json: str
    memory_ids_json: str
    prompt_payload_json: str
    snapshot_hash: str
    model_configured: bool
    applied: bool
    model_name: str
    created_at: datetime


class PoolMemoryUsageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    memory_id: str
    snapshot_id: str
    target_type: str
    target_id: str
    agent_role: str
    stage: str
    selected_reason: str
    score: float
    created_at: datetime


class PoolMemorySourceOption(BaseModel):
    kind: str
    id: str
    label: str
    detail: str = ""
    platform: str = ""
    format: str = ""
    eligible: bool = False
    eligibility_reason: str = ""

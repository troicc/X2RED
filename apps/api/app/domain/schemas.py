from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RightsStatusValue = Literal[
    "owned",
    "licensed",
    "open_license",
    "limited_quote",
    "needs_review",
    "do_not_publish",
]
WorkspaceStateValue = Literal["active", "archived"]


class IntakeRequest(BaseModel):
    url: str
    mode: Literal["thread", "conversation"] = "thread"
    download_media: bool | None = None


class IntakeResponse(BaseModel):
    source_id: str
    external_id: str
    imported_count: int
    asset_count: int
    snapshot_id: str


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    state: str
    payload_json: str
    result_json: str
    error: str
    attempts: int
    max_attempts: int
    priority: int
    dedupe_key: str
    available_at: datetime
    locked_by: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    role: str
    remote_url: str
    local_path: str
    mime_type: str
    width: int
    height: int
    alt_text: str
    state: str
    error: str
    rights_status: str
    rights_note: str


class SourceListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    platform: str
    external_id: str
    canonical_url: str
    author_handle: str
    author_name: str
    author_avatar_url: str
    text_original: str
    content_kind: str
    workspace_state: str
    workbench_state: WorkspaceStateValue = "active"
    created_at: datetime | None
    captured_at: datetime
    archived_at: datetime | None
    last_published_at: datetime | None
    published_count: int
    state: str
    rights_status: str
    rights_note: str


class SourceDetail(SourceListItem):
    structured_content_json: str
    editor_note: str
    metrics_json: str
    assets: list[AssetOut] = Field(default_factory=list)
    related: list[SourceListItem] = Field(default_factory=list)


class ManualSourceCreateRequest(BaseModel):
    title: str = Field(default="", max_length=200)
    author_name: str = Field(default="", max_length=160)
    canonical_url: str = Field(default="", max_length=2000)
    text_original: str = Field(min_length=20, max_length=200000)


class SourceNoteUpdateRequest(BaseModel):
    editor_note: str = Field(default="", max_length=6000)


class RightsUpdateRequest(BaseModel):
    source_status: RightsStatusValue
    source_note: str = Field(default="", max_length=2000)
    asset_status: RightsStatusValue | None = None
    asset_note: str = Field(default="", max_length=2000)
    apply_to_related: bool = True


class X2PDFImportRequest(BaseModel):
    document: dict[str, Any]


class X2PDFImportResponse(BaseModel):
    source_id: str
    external_id: str
    content_kind: str
    block_count: int
    asset_count: int
    updated: bool


class SkillBindingOut(BaseModel):
    skill_name: str
    label: str
    category: str
    description: str
    enabled: bool
    model_name: str
    reasoning_effort: str
    prompt_version: str


class SkillBindingUpdate(BaseModel):
    enabled: bool
    model_name: str = Field(default="", max_length=120)
    reasoning_effort: Literal["low", "medium", "high"] = "medium"
    prompt_version: str = Field(default="v1", max_length=40)


class DraftGenerateRequest(BaseModel):
    style: Literal["news", "explain", "opinion"] = "explain"


class DraftUpdateRequest(BaseModel):
    title: str = Field(max_length=80)
    body: str = Field(max_length=4000)
    tags: str = Field(default="", max_length=500)


class DraftTransformRequest(BaseModel):
    action: Literal["de_translate", "stronger_insight", "concise", "rewrite_title"]
    instruction: str = Field(default="", max_length=500)


class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    version: int
    style: str
    title: str
    body: str
    tags: str
    claims_json: str
    provenance_json: str
    created_by: str
    created_at: datetime


class CardGenerateRequest(BaseModel):
    template: Literal[
        "editorial_minimal",
        "tech_minimal",
        "clean_news",
        "warm_note",
        "warm_editorial",
        "dark_tech",
    ] = "editorial_minimal"
    visual_style: Literal[
        "auto",
        "editorial",
        "swiss",
        "guizang_editorial",
        "guizang_swiss",
        "knowledge",
        "poster",
        "notebook",
        "bold",
        "minimal",
    ] = "auto"
    layout: Literal[
        "auto",
        "sparse",
        "balanced",
        "dense",
        "list",
        "comparison",
        "flow",
        "quadrant",
    ] = "auto"
    palette: Literal[
        "auto",
        "neutral",
        "macaron",
        "warm",
        "neon",
        "monochrome",
    ] = "auto"
    material_strategy: Literal["auto", "source_first", "text_only"] = "auto"
    max_cards: int = Field(default=6, ge=2, le=9)


class CardRenderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    draft_id: str
    template: str
    spec_json: str
    output_paths_json: str
    status: str
    error: str
    created_at: datetime


class ReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str = Field(default="", max_length=1000)
    facts_checked: bool = False
    rights_checked: bool = False


class PublishPrepareRequest(BaseModel):
    include_cards: bool = True
    include_source_assets: bool = False


class PublishResultRequest(BaseModel):
    result_url: str = Field(min_length=1, max_length=2000)


class PublishTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    draft_id: str
    state: str
    title: str
    body: str
    tags: str
    package_path: str
    result_url: str
    error: str


class CorpusPoolCreateRequest(BaseModel):
    source_ids: list[str] = Field(min_length=1, max_length=500)
    name: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=4000)
    batch_size: int = Field(default=6, ge=1, le=12)


class CorpusPoolUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    batch_size: int | None = Field(default=None, ge=1, le=12)
    state: Literal["active", "archived"] | None = None
    unlock_name: bool = False


class CorpusPoolSourcesRequest(BaseModel):
    source_ids: list[str] = Field(min_length=1, max_length=500)


class CorpusPoolBatchRequest(BaseModel):
    batch_size: int | None = Field(default=None, ge=1, le=12)
    focus: str = Field(default="", max_length=500)


class CorpusPoolGenerateRequest(CorpusPoolBatchRequest):
    style: Literal["news", "explain", "opinion"] = "explain"


class CorpusPoolOut(BaseModel):
    id: str
    name: str
    name_locked: bool
    description: str
    state: str
    batch_size: int
    topic_keywords: list[str] = Field(default_factory=list)
    profile_text: str
    source_count: int
    total_chars: int
    revision: int
    created_at: datetime
    updated_at: datetime
    last_compiled_at: datetime | None


class CorpusPoolMemberOut(BaseModel):
    id: str
    pool_id: str
    source_id: str
    summary: str
    keywords: list[str] = Field(default_factory=list)
    used_count: int
    last_used_at: datetime | None
    added_at: datetime
    source: SourceListItem


class CorpusBatchOut(BaseModel):
    id: str
    pool_id: str
    sequence: int
    focus: str
    source_ids: list[str] = Field(default_factory=list)
    sources: list[SourceListItem] = Field(default_factory=list)
    source_fingerprint: str
    profile_revision: int
    anchor_source_id: str | None
    draft_id: str
    created_at: datetime | None
    draft: DraftOut | None = None


class CorpusPoolDetail(CorpusPoolOut):
    members: list[CorpusPoolMemberOut] = Field(default_factory=list)
    batches: list[CorpusBatchOut] = Field(default_factory=list)


class CorpusPoolDraftResult(BaseModel):
    pool: CorpusPoolOut
    batch: CorpusBatchOut
    draft: DraftOut

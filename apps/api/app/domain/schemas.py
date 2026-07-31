from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RightsStatusValue = Literal[
    "owned",
    "licensed",
    "open_license",
    "limited_quote",
    "needs_review",
    "do_not_publish",
]


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
    external_id: str
    canonical_url: str
    author_handle: str
    author_name: str
    text_original: str
    created_at: datetime | None
    captured_at: datetime
    state: str
    rights_status: str
    rights_note: str


class SourceDetail(SourceListItem):
    assets: list[AssetOut] = Field(default_factory=list)
    related: list[SourceListItem] = Field(default_factory=list)


class RightsUpdateRequest(BaseModel):
    source_status: RightsStatusValue
    source_note: str = Field(default="", max_length=2000)
    asset_status: RightsStatusValue | None = None
    asset_note: str = Field(default="", max_length=2000)
    apply_to_related: bool = True


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
    template: Literal["warm_editorial", "dark_tech", "clean_news"] = "warm_editorial"
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

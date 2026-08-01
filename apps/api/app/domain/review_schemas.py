from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ReviewArtifactType = Literal[
    "xhs_storyboard",
    "wechat_module_tree",
    "wechat_cover_brief",
]
ReviewScopeType = Literal["draft", "platform_variant"]
ReviewDecisionValue = Literal["approved", "changes_requested"]


class ReviewArtifactCreate(BaseModel):
    artifact_type: ReviewArtifactType
    scope_type: ReviewScopeType
    scope_id: str = Field(min_length=1, max_length=64)


class ReviewArtifactUpdate(BaseModel):
    payload: dict[str, Any]
    note: str = Field(default="", max_length=3000)


class ReviewArtifactDecision(BaseModel):
    decision: ReviewDecisionValue
    note: str = Field(default="", max_length=3000)


class ReviewArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scope_type: str
    scope_id: str
    artifact_type: str
    version: int
    parent_id: str
    payload_json: str
    state: str
    review_note: str
    created_by: str
    applied_to_id: str
    error: str
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StoryboardRenderRequest(BaseModel):
    template: Literal[
        "editorial_minimal",
        "tech_minimal",
        "clean_news",
        "warm_note",
    ] = "tech_minimal"
    preview: bool = False


class StoryboardRenderResult(BaseModel):
    artifact: ReviewArtifactOut
    card_render_id: str
    output_count: int


class ReviewApplyResult(BaseModel):
    artifact: ReviewArtifactOut
    applied_to_id: str


class WeChatPublisherPayload(BaseModel):
    variant_id: str
    title: str
    author: str
    body_html: str
    summary: str
    cover_wide_url: str
    cover_square_url: str
    validation_warnings: list[str]

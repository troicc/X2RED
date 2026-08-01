from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


WechatTheme = Literal[
    "auto",
    "editorial_blue",
    "vermillion",
    "graphite",
    "zen",
    "receipt",
    "olive",
]
LightContentRecipe = Literal[
    "comfort",
    "mature_life",
    "seasonal",
    "photo_quote",
    "short_commentary",
]


class WeChatVariantCreate(BaseModel):
    source_id: str
    draft_id: str | None = None
    theme: WechatTheme = "auto"
    mode: Literal["adapt", "preserve"] = "adapt"
    include_citations: bool = True
    include_illustration_plan: bool = True
    author: str = Field(default="", max_length=80)


class LightContentVariantCreate(BaseModel):
    source_id: str
    draft_id: str | None = None
    recipe: LightContentRecipe = "comfort"
    image_count: int = Field(default=4, ge=3, le=6)
    seasonal_topic: str = Field(default="", max_length=120)
    audience: str = Field(default="", max_length=500)
    tone: str = Field(default="安静、克制、有生活感", max_length=300)
    theme: WechatTheme = "zen"
    author: str = Field(default="", max_length=80)


class PlatformVariantUpdate(BaseModel):
    title: str = Field(max_length=160)
    subtitle: str = Field(default="", max_length=240)
    summary: str = Field(default="", max_length=1000)
    body_markdown: str = Field(max_length=50000)
    tags: str = Field(default="", max_length=1000)
    theme: WechatTheme = "auto"


class PlatformRenderRequest(BaseModel):
    package: bool = True


class PlatformVariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    base_draft_id: str | None
    platform: str
    format: str
    version: int
    title: str
    subtitle: str
    summary: str
    body_markdown: str
    body_html: str
    tags: str
    theme: str
    skill_profile_json: str
    metadata_json: str
    output_paths_json: str
    status: str
    error: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class SkillPackOut(BaseModel):
    id: str
    label: str
    platform: str
    description: str
    source_repositories: list[str]
    licenses: list[str]
    integration_mode: str
    skills: list[str]
    enabled: bool
    installed_paths: list[str]
    notes: str


class SkillPackUpdate(BaseModel):
    enabled: bool


class WeChatThemeOut(BaseModel):
    id: str
    label: str
    description: str
    suitable_for: list[str]
    palette: dict[str, str]


class WeChatRenderResult(BaseModel):
    variant: PlatformVariantOut
    validation: dict[str, list[str]]
    files: dict[str, str]
    preview_url: str
    download_urls: dict[str, str]


class PlatformCatalogOut(BaseModel):
    skill_packs: list[SkillPackOut]
    wechat_themes: list[WeChatThemeOut]
    platform_capabilities: dict[str, Any]

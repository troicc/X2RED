from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
LightVisualStyle = Literal[
    "auto",
    "minimal_zine",
    "photo_editorial",
    "classical_ink",
    "dark_contemplative",
    "seasonal_folk",
    "old_newspaper",
]
LightQualityMode = Literal["fast", "studio"]
MinimalZineLayout = Literal[
    "center-fragment",
    "lower-left-float",
    "upper-right-block",
    "dual-panel",
    "irregular-cutout",
    "type-led",
    "dot-orbit",
    "single-specimen",
]
MinimalZineAnchor = Literal[
    "tiny-faded-photo",
    "torn-paper-clipping",
    "flat-silhouette",
    "solid-color-block",
    "old-printed-illustration",
    "object-specimen",
    "translucent-geometric-overlay",
    "abstract-texture-window",
]
MinimalZineTexture = Literal[
    "xerox-softness",
    "risograph-grain",
    "letterpress-ink-bleed",
    "halftone-degradation",
    "film-grain-photo",
    "scan-noise-paper-fibers",
    "aged-paper-mottling",
    "soft-motion-blur",
]


class MinimalZineStoryboardPage(BaseModel):
    """A full, user-controlled page contract for an immutable storyboard revision."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    page: int = Field(ge=1, le=6)
    phrase: str = Field(min_length=1, max_length=80)
    note: str = Field(max_length=180)
    visual_metaphor: str = Field(min_length=1, max_length=240)
    layout: MinimalZineLayout
    anchor: MinimalZineAnchor
    accent: str = Field(min_length=1, max_length=32)
    texture: MinimalZineTexture
    mood: str = Field(min_length=1, max_length=80)
    focus_x: float = Field(ge=0.0, le=1.0)
    focus_y: float = Field(ge=0.0, le=1.0)
    zoom: float = Field(ge=0.65, le=2.0)

    @field_validator("phrase", "note", "visual_metaphor", "mood")
    @classmethod
    def clean_storyboard_text(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("accent")
    @classmethod
    def validate_accent(cls, value: str) -> str:
        cleaned = value.strip().lower().replace("_", "-").replace(" ", "-")
        names = {
            "blue",
            "cobalt",
            "ultramarine",
            "cyan",
            "violet",
            "magenta",
            "magenta-pink",
            "yellow",
            "lemon-yellow",
            "green",
            "pear-green",
            "orange",
            "red",
            "tomato-red",
            "vermilion",
        }
        if cleaned in names or (
            len(cleaned) == 7
            and cleaned.startswith("#")
            and all(char in "0123456789abcdef" for char in cleaned[1:])
        ):
            return cleaned
        raise ValueError("accent 必须是支持的强调色名称或 #RRGGBB")


class MinimalZineStoryboardRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages: list[MinimalZineStoryboardPage] = Field(min_length=3, max_length=6)

    @model_validator(mode="after")
    def unique_pages(self) -> MinimalZineStoryboardRevisionRequest:
        page_numbers = [page.page for page in self.pages]
        if len(set(page_numbers)) != len(page_numbers):
            raise ValueError("故事板页码不能重复")
        return self


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
    tone: str = Field(default="自然、具体、克制", max_length=300)
    theme: WechatTheme = "zen"
    author: str = Field(default="", max_length=80)
    visual_style: LightVisualStyle = "auto"
    quality_mode: LightQualityMode = "studio"
    feedback: str = Field(default="", max_length=3000)


class LightContentIterateRequest(BaseModel):
    feedback: str = Field(min_length=1, max_length=3000)
    quality_mode: LightQualityMode = "studio"


class LightContentCandidateSelect(BaseModel):
    candidate_index: int = Field(ge=0, le=2)


class LightContentApproval(BaseModel):
    note: str = Field(default="", max_length=3000)


class LightCorpusCreate(BaseModel):
    recipe: LightContentRecipe
    title: str = Field(default="", max_length=160)
    body_markdown: str = Field(default="", max_length=8000)
    visual_style: LightVisualStyle = "auto"
    note: str = Field(default="", max_length=3000)


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

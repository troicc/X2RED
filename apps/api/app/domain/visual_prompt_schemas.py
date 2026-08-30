from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.visual_brief_schemas import PageVisualBrief

VisualPromptMode = Literal["faithful_skill", "production_text_safe", "legacy"]
VisualPromptFeatureMode = Literal["legacy", "skill_v03", "production"]

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class StrictVisualPromptModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VisualPromptRecipe(StrictVisualPromptModel):
    layout_family: str = Field(min_length=2, max_length=120)
    anchor_form: str = Field(min_length=2, max_length=160)
    typography_mode: str = Field(min_length=2, max_length=120)
    texture_mode: str = Field(min_length=2, max_length=160)
    decorative_system: list[str] = Field(default_factory=list, max_length=12)
    main_hue: str = Field(min_length=1, max_length=80)
    mood: str = Field(min_length=1, max_length=160)

    @field_validator("decorative_system")
    @classmethod
    def clean_decorative_system(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            item = " ".join(str(value).split())[:160]
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned


class VisualPromptContext(StrictVisualPromptModel):
    """All semantic inputs that may change a page-level visual prompt."""

    variant_id: str = Field(default="", max_length=120)
    page: int = Field(ge=1, le=12)
    total_pages: int = Field(ge=1, le=12)
    article_thesis: str = Field(min_length=1, max_length=1200)
    section_title: str = Field(min_length=1, max_length=300)
    page_visual_role: str = Field(min_length=1, max_length=100)
    phrase: str = Field(default="", max_length=160)
    note: str = Field(default="", max_length=500)
    evidence_summary: str = Field(default="", max_length=1600)
    audience: str = Field(default="", max_length=500)
    emotion: str = Field(default="", max_length=300)
    current_page_concept: str = Field(min_length=1, max_length=800)
    visual_bible: dict[str, Any] = Field(default_factory=dict)
    page_visual_brief: PageVisualBrief | None = None
    previous_page_concept: str = Field(default="", max_length=800)
    next_page_concept: str = Field(default="", max_length=800)
    content_recipe: str = Field(default="", max_length=100)
    source_fit: str = Field(default="", max_length=800)
    layout_hint: str = Field(default="", max_length=120)
    anchor_hint: str = Field(default="", max_length=160)
    texture_hint: str = Field(default="", max_length=160)
    main_hue_hint: str = Field(default="", max_length=80)
    mood_hint: str = Field(default="", max_length=160)


class VisualPromptSpec(StrictVisualPromptModel):
    schema_version: Literal[1] = 1
    skill_name: str = Field(min_length=3, max_length=160)
    skill_version: str = Field(min_length=1, max_length=80)
    compiler_version: str = Field(min_length=3, max_length=120)
    mode: VisualPromptMode
    positive_prompt: str = Field(min_length=40, max_length=12_000)
    invariants: list[str] = Field(default_factory=list, max_length=24)
    exclusions: list[str] = Field(default_factory=list, max_length=24)
    recipe: VisualPromptRecipe
    source_fingerprint: str = Field(pattern=SHA256_PATTERN)
    prompt_fingerprint: str = Field(pattern=SHA256_PATTERN)
    warnings: list[str] = Field(default_factory=list, max_length=24)

    @field_validator("invariants", "exclusions", "warnings")
    @classmethod
    def clean_string_lists(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            item = " ".join(str(value).split())[:500]
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned

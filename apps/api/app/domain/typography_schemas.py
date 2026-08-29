from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TypographyMode = Literal[
    "type_led_large",
    "edge_pressed_phrase",
    "diagonal_fragments",
    "ghost_text",
    "archive_microtype",
    "type_in_color_block",
    "margin_scatter",
    "safe_zone_caption",
]
TextRole = Literal["title", "caption", "fragment", "ghost", "microtype", "folio"]
TextSource = Literal[
    "phrase",
    "phrase_head",
    "phrase_tail",
    "note",
    "folio",
    "label",
]
FontRole = Literal["sans_display", "serif_editorial", "mono_archive"]
TextAlignment = Literal["left", "center", "right"]
BlendMode = Literal["normal", "multiply", "screen"]
CollisionPolicy = Literal["avoid_subject", "soft_underlay", "safe_zone"]
BackgroundRole = Literal["none", "paper_veil", "ink_block", "accent_block"]


class StrictTypographyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TextRegion(StrictTypographyModel):
    """One normalized local-type region, independent of output aspect ratio."""

    region_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,47}$")
    role: TextRole
    source: TextSource
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)
    size_scale: float = Field(default=1.0, ge=0.2, le=2.0)
    max_lines: int = Field(default=4, ge=1, le=12)
    rotation: float | None = Field(default=None, ge=-28.0, le=28.0)
    alignment: TextAlignment | None = None
    opacity: float | None = Field(default=None, ge=0.05, le=1.0)
    background_role: BackgroundRole = "none"
    inset_ratio: float = Field(default=0.025, ge=0.0, le=0.12)

    @model_validator(mode="after")
    def region_fits_normalized_canvas(self) -> TextRegion:
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("文字区域必须完整位于归一化画布内")
        return self


class TypographyRecipe(StrictTypographyModel):
    """Frozen local-Chinese typography recipe v2."""

    schema_version: Literal["typography-recipe-v2"] = "typography-recipe-v2"
    mode: TypographyMode
    text_regions: list[TextRegion] = Field(min_length=1, max_length=8)
    font_role: FontRole
    weight: int = Field(ge=300, le=900)
    size_ratio: float = Field(gt=0.01, le=0.24)
    line_height: float = Field(ge=0.82, le=1.8)
    tracking: float = Field(ge=-0.08, le=0.28)
    rotation: float = Field(ge=-28.0, le=28.0)
    alignment: TextAlignment
    opacity: float = Field(ge=0.05, le=1.0)
    blend_mode: BlendMode
    collision_policy: CollisionPolicy
    source_fingerprint: str = Field(default="", pattern=r"^$|^[0-9a-f]{64}$")
    selection_reason: str = Field(default="", max_length=240)
    fallback_from: str = Field(default="", max_length=80)
    transform: Literal["identity", "mirror_x", "mirror_y", "mirror_xy"] = "identity"

    @model_validator(mode="after")
    def region_ids_are_unique(self) -> TypographyRecipe:
        identifiers = [region.region_id for region in self.text_regions]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("同一排版配方中的文字区域 ID 必须唯一")
        return self


class TypographyRegionDiagnostic(StrictTypographyModel):
    region_id: str
    role: TextRole
    source: TextSource
    box: tuple[int, int, int, int]
    rendered_box: tuple[int, int, int, int] | None = None
    font_size: int = Field(ge=0)
    lines: list[str] = Field(default_factory=list, max_length=12)
    rotation: float = Field(ge=-28.0, le=28.0)
    opacity: float = Field(ge=0.0, le=1.0)
    overlaps_subject: bool = False
    clipped: bool = False


class TypographyRenderDiagnostic(StrictTypographyModel):
    schema_version: Literal["typography-render-v2"] = "typography-render-v2"
    mode: TypographyMode
    font_role: FontRole
    canvas_ratio: str
    transform: Literal["identity", "mirror_x", "mirror_y", "mirror_xy"]
    selection_reason: str = ""
    fallback_from: str = ""
    collision_policy: CollisionPolicy
    protected_regions: list[tuple[int, int, int, int]] = Field(default_factory=list)
    regions: list[TypographyRegionDiagnostic] = Field(default_factory=list)
    no_overflow: bool = True
    subject_clear: bool = True
    visible_text_region_count: int = Field(default=0, ge=0)
    source_fingerprint: str = Field(default="", pattern=r"^$|^[0-9a-f]{64}$")

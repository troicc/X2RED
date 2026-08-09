from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VisualRole = Literal[
    "cover",
    "scene",
    "explanation",
    "evidence",
    "comparison",
    "process",
    "limitation",
    "transition",
    "conclusion",
]

VisualBriefMode = Literal["production", "deterministic", "legacy"]


class StrictVisualBriefModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VisualBible(StrictVisualBriefModel):
    """Article-level visual invariants, never page-level subject matter."""

    identity: str = Field(min_length=4, max_length=240)
    paper_system: str = Field(min_length=4, max_length=300)
    palette: list[str] = Field(min_length=2, max_length=8)
    accent_policy: str = Field(min_length=4, max_length=300)
    print_process: list[str] = Field(min_length=1, max_length=8)
    typography_modes: list[str] = Field(min_length=1, max_length=8)
    photographic_treatment: str = Field(min_length=4, max_length=300)
    illustration_treatment: str = Field(min_length=4, max_length=300)
    layout_distribution: list[str] = Field(min_length=3, max_length=12)
    recurring_motif_policy: str = Field(min_length=4, max_length=400)
    prohibited_cliches: list[str] = Field(default_factory=list, max_length=24)
    invariants: list[str] = Field(min_length=1, max_length=24)

    @field_validator(
        "palette",
        "print_process",
        "typography_modes",
        "layout_distribution",
        "prohibited_cliches",
        "invariants",
    )
    @classmethod
    def clean_unique_lists(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            item = " ".join(str(value).split())[:240]
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned


class PageVisualBrief(StrictVisualBriefModel):
    """Frozen page-level visual authority consumed by the Prompt compiler."""

    page: int = Field(ge=1, le=12)
    section_id: str = Field(min_length=1, max_length=120)
    visual_role: VisualRole
    claim: str = Field(min_length=2, max_length=600)
    reader_emotion: str = Field(min_length=1, max_length=160)
    concrete_subject: str = Field(min_length=2, max_length=240)
    secondary_subject: str = Field(default="", max_length=240)
    action_or_relation: str = Field(min_length=2, max_length=320)
    setting: str = Field(min_length=2, max_length=240)
    viewpoint: str = Field(min_length=2, max_length=160)
    crop: str = Field(min_length=2, max_length=160)
    lighting: str = Field(min_length=2, max_length=160)
    materials: list[str] = Field(min_length=1, max_length=12)
    layout_family: str = Field(min_length=2, max_length=120)
    typography_mode: str = Field(min_length=2, max_length=120)
    palette_delta: list[str] = Field(min_length=1, max_length=6)
    must_preserve: list[str] = Field(min_length=1, max_length=24)
    must_avoid: list[str] = Field(default_factory=list, max_length=24)
    evidence_refs: list[str] = Field(min_length=1, max_length=12)

    @field_validator(
        "materials",
        "palette_delta",
        "must_preserve",
        "must_avoid",
        "evidence_refs",
    )
    @classmethod
    def clean_brief_lists(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            item = " ".join(str(value).split())[:240]
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned


class PageVisualConceptCandidate(StrictVisualBriefModel):
    candidate_id: str = Field(min_length=3, max_length=120)
    brief: PageVisualBrief
    anchor_family: str = Field(min_length=2, max_length=120)
    rationale: str = Field(min_length=2, max_length=400)
    editor_score: float = Field(default=0.0, ge=0.0, le=10.0)


class PageVisualConceptSet(StrictVisualBriefModel):
    page: int = Field(ge=1, le=12)
    candidates: list[PageVisualConceptCandidate] = Field(min_length=3, max_length=3)
    selected_candidate_id: str = Field(min_length=3, max_length=120)

    @model_validator(mode="after")
    def selected_candidate_exists(self) -> PageVisualConceptSet:
        identifiers = {item.candidate_id for item in self.candidates}
        if len(identifiers) != len(self.candidates):
            raise ValueError("同一页的视觉候选 ID 必须唯一")
        if self.selected_candidate_id not in identifiers:
            raise ValueError("选中的视觉候选必须存在于该页候选集合")
        if any(item.brief.page != self.page for item in self.candidates):
            raise ValueError("视觉候选页码必须与候选集合页码一致")
        return self


class VisualDistinctnessIssue(StrictVisualBriefModel):
    code: str = Field(min_length=2, max_length=80)
    pages: list[int] = Field(default_factory=list, max_length=12)
    detail: str = Field(min_length=2, max_length=400)
    blocking: bool = False


class VisualDistinctnessReport(StrictVisualBriefModel):
    passed: bool
    score: float = Field(ge=0.0, le=100.0)
    layout_families: list[str] = Field(default_factory=list, max_length=12)
    concrete_subjects: list[str] = Field(default_factory=list, max_length=12)
    anchor_families: list[str] = Field(default_factory=list, max_length=12)
    issues: list[VisualDistinctnessIssue] = Field(default_factory=list, max_length=48)


class FrozenVisualBriefBundle(StrictVisualBriefModel):
    schema_version: Literal[1] = 1
    compiler_version: str = Field(min_length=3, max_length=120)
    mode: VisualBriefMode
    visual_bible: VisualBible
    pages: list[PageVisualConceptSet] = Field(min_length=1, max_length=12)
    distinctness: VisualDistinctnessReport
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    warnings: list[str] = Field(default_factory=list, max_length=24)

    @field_validator("warnings")
    @classmethod
    def clean_warnings(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            item = " ".join(str(value).split())[:500]
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned

    @model_validator(mode="after")
    def pages_are_ordered_and_distinct(self) -> FrozenVisualBriefBundle:
        page_numbers = [item.page for item in self.pages]
        if page_numbers != list(range(1, len(page_numbers) + 1)):
            raise ValueError("冻结视觉简报必须从第 1 页开始连续排序")
        if not self.distinctness.passed and self.mode != "legacy":
            raise ValueError("生产视觉简报必须通过 distinctness 门禁")
        return self

    def selected_candidates(self) -> list[PageVisualConceptCandidate]:
        output: list[PageVisualConceptCandidate] = []
        for page in self.pages:
            selected = next(
                item
                for item in page.candidates
                if item.candidate_id == page.selected_candidate_id
            )
            output.append(selected)
        return output

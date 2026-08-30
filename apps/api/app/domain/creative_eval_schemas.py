from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SHA256_PATTERN = r"^[0-9a-f]{64}$"
COMMIT_PATTERN = r"^[0-9a-f]{40}$"
CASE_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{2,79}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvalSuiteHeader(StrictModel):
    schema_version: Literal[1] = 1
    baseline_id: str = Field(min_length=3, max_length=120)
    baseline_commit: str = Field(pattern=COMMIT_PATTERN)
    captured_at: datetime
    fixture_policy: str = Field(min_length=10, max_length=500)
    rubric_path: str = Field(min_length=3, max_length=240)


class EvidenceFixture(StrictModel):
    ref: str = Field(min_length=3, max_length=120)
    title: str = Field(min_length=2, max_length=200)
    excerpt: str = Field(min_length=20, max_length=1600)
    rights_status: Literal[
        "synthetic",
        "owned",
        "licensed",
        "open_license",
        "limited_quote",
        "needs_review",
    ]


class WritingInputFixture(StrictModel):
    audience: str = Field(min_length=2, max_length=240)
    promise: str = Field(min_length=5, max_length=500)
    thesis: str = Field(min_length=5, max_length=600)
    source_materials: list[EvidenceFixture] = Field(min_length=1, max_length=8)
    constraints: list[str] = Field(default_factory=list, max_length=16)


class ClaimFixture(StrictModel):
    text: str = Field(min_length=5, max_length=500)
    evidence_refs: list[str] = Field(min_length=1, max_length=8)


class WritingOutputFixture(StrictModel):
    title: str = Field(min_length=2, max_length=180)
    body_markdown: str = Field(min_length=80, max_length=20_000)
    tags: list[str] = Field(default_factory=list, max_length=12)
    claims: list[ClaimFixture] = Field(min_length=1, max_length=24)


class WritingPipelineTrace(StrictModel):
    service_path: str = Field(min_length=5, max_length=240)
    entrypoint: str = Field(min_length=3, max_length=160)
    prompt_version: str = Field(min_length=1, max_length=80)
    execution_mode: Literal[
        "deterministic_fixture",
        "captured_model_output",
        "captured_human_revision",
    ]
    fallback_used: bool


class WritingEvalCase(StrictModel):
    id: str = Field(pattern=CASE_ID_PATTERN)
    category: Literal[
        "technical_explanation",
        "news_explanation",
        "opinion_commentary",
        "light_content",
        "wechat_longform",
    ]
    platform: Literal["xhs", "wechat"]
    article_type: str = Field(min_length=2, max_length=80)
    input: WritingInputFixture
    baseline_output: WritingOutputFixture
    trace: WritingPipelineTrace
    known_issues: list[str] = Field(min_length=1, max_length=12)
    baseline_output_fingerprint: str = Field(pattern=SHA256_PATTERN)


class WritingEvalSuite(EvalSuiteHeader):
    cases: list[WritingEvalCase] = Field(min_length=12)


class StoryboardFixture(StrictModel):
    page: int = Field(ge=1, le=12)
    total_pages: int = Field(ge=1, le=12)
    visual_metaphor: str = Field(min_length=3, max_length=240)
    layout: str = Field(min_length=2, max_length=100)
    anchor: str = Field(min_length=2, max_length=100)
    accent: str = Field(min_length=2, max_length=32)
    texture: str = Field(min_length=2, max_length=100)
    mood: str = Field(min_length=2, max_length=80)
    focus_x: float = Field(ge=0.0, le=1.0)
    focus_y: float = Field(ge=0.0, le=1.0)
    zoom: float = Field(ge=0.65, le=2.0)


class VisualCompilerTrace(StrictModel):
    service_path: str = Field(min_length=5, max_length=240)
    entrypoint: str = Field(min_length=3, max_length=240)
    compiler_mode: Literal["legacy_web_handoff", "legacy_api_capture"]
    skill_name: str = Field(min_length=3, max_length=120)
    skill_commit: str = Field(pattern=COMMIT_PATTERN)
    compositor_version: str = Field(min_length=3, max_length=120)


class VisualImageReference(StrictModel):
    policy: Literal["none", "sha256_only", "repository_relative"]
    value: str = Field(default="", max_length=240)


class VisualEvalCase(StrictModel):
    id: str = Field(pattern=CASE_ID_PATTERN)
    article_summary: str = Field(min_length=10, max_length=800)
    article_thesis: str = Field(min_length=5, max_length=600)
    section_title: str = Field(min_length=2, max_length=200)
    page_visual_role: Literal[
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
    phrase: str = Field(min_length=2, max_length=100)
    note: str = Field(min_length=2, max_length=240)
    evidence_summary: str = Field(min_length=10, max_length=800)
    storyboard: StoryboardFixture
    raw_prompt: str = Field(min_length=40, max_length=3000)
    final_prompt: str = Field(min_length=200, max_length=8000)
    compiler: VisualCompilerTrace
    model_input_fingerprint: str = Field(pattern=SHA256_PATTERN)
    prompt_fingerprint: str = Field(pattern=SHA256_PATTERN)
    image_reference: VisualImageReference
    known_issues: list[str] = Field(min_length=1, max_length=12)


class VisualEvalSuite(EvalSuiteHeader):
    cases: list[VisualEvalCase] = Field(min_length=20)


class RubricDimension(StrictModel):
    id: str = Field(pattern=CASE_ID_PATTERN)
    label: str = Field(min_length=2, max_length=100)
    question: str = Field(min_length=8, max_length=500)
    score_1: str = Field(min_length=5, max_length=500)
    score_3: str = Field(min_length=5, max_length=500)
    score_5: str = Field(min_length=5, max_length=500)
    blockers: list[str] = Field(default_factory=list, max_length=12)


class RubricDocument(StrictModel):
    schema_version: Literal[1] = 1
    kind: Literal["writing", "visual"]
    scale: Literal["1-5"] = "1-5"
    dimensions: list[RubricDimension] = Field(min_length=1)


class ExportedCreativeRecord(StrictModel):
    record_ref: str = Field(min_length=12, max_length=120)
    record_type: Literal["draft_revision", "platform_variant", "writing_artifact"]
    platform: str = Field(default="", max_length=40)
    format: str = Field(default="", max_length=80)
    version: int = Field(ge=0)
    title: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=500_000)
    tags: str = Field(default="", max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    prompts: list[str] = Field(default_factory=list, max_length=64)
    content_fingerprint: str = Field(pattern=SHA256_PATTERN)


class ExportedVisualPage(StrictModel):
    record_ref: str = Field(min_length=12, max_length=120)
    parent_record_ref: str = Field(min_length=12, max_length=120)
    page: int = Field(ge=1, le=100)
    article_summary: str = Field(default="", max_length=4000)
    phrase: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=2000)
    visual_metaphor: str = Field(default="", max_length=2000)
    final_prompt: str = Field(default="", max_length=10_000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_fingerprint: str = Field(pattern=SHA256_PATTERN)


class RedactionReport(StrictModel):
    secret_values: int = Field(ge=0)
    local_paths: int = Field(ge=0)
    sensitive_url_parameters: int = Field(ge=0)
    identifiers_hashed: int = Field(ge=0)


class CreativeBaselineExport(StrictModel):
    schema_version: Literal[1] = 1
    exporter_version: Literal["c0-v1"] = "c0-v1"
    exported_at: datetime
    source_database: str = Field(min_length=1, max_length=200)
    source_database_fingerprint: str = Field(pattern=SHA256_PATTERN)
    records: list[ExportedCreativeRecord]
    visual_pages: list[ExportedVisualPage]
    redaction: RedactionReport
    warnings: list[str] = Field(default_factory=list)


def canonical_fingerprint(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def writing_output_fingerprint(output: WritingOutputFixture | dict[str, Any]) -> str:
    if isinstance(output, WritingOutputFixture):
        output = output.model_dump(mode="json")
    return canonical_fingerprint(output)


def prompt_fingerprint(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

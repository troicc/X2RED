from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SHA256_PATTERN = r"^[0-9a-f]{64}$"
EVIDENCE_REF_PATTERN = r"^[^:\s]+:[^\s]+$"


class StrictEvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


EvidenceMode = Literal["hybrid", "legacy"]
RetrievalBackend = Literal["bm25", "bm25+embedding", "legacy_character_slice"]
SelectionRole = Literal["primary", "supporting", "connected", "written_version"]
MaterialKind = Literal["source", "draft_revision", "platform_variant"]
SectionRole = Literal[
    "opening",
    "overview",
    "mechanism",
    "evidence",
    "comparison",
    "example",
    "limitations",
    "conclusion",
]


class EvidenceDocument(StrictEvidenceModel):
    document_id: str = Field(min_length=1, max_length=180)
    source_id: str = Field(min_length=1, max_length=160)
    source_index: int = Field(ge=1, le=10_000)
    material_ref: str = Field(min_length=3, max_length=240)
    material_kind: MaterialKind = "source"
    selection_role: SelectionRole = "supporting"
    title: str = Field(default="", max_length=300)
    author: str = Field(default="", max_length=240)
    canonical_url: str = Field(default="", max_length=4000)
    published_at: datetime | None = None
    captured_at: datetime | None = None
    rights_status: str = Field(default="needs_review", max_length=60)
    rights_note: str = Field(default="", max_length=2000)
    editor_note: str = Field(default="", max_length=6000)
    provider: str = Field(default="", max_length=80)
    platform: str = Field(default="", max_length=80)
    content_kind: str = Field(default="", max_length=80)
    authority_score: float = Field(default=0.5, ge=0.0, le=1.0)
    text: str = Field(min_length=1, max_length=300_000)


class EvidenceChunk(StrictEvidenceModel):
    evidence_ref: str = Field(pattern=EVIDENCE_REF_PATTERN, max_length=260)
    chunk_id: str = Field(min_length=2, max_length=120)
    source_id: str = Field(min_length=1, max_length=160)
    source_index: int = Field(ge=1, le=10_000)
    document_id: str = Field(min_length=1, max_length=180)
    material_ref: str = Field(min_length=3, max_length=240)
    material_kind: MaterialKind
    selection_role: SelectionRole
    title: str = Field(default="", max_length=300)
    author: str = Field(default="", max_length=240)
    canonical_url: str = Field(default="", max_length=4000)
    published_at: datetime | None = None
    captured_at: datetime | None = None
    rights_status: str = Field(default="needs_review", max_length=60)
    rights_note: str = Field(default="", max_length=2000)
    editor_note: str = Field(default="", max_length=6000)
    provider: str = Field(default="", max_length=80)
    platform: str = Field(default="", max_length=80)
    content_kind: str = Field(default="", max_length=80)
    authority_score: float = Field(default=0.5, ge=0.0, le=1.0)
    ordinal: int = Field(ge=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=5000)
    content_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_position_and_ref(self) -> EvidenceChunk:
        if self.end_char <= self.start_char:
            raise ValueError("evidence chunk end_char must be after start_char")
        if self.evidence_ref != f"{self.source_id}:{self.chunk_id}":
            raise ValueError("evidence_ref must preserve source_id:chunk_id")
        return self


class EvidenceSectionRequest(StrictEvidenceModel):
    section_id: str = Field(min_length=1, max_length=120)
    heading: str = Field(min_length=1, max_length=300)
    query: str = Field(min_length=1, max_length=4000)
    role: SectionRole = "overview"
    editor_note: str = Field(default="", max_length=2000)
    max_chunks: int = Field(default=5, ge=1, le=12)
    max_chars: int = Field(default=4200, ge=200, le=20_000)


class EvidenceScore(StrictEvidenceModel):
    semantic_relevance: float = Field(ge=0.0, le=1.0)
    lexical_bm25: float = Field(ge=0.0, le=1.0)
    embedding_similarity: float | None = Field(default=None, ge=-1.0, le=1.0)
    source_authority: float = Field(ge=0.0, le=1.0)
    primary_source_bonus: float = Field(ge=0.0, le=1.0)
    freshness: float = Field(ge=0.0, le=1.0)
    editor_note_relevance: float = Field(ge=0.0, le=1.0)
    section_role_relevance: float = Field(ge=0.0, le=1.0)
    rights_status: float = Field(ge=0.0, le=1.0)
    source_diversity_bonus: float = Field(ge=0.0, le=1.0)
    redundancy_penalty: float = Field(ge=0.0, le=1.0)
    rerank_score: float = Field(ge=0.0, le=1.5)
    mmr_score: float = Field(ge=-1.0, le=1.5)


class EvidenceHit(StrictEvidenceModel):
    rank: int = Field(ge=1)
    chunk: EvidenceChunk
    score: EvidenceScore
    reasons: list[str] = Field(default_factory=list, max_length=20)


class SectionEvidence(StrictEvidenceModel):
    section_id: str = Field(min_length=1, max_length=120)
    heading: str = Field(min_length=1, max_length=300)
    query: str = Field(min_length=1, max_length=4000)
    role: SectionRole
    hits: list[EvidenceHit] = Field(default_factory=list, max_length=12)
    selected_chars: int = Field(default=0, ge=0, le=100_000)


class EvidenceBundle(StrictEvidenceModel):
    schema_version: Literal[1] = 1
    compiler_version: Literal["evidence-compiler-v1"] = "evidence-compiler-v1"
    mode: EvidenceMode
    retrieval_backend: RetrievalBackend
    fingerprint: str = Field(pattern=SHA256_PATTERN)
    chunk_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    sections: list[SectionEvidence] = Field(min_length=1, max_length=24)
    warnings: list[str] = Field(default_factory=list, max_length=30)

    def evidence_refs(self) -> list[str]:
        return list(
            dict.fromkeys(
                hit.chunk.evidence_ref
                for section in self.sections
                for hit in section.hits
            )
        )

    def prompt_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "compiler_version": self.compiler_version,
            "mode": self.mode,
            "retrieval_backend": self.retrieval_backend,
            "fingerprint": self.fingerprint,
            "chunk_count": self.chunk_count,
            "source_count": self.source_count,
            "warnings": self.warnings,
            "sections": [
                {
                    "section_id": section.section_id,
                    "heading": section.heading,
                    "query": section.query,
                    "role": section.role,
                    "selected_chars": section.selected_chars,
                    "evidence_chunks": [
                        {
                            "rank": hit.rank,
                            "evidence_ref": hit.chunk.evidence_ref,
                            "source_index": hit.chunk.source_index,
                            "source_id": hit.chunk.source_id,
                            "material_ref": hit.chunk.material_ref,
                            "material_kind": hit.chunk.material_kind,
                            "selection_role": hit.chunk.selection_role,
                            "title": hit.chunk.title,
                            "author": hit.chunk.author,
                            "published_at": (
                                hit.chunk.published_at.isoformat()
                                if hit.chunk.published_at is not None
                                else ""
                            ),
                            "captured_at": (
                                hit.chunk.captured_at.isoformat()
                                if hit.chunk.captured_at is not None
                                else ""
                            ),
                            "canonical_url": hit.chunk.canonical_url,
                            "rights_status": hit.chunk.rights_status,
                            "rights_note": hit.chunk.rights_note,
                            "editor_note": hit.chunk.editor_note,
                            "provider": hit.chunk.provider,
                            "platform": hit.chunk.platform,
                            "content_kind": hit.chunk.content_kind,
                            "authority_score": hit.chunk.authority_score,
                            "position": {
                                "start_char": hit.chunk.start_char,
                                "end_char": hit.chunk.end_char,
                                "ordinal": hit.chunk.ordinal,
                            },
                            "text": hit.chunk.text,
                            "score": round(hit.score.mmr_score, 6),
                            "score_breakdown": hit.score.model_dump(mode="json"),
                            "reasons": hit.reasons,
                        }
                        for hit in section.hits
                    ],
                }
                for section in self.sections
            ],
        }

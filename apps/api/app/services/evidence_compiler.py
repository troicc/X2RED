from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.domain.evidence_schemas import (
    EvidenceBundle,
    EvidenceChunk,
    EvidenceDocument,
    EvidenceHit,
    EvidenceScore,
    EvidenceSectionRequest,
    SectionEvidence,
)
from app.domain.models import SourceItem
from app.services.retrieval import (
    EmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    RetrievalService,
    term_similarity,
)


LEGACY_FALLBACK_MARKER = "DEGRADED_LEGACY_CHARACTER_SLICE"


@dataclass(frozen=True)
class _TextUnit:
    start: int
    end: int
    text: str


class EvidenceCompiler:
    """Compile raw materials into auditable, section-specific evidence chunks."""

    compiler_version = "evidence-compiler-v1"

    def __init__(
        self,
        settings: Settings,
        *,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.settings = settings
        self.mode = settings.evidence_retrieval_mode
        self.embedding_provider = embedding_provider or self._configured_embedding_provider()
        self.retrieval = RetrievalService(self.embedding_provider)

    def _configured_embedding_provider(self) -> EmbeddingProvider | None:
        if not (
            self.settings.evidence_embedding_base_url
            and self.settings.evidence_embedding_model
        ):
            return None
        return OpenAICompatibleEmbeddingProvider(
            base_url=self.settings.evidence_embedding_base_url,
            api_key=self.settings.evidence_embedding_api_key,
            model=self.settings.evidence_embedding_model,
            timeout_seconds=self.settings.request_timeout_seconds,
        )

    @staticmethod
    def _json_object(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @classmethod
    def source_title(cls, source: SourceItem) -> str:
        metadata = cls._json_object(source.structured_content_json)
        title = metadata.get("title")
        nested = metadata.get("metadata")
        if not title and isinstance(nested, dict):
            title = nested.get("title")
        clean = re.sub(r"\s+", " ", str(title or "")).strip()
        if clean:
            return clean[:300]
        first = re.sub(r"\s+", " ", source.text_original or "").strip()
        return first[:160] or source.author_name or source.author_handle or "未命名来源"

    @staticmethod
    def _authority(source: SourceItem, selection_role: str, material_kind: str) -> float:
        if material_kind != "source":
            return 0.35
        kind_scores = {
            "paper": 0.96,
            "research": 0.92,
            "official": 0.9,
            "article": 0.78,
            "thread": 0.68,
            "post": 0.58,
            "corpus_batch": 0.3,
        }
        score = kind_scores.get(source.content_kind, 0.55)
        if selection_role == "primary":
            score += 0.08
        elif selection_role == "supporting":
            score += 0.04
        if source.provider in {"manual", "x2pdf"}:
            score += 0.03
        return max(0.0, min(score, 1.0))

    def documents_from_sources(
        self,
        sources: list[SourceItem],
        *,
        primary_source_id: str = "",
        selected_source_ids: list[str] | None = None,
        materials: list[dict[str, Any]] | None = None,
    ) -> list[EvidenceDocument]:
        selected = list(dict.fromkeys(selected_source_ids or [item.id for item in sources]))
        primary = primary_source_id or (selected[0] if selected else sources[0].id if sources else "")
        source_map = {source.id: source for source in sources}
        ordered_ids = list(dict.fromkeys([*selected, *[item.id for item in sources]]))
        index_by_source = {source_id: index for index, source_id in enumerate(ordered_ids, start=1)}
        documents: list[EvidenceDocument] = []

        for source_id in ordered_ids:
            source = source_map.get(source_id)
            if source is None or not str(source.text_original or "").strip():
                continue
            selection_role = (
                "primary"
                if source.id == primary
                else "supporting"
                if source.id in selected
                else "connected"
            )
            documents.append(
                EvidenceDocument(
                    document_id=f"source:{source.id}",
                    source_id=source.id,
                    source_index=index_by_source[source.id],
                    material_ref=f"source:{source.id}",
                    material_kind="source",
                    selection_role=selection_role,
                    title=self.source_title(source),
                    author=source.author_name or source.author_handle or "",
                    canonical_url=source.canonical_url or "",
                    published_at=source.created_at,
                    captured_at=source.captured_at,
                    rights_status=source.rights_status or "needs_review",
                    rights_note=source.rights_note or "",
                    editor_note=source.editor_note or "",
                    provider=source.provider or "",
                    platform=source.platform or "",
                    content_kind=source.content_kind or "",
                    authority_score=self._authority(source, selection_role, "source"),
                    text=source.text_original,
                )
            )

        for material in materials or []:
            kind = str(material.get("kind") or "source")
            if kind == "source":
                continue
            body = str(material.get("body") or "").strip()
            if not body:
                continue
            source_id = str(material.get("source_id") or material.get("id") or "")
            source = source_map.get(source_id)
            material_ref = str(material.get("ref") or f"{kind}:{material.get('id')}")
            documents.append(
                EvidenceDocument(
                    document_id=material_ref,
                    source_id=source_id,
                    source_index=index_by_source.get(source_id, len(index_by_source) + 1),
                    material_ref=material_ref,
                    material_kind=(
                        "draft_revision" if kind in {"draft", "draft_revision"} else "platform_variant"
                    ),
                    selection_role="written_version",
                    title=str(material.get("title") or "已写版本")[:300],
                    author=(source.author_name or source.author_handle) if source else "",
                    canonical_url=(source.canonical_url or "") if source else "",
                    published_at=source.created_at if source else None,
                    captured_at=source.captured_at if source else None,
                    rights_status=(source.rights_status or "needs_review") if source else "needs_review",
                    rights_note=(source.rights_note or "") if source else "",
                    editor_note=(
                        "已写版本仅可提供结构与表达；具体事实仍须由关联原始来源支持。"
                    ),
                    provider=(source.provider or "") if source else "",
                    platform=str(material.get("platform") or ((source.platform or "") if source else "")),
                    content_kind="written_version",
                    authority_score=self._authority(
                        source,
                        "written_version",
                        "draft_revision" if kind in {"draft", "draft_revision"} else "platform_variant",
                    ) if source else 0.3,
                    text=body,
                )
            )
        return documents

    @staticmethod
    def _clean_chunk(value: str) -> str:
        lines: list[str] = []
        for raw in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = re.sub(r"[\t ]+", " ", raw).strip()
            if line:
                lines.append(line)
        return "\n".join(lines).strip()

    @classmethod
    def _forced_units(cls, text: str, start: int, end: int, *, max_chars: int) -> list[_TextUnit]:
        output: list[_TextUnit] = []
        cursor = start
        while cursor < end:
            ceiling = min(cursor + max_chars, end)
            cut = ceiling
            if ceiling < end:
                window = text[cursor:ceiling]
                candidates = [window.rfind(mark) for mark in ("。", "！", "？", "；", "\n", "，")]
                best = max(candidates)
                if best >= max_chars // 2:
                    cut = cursor + best + 1
            clean = cls._clean_chunk(text[cursor:cut])
            if clean:
                output.append(_TextUnit(cursor, cut, clean))
            cursor = cut
        return output

    @classmethod
    def _semantic_units(cls, text: str, *, max_unit_chars: int = 520) -> list[_TextUnit]:
        output: list[_TextUnit] = []
        paragraph_pattern = re.compile(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", re.DOTALL)
        sentence_pattern = re.compile(r"[^。！？!?；;\n]+(?:[。！？!?；;]+|\n|\Z)")
        for paragraph in paragraph_pattern.finditer(text):
            start, end = paragraph.span()
            clean = cls._clean_chunk(paragraph.group())
            if not clean:
                continue
            if len(clean) <= max_unit_chars:
                output.append(_TextUnit(start, end, clean))
                continue
            sentence_units: list[_TextUnit] = []
            for sentence in sentence_pattern.finditer(paragraph.group()):
                sentence_start = start + sentence.start()
                sentence_end = start + sentence.end()
                sentence_clean = cls._clean_chunk(sentence.group())
                if not sentence_clean:
                    continue
                if len(sentence_clean) > max_unit_chars:
                    sentence_units.extend(
                        cls._forced_units(text, sentence_start, sentence_end, max_chars=max_unit_chars)
                    )
                else:
                    sentence_units.append(_TextUnit(sentence_start, sentence_end, sentence_clean))
            output.extend(sentence_units or cls._forced_units(text, start, end, max_chars=max_unit_chars))
        return output

    @classmethod
    def chunk_document(
        cls,
        document: EvidenceDocument,
        *,
        target_chars: int = 520,
        max_chars: int = 850,
    ) -> list[EvidenceChunk]:
        units = cls._semantic_units(document.text)
        spans: list[list[_TextUnit]] = []
        current: list[_TextUnit] = []
        current_chars = 0
        for unit in units:
            unit_chars = len(unit.text)
            if current and current_chars + unit_chars > target_chars:
                spans.append(current)
                current = []
                current_chars = 0
            current.append(unit)
            current_chars += unit_chars
            if current_chars >= max_chars:
                spans.append(current)
                current = []
                current_chars = 0
        if current:
            spans.append(current)

        material_prefix = ""
        if document.material_kind != "source":
            material_prefix = "m" + hashlib.sha256(document.material_ref.encode()).hexdigest()[:8] + "-"
        chunks: list[EvidenceChunk] = []
        for ordinal, group in enumerate(spans, start=1):
            text = "\n\n".join(unit.text for unit in group).strip()
            if not text:
                continue
            start = min(unit.start for unit in group)
            end = max(unit.end for unit in group)
            chunk_id = f"{material_prefix}c{ordinal:04d}"
            chunks.append(
                EvidenceChunk(
                    evidence_ref=f"{document.source_id}:{chunk_id}",
                    chunk_id=chunk_id,
                    source_id=document.source_id,
                    source_index=document.source_index,
                    document_id=document.document_id,
                    material_ref=document.material_ref,
                    material_kind=document.material_kind,
                    selection_role=document.selection_role,
                    title=document.title,
                    author=document.author,
                    canonical_url=document.canonical_url,
                    published_at=document.published_at,
                    captured_at=document.captured_at,
                    rights_status=document.rights_status,
                    rights_note=document.rights_note,
                    editor_note=document.editor_note,
                    provider=document.provider,
                    platform=document.platform,
                    content_kind=document.content_kind,
                    authority_score=document.authority_score,
                    ordinal=ordinal,
                    start_char=start,
                    end_char=end,
                    text=text,
                    content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                )
            )
        return chunks

    def compile_sources(
        self,
        sources: list[SourceItem],
        sections: list[EvidenceSectionRequest],
        *,
        primary_source_id: str = "",
        selected_source_ids: list[str] | None = None,
        materials: list[dict[str, Any]] | None = None,
    ) -> EvidenceBundle:
        documents = self.documents_from_sources(
            sources,
            primary_source_id=primary_source_id,
            selected_source_ids=selected_source_ids,
            materials=materials,
        )
        return self.compile(documents, sections)

    def compile(
        self,
        documents: list[EvidenceDocument],
        sections: list[EvidenceSectionRequest],
    ) -> EvidenceBundle:
        if not sections:
            raise ValueError("evidence compilation requires at least one section query")
        fingerprint = self._fingerprint(documents, sections)
        if self.mode == "legacy":
            return self._compile_legacy(documents, sections, fingerprint=fingerprint)

        chunks = [
            chunk
            for document in documents
            for chunk in self.chunk_document(document)
        ]
        compiled_sections: list[SectionEvidence] = []
        warnings: list[str] = []
        backends: set[str] = set()
        for section in sections:
            result = self.retrieval.search(chunks, section)
            warnings.extend(result.warnings)
            backends.add(result.backend)
            compiled_sections.append(
                SectionEvidence(
                    section_id=section.section_id,
                    heading=section.heading,
                    query=section.query,
                    role=section.role,
                    hits=result.hits,
                    selected_chars=sum(len(hit.chunk.text) for hit in result.hits),
                )
            )
        backend = "bm25+embedding" if "bm25+embedding" in backends else "bm25"
        return EvidenceBundle(
            mode="hybrid",
            retrieval_backend=backend,
            fingerprint=fingerprint,
            chunk_count=len(chunks),
            source_count=len({document.source_id for document in documents}),
            sections=compiled_sections,
            warnings=list(dict.fromkeys(warnings)),
        )

    def _compile_legacy(
        self,
        documents: list[EvidenceDocument],
        sections: list[EvidenceSectionRequest],
        *,
        fingerprint: str,
    ) -> EvidenceBundle:
        per_document = max(600, min(4000, 24_000 // max(1, len(documents))))
        chunks: list[EvidenceChunk] = []
        for document in documents:
            text = self._clean_chunk(document.text[:per_document])
            if not text:
                continue
            chunk_id = (
                "legacy-c0001"
                if document.material_kind == "source"
                else "m"
                + hashlib.sha256(document.material_ref.encode()).hexdigest()[:8]
                + "-legacy-c0001"
            )
            chunks.append(
                EvidenceChunk(
                    evidence_ref=f"{document.source_id}:{chunk_id}",
                    chunk_id=chunk_id,
                    source_id=document.source_id,
                    source_index=document.source_index,
                    document_id=document.document_id,
                    material_ref=document.material_ref,
                    material_kind=document.material_kind,
                    selection_role=document.selection_role,
                    title=document.title,
                    author=document.author,
                    canonical_url=document.canonical_url,
                    published_at=document.published_at,
                    captured_at=document.captured_at,
                    rights_status=document.rights_status,
                    rights_note=document.rights_note,
                    editor_note=document.editor_note,
                    provider=document.provider,
                    platform=document.platform,
                    content_kind=document.content_kind,
                    authority_score=document.authority_score,
                    ordinal=1,
                    start_char=0,
                    end_char=min(len(document.text), per_document),
                    text=text,
                    content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                )
            )
        compiled: list[SectionEvidence] = []
        for section in sections:
            selected: list[EvidenceHit] = []
            selected_chars = 0
            for chunk in chunks:
                if selected and (
                    len(selected) >= section.max_chunks
                    or selected_chars + len(chunk.text) > section.max_chars
                ):
                    continue
                rights = 0.0 if chunk.rights_status == "do_not_publish" else 0.45
                selected.append(
                    EvidenceHit(
                        rank=len(selected) + 1,
                        chunk=chunk,
                        score=EvidenceScore(
                            semantic_relevance=0.0,
                            lexical_bm25=0.0,
                            embedding_similarity=None,
                            source_authority=chunk.authority_score,
                            primary_source_bonus=(1.0 if chunk.selection_role == "primary" else 0.0),
                            freshness=0.0,
                            editor_note_relevance=0.0,
                            section_role_relevance=0.0,
                            rights_status=rights,
                            source_diversity_bonus=0.0,
                            redundancy_penalty=0.0,
                            rerank_score=0.0,
                            mmr_score=0.0,
                        ),
                        reasons=[LEGACY_FALLBACK_MARKER],
                    )
                )
                selected_chars += len(chunk.text)
            compiled.append(
                SectionEvidence(
                    section_id=section.section_id,
                    heading=section.heading,
                    query=section.query,
                    role=section.role,
                    hits=selected,
                    selected_chars=selected_chars,
                )
            )
        return EvidenceBundle(
            mode="legacy",
            retrieval_backend="legacy_character_slice",
            fingerprint=fingerprint,
            chunk_count=len(chunks),
            source_count=len({document.source_id for document in documents}),
            sections=compiled,
            warnings=[LEGACY_FALLBACK_MARKER],
        )

    def semantic_summary(self, source: SourceItem, *, query: str = "") -> tuple[str, list[str]]:
        sections = [
            EvidenceSectionRequest(
                section_id="overview",
                heading="核心信息",
                query=query or self.source_title(source),
                role="overview",
                max_chunks=1,
                max_chars=1200,
            ),
            EvidenceSectionRequest(
                section_id="limitations",
                heading="证据与限制",
                query=f"{query} 数据 结果 方法 限制 条件 反例 结论",
                role="limitations",
                max_chunks=1,
                max_chars=1200,
            ),
        ]
        bundle = self.compile_sources(
            [source],
            sections,
            primary_source_id=source.id,
            selected_source_ids=[source.id],
        )
        hits = [hit for section in bundle.sections for hit in section.hits]
        excerpts: list[str] = []
        refs: list[str] = []
        for hit in hits:
            compact = re.sub(r"\s+", " ", hit.chunk.text).strip()
            sentences = [
                item.strip()
                for item in re.split(r"(?<=[。！？!?；;])", compact)
                if item.strip()
            ]
            sentence = max(
                sentences or [compact],
                key=lambda item: (
                    term_similarity(query, item),
                    min(len(item), 260),
                ),
            )
            value = sentence[:260]
            if value and value not in excerpts:
                excerpts.append(value)
                refs.append(hit.chunk.evidence_ref)
        return " ".join(excerpts)[:520], refs

    def _fingerprint(
        self,
        documents: list[EvidenceDocument],
        sections: list[EvidenceSectionRequest],
    ) -> str:
        payload = {
            "compiler_version": self.compiler_version,
            "mode": self.mode,
            "embedding_provider": (
                self.embedding_provider.name if self.embedding_provider is not None else ""
            ),
            "documents": [
                {
                    **item.model_dump(mode="json", exclude={"text"}),
                    "text_sha256": hashlib.sha256(item.text.encode()).hexdigest(),
                }
                for item in documents
            ],
            "sections": [item.model_dump(mode="json") for item in sections],
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

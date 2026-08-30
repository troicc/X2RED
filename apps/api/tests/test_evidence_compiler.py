from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.domain.evidence_schemas import (
    EvidenceDocument,
    EvidenceSectionRequest,
)
from app.domain.models import SourceItem
from app.services.evidence_compiler import (
    LEGACY_FALLBACK_MARKER,
    EvidenceCompiler,
)
from app.services.retrieval import bounded_json


def _source(
    source_id: str,
    text: str,
    *,
    title: str = "合成证据来源",
    role_note: str = "",
    rights_status: str = "owned",
) -> SourceItem:
    return SourceItem(
        id=source_id,
        provider="manual",
        platform="web",
        external_id=source_id,
        canonical_url=f"https://example.com/{source_id}",
        author_name=f"作者 {source_id}",
        text_original=text,
        content_kind="article",
        structured_content_json=f'{{"title":"{title}","unused":"不应作为正文切片"}}',
        editor_note=role_note,
        rights_status=rights_status,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        captured_at=datetime(2026, 8, 2, tzinfo=UTC),
    )


def _section(
    query: str,
    *,
    section_id: str = "evidence",
    heading: str = "关键证据",
    role: str = "evidence",
    max_chunks: int = 4,
) -> EvidenceSectionRequest:
    return EvidenceSectionRequest(
        section_id=section_id,
        heading=heading,
        query=query,
        role=role,
        max_chunks=max_chunks,
        max_chars=3600,
    )


def test_evidence_schema_is_strict_and_preserves_source_chunk_ref() -> None:
    with pytest.raises(ValidationError):
        EvidenceDocument(
            document_id="source:src_1",
            source_id="src_1",
            source_index=1,
            material_ref="source:src_1",
            text="有效正文",
            unknown_field="not allowed",
        )

    compiler = EvidenceCompiler(Settings())
    source = _source("src_1", "第一段说明方法。\n\n第二段给出测试结果。")
    bundle = compiler.compile_sources(
        [source],
        [_section("测试结果")],
        primary_source_id=source.id,
        selected_source_ids=[source.id],
    )
    hit = bundle.sections[0].hits[0]
    assert hit.chunk.evidence_ref == f"{hit.chunk.source_id}:{hit.chunk.chunk_id}"
    assert hit.chunk.start_char < hit.chunk.end_char
    assert hit.chunk.rights_status == "owned"
    assert hit.chunk.author == "作者 src_1"
    assert hit.chunk.captured_at == source.captured_at
    assert hit.chunk.canonical_url == source.canonical_url
    prompt_hit = bundle.prompt_payload()["sections"][0]["evidence_chunks"][0]
    assert bundle.prompt_payload()["compiler_version"] == "evidence-compiler-v1"
    assert bundle.prompt_payload()["chunk_count"] == bundle.chunk_count
    assert prompt_hit["captured_at"] == source.captured_at.isoformat()
    assert prompt_hit["canonical_url"] == source.canonical_url
    assert prompt_hit["rank"] == 1
    assert set(prompt_hit["score_breakdown"]) >= {
        "semantic_relevance",
        "source_authority",
        "freshness",
        "source_diversity_bonus",
        "redundancy_penalty",
    }


def test_prompt_budget_compaction_keeps_valid_json() -> None:
    rendered = bounded_json(
        {"sources": [{"text": "尾部证据" * 5000, "id": "src_long"}]},
        1200,
    )

    parsed = json.loads(rendered)
    assert len(rendered) <= 1200
    assert parsed["_x2red_prompt_compacted"] is True


def test_tail_evidence_survives_long_material_and_is_retrieved() -> None:
    opening = "\n\n".join(
        f"背景段落 {index} 介绍一般流程、常规步骤和已知上下文。" * 8
        for index in range(8)
    )
    tail = (
        "最终限制条件：只有在离线模式并保持原始顺序时才能复现实验；"
        "联网模式会改变缓存，因此不能把局部结果扩大成端到端结论。"
    )
    source = _source("src_tail", f"{opening}\n\n{tail}", title="长材料尾部实验")
    compiler = EvidenceCompiler(Settings(evidence_retrieval_mode="hybrid"))

    bundle = compiler.compile_sources(
        [source],
        [_section("离线模式 原始顺序 缓存 局部结果 限制", role="limitations")],
        primary_source_id=source.id,
        selected_source_ids=[source.id],
    )

    assert bundle.mode == "hybrid"
    assert bundle.retrieval_backend == "bm25"
    assert any("最终限制条件" in hit.chunk.text for hit in bundle.sections[0].hits)
    assert any(hit.chunk.start_char > len(source.text_original) * 0.7 for hit in bundle.sections[0].hits)


def test_section_queries_receive_different_evidence_chunks() -> None:
    source = _source(
        "src_sections",
        (
            "## 工作机制\n\n调度器先建立倒排索引，再计算词频与逆文档频率，最后形成 BM25 分数。\n\n"
            + "机制补充说明。" * 80
            + "\n\n## 适用限制\n\n样本高度重复时必须使用 MMR 去重；权利状态为禁止发布的片段不能进入成稿。"
        ),
    )
    compiler = EvidenceCompiler(Settings())
    bundle = compiler.compile_sources(
        [source],
        [
            _section("倒排索引 BM25 计算步骤", section_id="mechanism", heading="怎么做", role="mechanism", max_chunks=1),
            _section("重复样本 MMR 权利 禁止发布", section_id="limits", heading="边界", role="limitations", max_chunks=1),
        ],
        primary_source_id=source.id,
    )

    mechanism = bundle.sections[0].hits[0].chunk
    limitations = bundle.sections[1].hits[0].chunk
    assert mechanism.evidence_ref != limitations.evidence_ref
    assert "倒排索引" in mechanism.text
    assert "MMR" in limitations.text
    assert all(section.hits for section in bundle.sections)


def test_mmr_deduplicates_repeated_text_and_rewards_source_diversity() -> None:
    duplicate = "公开测试记录显示，缓存命中后延迟下降；该结果只对应局部函数。" * 12
    source_a = _source("src_a", duplicate, title="来源 A")
    source_b = _source("src_b", duplicate, title="来源 B")
    source_c = _source(
        "src_c",
        "另一份独立材料解释了缓存失效条件，并指出端到端结果仍受网络和磁盘影响。" * 8,
        title="来源 C",
    )
    compiler = EvidenceCompiler(Settings())
    bundle = compiler.compile_sources(
        [source_a, source_b, source_c],
        [_section("缓存 延迟 局部函数 失效条件 端到端", max_chunks=6)],
        primary_source_id=source_a.id,
        selected_source_ids=[source_a.id, source_b.id, source_c.id],
    )

    hits = bundle.sections[0].hits
    hashes = [hit.chunk.content_sha256 for hit in hits]
    assert len(hashes) == len(set(hashes))
    assert "src_c" in {hit.chunk.source_id for hit in hits}
    assert len(hits) < 6


def test_written_version_chunks_keep_underlying_source_and_unique_chunk_ids() -> None:
    source = _source("src_written", "原始来源确认系统使用不可变版本保存事实。")
    compiler = EvidenceCompiler(Settings())
    documents = compiler.documents_from_sources(
        [source],
        primary_source_id=source.id,
        materials=[
            {
                "ref": "draft:draft_1",
                "kind": "draft_revision",
                "id": "draft_1",
                "source_id": source.id,
                "title": "旧稿",
                "body": "旧稿提出一种段落结构，但具体事实必须回到原始来源。",
            }
        ],
    )
    chunks = [chunk for document in documents for chunk in compiler.chunk_document(document)]

    assert len({chunk.evidence_ref for chunk in chunks}) == len(chunks)
    written = next(chunk for chunk in chunks if chunk.material_kind == "draft_revision")
    assert written.selection_role == "written_version"
    assert written.evidence_ref.startswith(f"{source.id}:m")


def test_structured_json_is_metadata_not_a_string_slice() -> None:
    source = _source("src_json", "正文只包含可引用事实：尾部约束必须保留。")
    source.structured_content_json = (
        '{"title":"结构标题","private_internal":"JSON_ONLY_SENTINEL",'
        '"nested":{"body":"不应进入证据正文"}}'
    )
    compiler = EvidenceCompiler(Settings())
    bundle = compiler.compile_sources([source], [_section("尾部约束")])

    texts = "\n".join(hit.chunk.text for hit in bundle.sections[0].hits)
    assert "JSON_ONLY_SENTINEL" not in texts
    assert "不应进入证据正文" not in texts
    assert bundle.sections[0].hits[0].chunk.title == "结构标题"


def test_bundle_fingerprint_covers_provenance_and_ranking_metadata() -> None:
    source = _source(
        "src_fingerprint",
        "相同正文也必须受来源元数据指纹约束。",
        role_note="优先说明权利边界",
    )
    compiler = EvidenceCompiler(Settings())
    first = compiler.compile_sources([source], [_section("来源元数据")])

    source.editor_note = "优先说明适用范围"
    source.rights_note = "只允许短引用"
    second = compiler.compile_sources([source], [_section("来源元数据")])

    assert first.fingerprint != second.fingerprint


def test_no_embedding_configuration_uses_bm25_fallback() -> None:
    compiler = EvidenceCompiler(
        Settings(
            evidence_embedding_base_url="",
            evidence_embedding_model="",
        )
    )
    bundle = compiler.compile_sources(
        [_source("src_fts", "全文检索可以在没有向量模型时继续工作。")],
        [_section("全文检索 向量模型")],
    )

    assert bundle.retrieval_backend == "bm25"
    assert "EMBEDDING_NOT_CONFIGURED_USING_BM25" in bundle.warnings


def test_optional_embedding_provider_participates_in_hybrid_ranking() -> None:
    class FakeEmbeddingProvider:
        name = "fake-test-embedding"

        def embed(self, texts: list[str]) -> list[list[float]]:
            return [
                [1.0, 0.0] if "稀有尾证据" in text else [0.0, 1.0]
                for text in texts
            ]

    compiler = EvidenceCompiler(Settings(), embedding_provider=FakeEmbeddingProvider())
    source = _source(
        "src_embed",
        "普通背景说明。" * 100 + "\n\n稀有尾证据说明特殊失败条件。",
    )
    bundle = compiler.compile_sources(
        [source],
        [_section("稀有尾证据")],
    )

    assert bundle.retrieval_backend == "bm25+embedding"
    assert "稀有尾证据" in bundle.sections[0].hits[0].chunk.text
    assert bundle.sections[0].hits[0].score.embedding_similarity is not None


def test_embedding_failure_is_explicit_and_falls_back_to_bm25() -> None:
    class BrokenEmbeddingProvider:
        name = "broken-test-embedding"

        def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("offline")

    compiler = EvidenceCompiler(Settings(), embedding_provider=BrokenEmbeddingProvider())
    source = _source("src_bm25", "BM25 仍然可以召回失败边界。")
    bundle = compiler.compile_sources([source], [_section("失败边界")])

    assert bundle.retrieval_backend == "bm25"
    assert "EMBEDDING_FAILED_USING_BM25:RuntimeError" in bundle.warnings
    assert bundle.sections[0].hits


def test_legacy_mode_is_available_but_marked_degraded() -> None:
    source = _source(
        "src_legacy",
        "开头信息。" * 900 + "尾部决定性证据只在最后出现。",
    )
    compiler = EvidenceCompiler(Settings(evidence_retrieval_mode="legacy"))
    bundle = compiler.compile_sources(
        [source],
        [_section("尾部决定性证据")],
    )

    assert bundle.mode == "legacy"
    assert bundle.retrieval_backend == "legacy_character_slice"
    assert LEGACY_FALLBACK_MARKER in bundle.warnings
    assert all(
        LEGACY_FALLBACK_MARKER in hit.reasons
        for hit in bundle.sections[0].hits
    )
    assert all("尾部决定性证据" not in hit.chunk.text for hit in bundle.sections[0].hits)


def test_semantic_summary_can_use_relevant_tail_instead_of_first_sentences() -> None:
    source = _source(
        "src_summary",
        "一般背景信息。" * 180
        + "\n\n关键限制条件是必须保留原始顺序，否则缓存键会发生变化。",
        title="缓存顺序实验",
        role_note="摘要必须说明原始顺序和缓存键限制",
    )
    compiler = EvidenceCompiler(Settings())
    summary, refs = compiler.semantic_summary(
        source,
        query="原始顺序 缓存键 限制",
    )

    assert "原始顺序" in summary
    assert refs and all(value.startswith(f"{source.id}:") for value in refs)

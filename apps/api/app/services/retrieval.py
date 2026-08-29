from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

import httpx

from app.domain.evidence_schemas import (
    EvidenceChunk,
    EvidenceHit,
    EvidenceScore,
    EvidenceSectionRequest,
)


_ROLE_TERMS: dict[str, str] = {
    "opening": "发生 变化 结果 为什么 值得 重要 背景",
    "overview": "主题 核心 发生 总结 主线",
    "mechanism": "方法 机制 过程 步骤 原理 实现 如何",
    "evidence": "证据 数据 数字 测试 结果 显示 样本 来源",
    "comparison": "对比 差异 相比 另一 然而 但是 取舍",
    "example": "案例 例子 场景 实际 具体",
    "limitations": "限制 边界 风险 反例 不能 条件 仅 局部 未知",
    "conclusion": "结论 意味 因此 判断 下一步 影响",
}

_RIGHTS_SCORES = {
    "owned": 1.0,
    "licensed": 0.95,
    "open_license": 0.9,
    "limited_quote": 0.7,
    "needs_review": 0.45,
    "do_not_publish": 0.0,
    "synthetic": 1.0,
}


def bounded_json(value: object, max_chars: int) -> str:
    """Serialize valid JSON within a prompt budget; never slice serialized JSON."""

    minimal = '{"_x2red_prompt_compacted":true}'
    if max_chars < len(minimal):
        raise ValueError(
            f"bounded_json requires max_chars >= {len(minimal)} to preserve its marker"
        )
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(rendered) <= max_chars:
        return rendered

    def compact(item: object, *, string_limit: int, item_limit: int) -> object:
        if isinstance(item, dict):
            return {
                str(key): compact(child, string_limit=string_limit, item_limit=item_limit)
                for key, child in list(item.items())[:item_limit]
            }
        if isinstance(item, list):
            output = [
                compact(child, string_limit=string_limit, item_limit=item_limit)
                for child in item[:item_limit]
            ]
            if len(item) > item_limit:
                output.append({"_x2red_omitted_items": len(item) - item_limit})
            return output
        if isinstance(item, str) and len(item) > string_limit:
            omitted = len(item) - string_limit
            return f"{item[:string_limit]}…[X2RED omitted {omitted} chars]"
        return item

    for string_limit, item_limit in (
        (4000, 48),
        (2000, 32),
        (1000, 24),
        (500, 16),
        (240, 12),
        (120, 8),
        (60, 5),
    ):
        candidate = json.dumps(
            {
                "_x2red_prompt_compacted": True,
                "payload": compact(
                    value,
                    string_limit=string_limit,
                    item_limit=item_limit,
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if len(candidate) <= max_chars:
            return candidate

    top_level_keys = list(value)[:20] if isinstance(value, dict) else []
    final = json.dumps(
        {
            "_x2red_prompt_compacted": True,
            "content_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
            "original_chars": len(rendered),
            "top_level_keys": top_level_keys,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return final if len(final) <= max_chars else minimal


def lexical_tokens(value: str) -> list[str]:
    """Return deterministic English terms and Chinese bi/tri-grams for FTS."""

    lowered = str(value or "").lower()
    output = re.findall(r"[a-z0-9][a-z0-9_+.#-]{1,50}", lowered)
    for run in re.findall(r"[\u3400-\u9fff]+", lowered):
        if len(run) <= 2:
            output.append(run)
            continue
        output.extend(run[index : index + 2] for index in range(len(run) - 1))
        if len(run) <= 36:
            output.extend(run[index : index + 3] for index in range(len(run) - 2))
    return output


def lexical_terms(value: str) -> set[str]:
    return set(lexical_tokens(value))


def term_similarity(left: str, right: str) -> float:
    left_terms = lexical_terms(left)
    right_terms = lexical_terms(right)
    if not left_terms or not right_terms:
        return 0.0
    return len(left_terms & right_terms) / math.sqrt(len(left_terms) * len(right_terms))


def keyword_digest(value: str, *, max_terms: int = 256) -> str:
    """Compress a long relevance query without privileging its first characters."""

    counts = Counter(lexical_tokens(value))
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return " ".join(term for term, _ in ranked[:max_terms])


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if denominator <= 0:
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=True)) / denominator))


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAICompatibleEmbeddingProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.name = f"openai-compatible:{model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        endpoint = (
            self.base_url
            if self.base_url.endswith("/embeddings")
            else f"{self.base_url}/embeddings"
        )
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            endpoint,
            headers=headers,
            json={"model": self.model, "input": texts},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("embedding provider returned no data list")
        ordered = sorted(
            (item for item in rows if isinstance(item, dict)),
            key=lambda item: int(item.get("index") or 0),
        )
        vectors = [item.get("embedding") for item in ordered]
        if len(vectors) != len(texts) or any(not isinstance(item, list) for item in vectors):
            raise ValueError("embedding provider returned an invalid vector count")
        return [[float(value) for value in item] for item in vectors]


@dataclass(frozen=True)
class RetrievalResult:
    hits: list[EvidenceHit]
    backend: str
    warnings: list[str]


@dataclass(frozen=True)
class _Candidate:
    chunk: EvidenceChunk
    score: EvidenceScore
    reasons: list[str]


class BM25Index:
    def __init__(self, chunks: list[EvidenceChunk], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.tokens = [lexical_tokens(chunk.text) for chunk in chunks]
        self.frequencies = [Counter(tokens) for tokens in self.tokens]
        self.lengths = [len(tokens) for tokens in self.tokens]
        self.average_length = sum(self.lengths) / max(1, len(self.lengths))
        self.document_frequency: Counter[str] = Counter()
        for tokens in self.tokens:
            self.document_frequency.update(set(tokens))

    def scores(self, query: str) -> list[float]:
        query_terms = Counter(lexical_tokens(query))
        document_count = len(self.chunks)
        output: list[float] = []
        for frequencies, length in zip(self.frequencies, self.lengths, strict=True):
            score = 0.0
            for term, query_frequency in query_terms.items():
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                df = self.document_frequency[term]
                inverse = math.log(1 + (document_count - df + 0.5) / (df + 0.5))
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * length / max(self.average_length, 1.0)
                )
                score += inverse * (frequency * (self.k1 + 1) / denominator) * min(query_frequency, 2)
            output.append(score)
        return output


class RetrievalService:
    def __init__(self, embedding_provider: EmbeddingProvider | None = None) -> None:
        self.embedding_provider = embedding_provider
        self._embedding_cache: dict[str, list[float]] = {}
        self._embedding_error_warning = ""

    @staticmethod
    def _freshness(chunk: EvidenceChunk) -> float:
        published = chunk.published_at
        if published is None:
            return 0.35
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        age_days = max((datetime.now(UTC) - published).total_seconds() / 86400, 0.0)
        return 1.0 / (1.0 + age_days / 365.0)

    @staticmethod
    def _role_relevance(section: EvidenceSectionRequest, chunk: EvidenceChunk) -> float:
        role_terms = _ROLE_TERMS.get(section.role, "")
        return min(1.0, term_similarity(role_terms, chunk.text) * 2.5)

    @staticmethod
    def _near_duplicate(left: EvidenceChunk, right: EvidenceChunk) -> bool:
        if left.content_sha256 == right.content_sha256:
            return True
        left_terms = lexical_terms(left.text)
        right_terms = lexical_terms(right.text)
        if not left_terms or not right_terms:
            return False
        union = left_terms | right_terms
        return bool(union) and len(left_terms & right_terms) / len(union) >= 0.9

    @staticmethod
    def _embedding_key(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def _embedding_scores(
        self,
        chunks: list[EvidenceChunk],
        section: EvidenceSectionRequest,
        bm25: list[float],
    ) -> tuple[list[float | None], str]:
        output: list[float | None] = [None] * len(chunks)
        if self.embedding_provider is None:
            return output, "EMBEDDING_NOT_CONFIGURED_USING_BM25"
        if self._embedding_error_warning:
            return output, self._embedding_error_warning

        recall_limit = min(len(chunks), max(48, section.max_chunks * 12), 128)
        ranked = sorted(
            range(len(chunks)),
            key=lambda index: (
                bm25[index],
                chunks[index].authority_score,
                chunks[index].selection_role == "primary",
                -chunks[index].source_index,
            ),
            reverse=True,
        )
        candidate_indices = set(ranked[:recall_limit])
        # Preserve one lexical candidate per source before embedding rerank.
        per_source: dict[str, int] = {}
        for index in ranked:
            per_source.setdefault(chunks[index].source_id, index)
        candidate_indices.update(per_source.values())

        query_text = " ".join(
            [section.heading, section.query, section.editor_note, _ROLE_TERMS[section.role]]
        )
        values = [query_text, *[chunks[index].text for index in sorted(candidate_indices)]]
        keys = [self._embedding_key(value) for value in values]
        missing: list[tuple[str, str]] = [
            (key, value)
            for key, value in zip(keys, values, strict=True)
            if key not in self._embedding_cache
        ]
        try:
            if missing:
                vectors = self.embedding_provider.embed([value for _, value in missing])
                if len(vectors) != len(missing):
                    raise ValueError("embedding vector count mismatch")
                for (key, _), vector in zip(missing, vectors, strict=True):
                    if not vector or not all(math.isfinite(float(value)) for value in vector):
                        raise ValueError("embedding provider returned an invalid vector")
                    self._embedding_cache[key] = vector
            query_vector = self._embedding_cache[keys[0]]
            expected_dimensions = len(query_vector)
            if expected_dimensions == 0 or any(
                len(self._embedding_cache[key]) != expected_dimensions
                for key in keys[1:]
            ):
                raise ValueError("embedding provider returned inconsistent dimensions")
            for offset, index in enumerate(sorted(candidate_indices), start=1):
                output[index] = _cosine(query_vector, self._embedding_cache[keys[offset]])
        except Exception as exc:
            self._embedding_error_warning = (
                f"EMBEDDING_FAILED_USING_BM25:{type(exc).__name__}"
            )
            return [None] * len(chunks), self._embedding_error_warning
        return output, ""

    def search(
        self,
        chunks: list[EvidenceChunk],
        section: EvidenceSectionRequest,
    ) -> RetrievalResult:
        if not chunks:
            return RetrievalResult(hits=[], backend="bm25", warnings=["NO_EVIDENCE_CHUNKS"])

        bm25_raw = BM25Index(chunks).scores(
            " ".join([section.heading, section.query, section.editor_note, _ROLE_TERMS[section.role]])
        )
        bm25_peak = max(bm25_raw) if bm25_raw else 0.0
        bm25 = [value / bm25_peak if bm25_peak > 0 else 0.0 for value in bm25_raw]

        warnings: list[str] = []
        backend = "bm25"
        embedding_scores, embedding_warning = self._embedding_scores(
            chunks,
            section,
            bm25,
        )
        if embedding_warning:
            warnings.append(embedding_warning)
        elif any(value is not None for value in embedding_scores):
            backend = "bm25+embedding"

        candidates: list[_Candidate] = []
        query_text = " ".join([section.heading, section.query, section.editor_note])
        for index, chunk in enumerate(chunks):
            embedding = embedding_scores[index]
            embedding_normalized = ((embedding + 1.0) / 2.0) if embedding is not None else 0.0
            semantic = (
                0.68 * bm25[index] + 0.32 * embedding_normalized
                if embedding is not None
                else bm25[index]
            )
            primary = 1.0 if chunk.selection_role == "primary" else 0.55 if chunk.selection_role == "supporting" else 0.0
            freshness = self._freshness(chunk)
            editor_relevance = min(
                1.0,
                max(
                    term_similarity(query_text, chunk.editor_note) * 2.5,
                    term_similarity(section.editor_note, chunk.text) * 2.5,
                ),
            )
            role_relevance = self._role_relevance(section, chunk)
            rights = _RIGHTS_SCORES.get(chunk.rights_status, 0.35)
            rerank = (
                semantic * 0.52
                + chunk.authority_score * 0.12
                + primary * 0.08
                + freshness * 0.06
                + editor_relevance * 0.07
                + role_relevance * 0.08
                + rights * 0.07
            )
            reasons = ["BM25 全文召回"]
            if embedding is not None:
                reasons.append(f"embedding:{self.embedding_provider.name}")
            if chunk.selection_role == "primary":
                reasons.append("主来源加权")
            elif chunk.selection_role == "supporting":
                reasons.append("作者选定 supporting 来源")
            if editor_relevance > 0:
                reasons.append("编辑备注相关")
            if role_relevance > 0:
                reasons.append(f"章节职责相关:{section.role}")
            reasons.extend(
                [
                    f"来源权威:{chunk.authority_score:.2f}",
                    f"新鲜度:{freshness:.2f}",
                    f"权利状态:{chunk.rights_status}",
                ]
            )
            candidates.append(
                _Candidate(
                    chunk=chunk,
                    reasons=reasons,
                    score=EvidenceScore(
                        semantic_relevance=round(semantic, 8),
                        lexical_bm25=round(bm25[index], 8),
                        embedding_similarity=(round(embedding, 8) if embedding is not None else None),
                        source_authority=round(chunk.authority_score, 8),
                        primary_source_bonus=primary,
                        freshness=round(freshness, 8),
                        editor_note_relevance=round(editor_relevance, 8),
                        section_role_relevance=round(role_relevance, 8),
                        rights_status=rights,
                        source_diversity_bonus=0.0,
                        redundancy_penalty=0.0,
                        rerank_score=round(rerank, 8),
                        mmr_score=round(rerank, 8),
                    ),
                )
            )

        candidates.sort(
            key=lambda item: (
                item.score.rerank_score,
                -item.chunk.source_index,
                -item.chunk.ordinal,
            ),
            reverse=True,
        )
        selected: list[_Candidate] = []
        selected_sources: set[str] = set()
        selected_chars = 0
        remaining = list(candidates)
        while remaining and len(selected) < section.max_chunks:
            best: _Candidate | None = None
            best_score = -10.0
            for candidate in remaining:
                if any(self._near_duplicate(candidate.chunk, item.chunk) for item in selected):
                    continue
                redundancy = max(
                    (term_similarity(candidate.chunk.text, item.chunk.text) for item in selected),
                    default=0.0,
                )
                diversity = 0.08 if candidate.chunk.source_id not in selected_sources else 0.0
                mmr_score = candidate.score.rerank_score * 0.78 - redundancy * 0.22 + diversity
                if mmr_score > best_score:
                    best_score = mmr_score
                    best = replace(
                        candidate,
                        reasons=[
                            *candidate.reasons,
                            *(["来源多样性加分"] if diversity else []),
                            *([f"冗余惩罚:{redundancy:.2f}"] if redundancy else []),
                        ],
                        score=candidate.score.model_copy(
                            update={
                                "source_diversity_bonus": diversity,
                                "redundancy_penalty": round(redundancy, 8),
                                "mmr_score": round(mmr_score, 8),
                            }
                        ),
                    )
            if best is None:
                break
            remaining = [item for item in remaining if item.chunk.evidence_ref != best.chunk.evidence_ref]
            chunk_chars = len(best.chunk.text)
            if selected and selected_chars + chunk_chars > section.max_chars:
                continue
            selected.append(best)
            selected_sources.add(best.chunk.source_id)
            selected_chars += chunk_chars

        if not selected and candidates:
            selected = [candidates[0]]
        hits = [
            EvidenceHit(
                rank=index,
                chunk=item.chunk,
                score=item.score,
                reasons=item.reasons,
            )
            for index, item in enumerate(selected, start=1)
        ]
        return RetrievalResult(hits=hits, backend=backend, warnings=warnings)

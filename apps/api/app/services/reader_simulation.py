from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.writing_agent_schemas import TitleCandidateOutput
from app.services.retrieval import lexical_terms, term_similarity


class StrictReaderSimulationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReaderScoreBreakdown(StrictReaderSimulationModel):
    topic_clarity: float = Field(ge=0, le=25)
    value_promise: float = Field(ge=0, le=25)
    specificity: float = Field(ge=0, le=20)
    first_glance: float = Field(ge=0, le=20)
    naturalness: float = Field(ge=0, le=10)


class ReaderFirstGlance(StrictReaderSimulationModel):
    candidate_id: str = Field(min_length=1, max_length=120)
    understood_topic: str = Field(min_length=1, max_length=300)
    expected_value: str = Field(min_length=1, max_length=500)
    trust_risk: str = Field(default="", max_length=500)
    breakdown: ReaderScoreBreakdown
    total_score: float = Field(ge=0, le=100)


class ReaderSimulationReport(StrictReaderSimulationModel):
    simulator_version: Literal["reader-first-glance-v1"] = "reader-first-glance-v1"
    audience: str = Field(min_length=1, max_length=2000)
    assessments: list[ReaderFirstGlance] = Field(default_factory=list, max_length=20)


class ReaderSimulationService:
    """Deterministic first-glance scoring; it never invents factual support."""

    version = "reader-first-glance-v1"

    @staticmethod
    def _compact(value: str, limit: int) -> str:
        compacted = re.sub(r"\s+", " ", str(value or "")).strip()
        return compacted if len(compacted) <= limit else compacted[: limit - 1].rstrip() + "…"

    @staticmethod
    def _length_score(title: str) -> float:
        compacted = re.sub(r"\s+", "", title)
        length = len(compacted)
        if 12 <= length <= 28:
            return 20.0
        if 8 <= length <= 36:
            return 16.0
        if 5 <= length <= 45:
            return 11.0
        return 5.0

    @staticmethod
    def _specificity_score(title: str) -> float:
        terms = lexical_terms(title)
        score = min(len(terms) * 0.7, 14.0)
        if re.search(r"\d|[一二三四五六七八九十]+(?=个|步|类|种|次)", title):
            score += 3.0
        if re.search(r"为什么|如何|怎样|哪|什么", title):
            score += 2.0
        return min(score, 20.0)

    def simulate(
        self,
        candidates: list[TitleCandidateOutput],
        *,
        audience: str,
        promise: str,
        thesis: str,
        filter_reasons: dict[str, list[str]] | None = None,
    ) -> ReaderSimulationReport:
        reasons_by_id = filter_reasons or {}
        context = f"{promise} {thesis}".strip()
        assessments: list[ReaderFirstGlance] = []
        for candidate in candidates:
            topic_similarity = term_similarity(candidate.title, context)
            promise_similarity = term_similarity(candidate.reader_promise, context)
            topic_score = min(topic_similarity * 55.0, 25.0)
            value_score = min(promise_similarity * 45.0, 20.0)
            if candidate.mechanism in {"result", "conflict", "counterintuitive", "judgment"}:
                value_score += 5.0
            specificity = self._specificity_score(candidate.title)
            first_glance = self._length_score(candidate.title)
            naturalness = 10.0
            if candidate.title.count("？") + candidate.title.count("?") > 1:
                naturalness -= 3.0
            if candidate.title.count("！") + candidate.title.count("!"):
                naturalness -= 3.0
            if re.search(r"[：:——-]{2,}", candidate.title):
                naturalness -= 2.0
            rejected = reasons_by_id.get(candidate.candidate_id, [])
            penalty = min(len(rejected) * 15.0, 45.0)
            total = max(
                0.0,
                min(
                    topic_score + value_score + specificity + first_glance + naturalness - penalty,
                    100.0,
                ),
            )
            assessments.append(
                ReaderFirstGlance(
                    candidate_id=candidate.candidate_id,
                    understood_topic=self._compact(candidate.title, 300),
                    expected_value=self._compact(candidate.reader_promise, 500),
                    trust_risk="；".join(rejected),
                    breakdown=ReaderScoreBreakdown(
                        topic_clarity=round(topic_score, 4),
                        value_promise=round(value_score, 4),
                        specificity=round(specificity, 4),
                        first_glance=round(first_glance, 4),
                        naturalness=round(max(naturalness, 0.0), 4),
                    ),
                    total_score=round(total, 4),
                )
            )
        assessments.sort(key=lambda item: (-item.total_score, item.candidate_id))
        return ReaderSimulationReport(
            audience=self._compact(audience, 2000) or "目标读者",
            assessments=assessments,
        )

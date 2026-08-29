from __future__ import annotations

import re
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.writing_agent_schemas import TitleCandidateOutput, TitleCandidatesOutput
from app.services.reader_simulation import ReaderFirstGlance, ReaderSimulationService
from app.services.retrieval import term_similarity


class StrictTitleTournamentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TitleCandidateEvaluation(StrictTitleTournamentModel):
    candidate: TitleCandidateOutput
    matched_evidence_refs: list[str] = Field(default_factory=list, max_length=8)
    filter_reasons: list[str] = Field(default_factory=list, max_length=12)
    reader_first_glance: ReaderFirstGlance
    eligible: bool


class TitleTournamentResult(StrictTitleTournamentModel):
    schema_version: Literal[1] = 1
    tournament_version: Literal["title-tournament-v1"] = "title-tournament-v1"
    reader_simulator_version: Literal["reader-first-glance-v1"] = (
        "reader-first-glance-v1"
    )
    source_artifact_id: str = Field(default="", max_length=160)
    candidate_count: int = Field(ge=12, le=20)
    eligible_count: int = Field(ge=0, le=20)
    top_five: list[TitleCandidateEvaluation] = Field(default_factory=list, max_length=5)
    evaluations: list[TitleCandidateEvaluation] = Field(min_length=12, max_length=20)
    filter_summary: dict[str, int] = Field(default_factory=dict)
    quality_gate_passed: bool

    @model_validator(mode="after")
    def counts_match_candidates(self) -> TitleTournamentResult:
        if self.candidate_count != len(self.evaluations):
            raise ValueError("title tournament candidate count does not match evaluations")
        if self.eligible_count != sum(item.eligible for item in self.evaluations):
            raise ValueError("title tournament eligible count does not match evaluations")
        top_ids = [item.candidate.candidate_id for item in self.top_five]
        if len(top_ids) != len(set(top_ids)):
            raise ValueError("title tournament top five contains duplicate candidates")
        if any(not item.eligible for item in self.top_five):
            raise ValueError("title tournament top five may contain only eligible candidates")
        if self.quality_gate_passed != (len(self.top_five) == 5):
            raise ValueError("title tournament quality gate does not match top five")
        return self


class TitleTournamentService:
    version = "title-tournament-v1"
    homogeneity_threshold = 0.72
    _EMPTY_PROMISE_PATTERNS = (
        r"一文读懂",
        r"看完就懂",
        r"值得关注",
        r"你需要知道",
        r"全面解析",
        r"终极指南",
        r"干货满满",
    )
    _CLICKBAIT_PATTERNS = (
        r"震惊",
        r"万万没想到",
        r"绝对想不到",
        r"秘密竟然",
        r"不看后悔",
        r"颠覆认知",
        r"真相了",
    )
    _CLICHE_PATTERNS = (
        r"底层逻辑",
        r"破局",
        r"赋能",
        r"新范式",
        r"时代已经来临",
        r"天花板",
        r"王炸",
        r"降维打击",
    )
    _OVERCLAIM_PATTERNS = (
        r"彻底",
        r"所有人",
        r"百分百",
        r"零风险",
        r"绝不会",
        r"行业第一",
        r"史上最",
        r"重新定义",
    )

    @staticmethod
    def _normalized(value: str) -> str:
        return re.sub(r"\s+", "", str(value or "")).lower()

    @classmethod
    def evidence_chunks(cls, payload: object) -> dict[str, str]:
        output: dict[str, str] = {}

        def visit(value: object) -> None:
            if isinstance(value, dict):
                evidence_ref = str(value.get("evidence_ref") or "")
                text = str(value.get("text") or "")
                if evidence_ref and text:
                    output.setdefault(evidence_ref, text)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(payload)
        return output

    @classmethod
    def _base_filter_reasons(
        cls,
        candidate: TitleCandidateOutput,
        evidence: dict[str, str],
    ) -> tuple[list[str], list[str]]:
        reasons: list[str] = []
        matched = [ref for ref in candidate.evidence_refs if ref in evidence]
        if not candidate.evidence_refs or not matched:
            reasons.append("EVIDENCE_MISSING")
        if len(matched) != len(candidate.evidence_refs):
            reasons.append("EVIDENCE_REF_UNKNOWN")
        cited_text = " ".join(evidence[ref] for ref in matched)
        if matched and max(
            term_similarity(candidate.title, cited_text),
            term_similarity(candidate.reader_promise, cited_text),
        ) < 0.08:
            reasons.append("EVIDENCE_MISMATCH")
        title_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", candidate.title))
        cited_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", cited_text))
        if title_numbers - cited_numbers:
            reasons.append("UNSUPPORTED_NUMBER")
        chinese_numbers = set(
            re.findall(
                r"[零〇一二两三四五六七八九十百千万]+(?=个|步|类|种|次|层|项|条|点|方面|问题)",
                candidate.title,
            )
        )
        if any(number not in cited_text for number in chinese_numbers):
            reasons.append("UNSUPPORTED_NUMBER")
        if any(re.search(pattern, candidate.title, re.IGNORECASE) for pattern in cls._EMPTY_PROMISE_PATTERNS):
            reasons.append("EMPTY_PROMISE")
        if any(re.search(pattern, candidate.title, re.IGNORECASE) for pattern in cls._CLICKBAIT_PATTERNS):
            reasons.append("OVER_CURIOSITY")
        if any(re.search(pattern, candidate.title, re.IGNORECASE) for pattern in cls._CLICHE_PATTERNS):
            reasons.append("CLICHE")
        if any(re.search(pattern, candidate.title, re.IGNORECASE) for pattern in cls._OVERCLAIM_PATTERNS):
            normalized_evidence = cls._normalized(cited_text)
            if not any(
                cls._normalized(match.group(0)) in normalized_evidence
                for pattern in cls._OVERCLAIM_PATTERNS
                for match in re.finditer(pattern, candidate.title, re.IGNORECASE)
            ):
                reasons.append("UNSUPPORTED_PROMISE")
        return list(dict.fromkeys(reasons)), matched

    def evaluate(
        self,
        output: TitleCandidatesOutput,
        *,
        evidence_payload: object,
        audience: str,
        promise: str,
        thesis: str,
        source_artifact_id: str = "",
    ) -> TitleTournamentResult:
        evidence = self.evidence_chunks(evidence_payload)
        reasons_by_id: dict[str, list[str]] = {}
        matched_by_id: dict[str, list[str]] = {}
        earlier: list[TitleCandidateOutput] = []
        for candidate in output.candidates:
            reasons, matched = self._base_filter_reasons(candidate, evidence)
            for previous in earlier:
                if (
                    term_similarity(candidate.title, previous.title)
                    >= self.homogeneity_threshold
                ):
                    reasons.append(f"HOMOGENEOUS_WITH:{previous.candidate_id}")
                    break
            reasons_by_id[candidate.candidate_id] = list(dict.fromkeys(reasons))
            matched_by_id[candidate.candidate_id] = matched
            earlier.append(candidate)

        simulation = ReaderSimulationService().simulate(
            output.candidates,
            audience=audience,
            promise=promise,
            thesis=thesis,
            filter_reasons=reasons_by_id,
        )
        assessment_by_id = {item.candidate_id: item for item in simulation.assessments}
        evaluations = [
            TitleCandidateEvaluation(
                candidate=candidate,
                matched_evidence_refs=matched_by_id[candidate.candidate_id],
                filter_reasons=reasons_by_id[candidate.candidate_id],
                reader_first_glance=assessment_by_id[candidate.candidate_id],
                eligible=not reasons_by_id[candidate.candidate_id],
            )
            for candidate in output.candidates
        ]
        ranked = sorted(
            (item for item in evaluations if item.eligible),
            key=lambda item: (
                -item.reader_first_glance.total_score,
                item.candidate.candidate_id,
            ),
        )
        top_five: list[TitleCandidateEvaluation] = []
        mechanisms: Counter[str] = Counter()
        for item in ranked:
            mechanism = item.candidate.mechanism
            if mechanisms[mechanism] or len(top_five) >= 5:
                continue
            top_five.append(item)
            mechanisms[mechanism] += 1
        for item in ranked:
            if len(top_five) >= 5:
                break
            if item in top_five or mechanisms[item.candidate.mechanism] >= 2:
                continue
            top_five.append(item)
            mechanisms[item.candidate.mechanism] += 1
        # Diversity is a ranking preference, not a reason to discard an
        # otherwise evidence-backed finalist. Fill the remaining places after
        # the diverse passes so five eligible candidates always produce top 5.
        for item in ranked:
            if len(top_five) >= 5:
                break
            if item in top_five:
                continue
            top_five.append(item)
            mechanisms[item.candidate.mechanism] += 1
        summary = Counter(reason for reasons in reasons_by_id.values() for reason in reasons)
        return TitleTournamentResult(
            source_artifact_id=source_artifact_id,
            candidate_count=len(evaluations),
            eligible_count=sum(item.eligible for item in evaluations),
            top_five=top_five,
            evaluations=evaluations,
            filter_summary=dict(sorted(summary.items())),
            quality_gate_passed=len(top_five) == 5,
        )

    @staticmethod
    def selected_candidate(
        tournament: TitleTournamentResult | dict[str, Any],
        candidate_id: str,
    ) -> TitleCandidateEvaluation:
        parsed = (
            tournament
            if isinstance(tournament, TitleTournamentResult)
            else TitleTournamentResult.model_validate(tournament)
        )
        if not parsed.quality_gate_passed:
            raise ValueError("标题锦标赛不足五个合格候选，不能记录人工选择")
        for item in parsed.top_five:
            if item.candidate.candidate_id == candidate_id:
                return item
        raise ValueError("只能从当前 title tournament 的 top 5 中选择标题")

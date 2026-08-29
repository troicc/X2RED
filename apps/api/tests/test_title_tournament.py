from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.domain.models import SourceItem
from app.domain.studio import WritingArtifact, WritingProject
from app.domain.writing_agent_schemas import (
    TitleCandidatesOutput,
    WritingAgentContractError,
    validate_agent_payload,
)
from app.services.editorial import EditorialService
from app.services.title_tournament import TitleTournamentService
from app.services.writing_studio import MultiAgentWritingService


def _candidate(
    index: int,
    title: str,
    mechanism: str,
    *,
    evidence_refs: list[str] | None = None,
) -> dict:
    return {
        "candidate_id": f"title-{index:02d}",
        "title": title,
        "mechanism": mechanism,
        "reader_promise": "读者将看到本地证据检索如何约束事实主张",
        "evidence_refs": evidence_refs or ["src:chunk-main"],
    }


def _candidates() -> TitleCandidatesOutput:
    return TitleCandidatesOutput.model_validate(
        {
            "candidates": [
                _candidate(1, "本地证据检索让文章末尾证据不再漏掉", "result"),
                _candidate(2, "检索范围更大，为什么事实边界反而要更窄", "conflict"),
                _candidate(3, "证据越多，越不能让标题承诺更多", "counterintuitive"),
                _candidate(4, "当尾段证据进入真实写作流程之后", "scene"),
                _candidate(5, "文章末尾的关键证据为什么总被漏掉", "question"),
                _candidate(6, "三个检索步骤如何守住事实边界", "number"),
                _candidate(7, "好标题先尊重证据，再争取注意力", "judgment"),
                _candidate(8, "一文读懂本地证据检索", "result"),
                _candidate(9, "震惊：证据检索的秘密竟然在这里", "question"),
                _candidate(10, "证据检索如何成为写作破局新范式", "judgment"),
                _candidate(11, "9个检索步骤解决文章证据遗漏", "number"),
                _candidate(12, "证据检索彻底解决所有事实问题", "result"),
                _candidate(
                    13,
                    "来源引用如何进入每一条事实主张",
                    "scene",
                    evidence_refs=["src:missing"],
                ),
                _candidate(14, "本地证据检索让文章尾部证据不再漏掉", "result"),
            ]
        }
    )


def _evidence() -> dict:
    return {
        "sections": [
            {
                "evidence_chunks": [
                    {
                        "evidence_ref": "src:chunk-main",
                        "text": (
                            "本地证据检索让文章末尾和尾段证据不再漏掉。检索范围扩大后，"
                            "事实边界仍要收窄；标题只能承诺来源支持的结果。真实写作流程按三个"
                            "检索步骤检查关键证据、来源引用和事实主张，好标题先尊重证据再争取注意力。"
                        ),
                    }
                ]
            }
        ]
    }


def test_title_tournament_filters_risk_and_returns_diverse_top_five() -> None:
    service = TitleTournamentService()
    first = service.evaluate(
        _candidates(),
        evidence_payload=_evidence(),
        audience="需要可靠技术解释的读者",
        promise="讲清本地证据检索如何避免遗漏并约束事实边界",
        thesis="标题承诺不能超出当前证据",
        source_artifact_id="artifact-title-candidates",
    )
    second = service.evaluate(
        _candidates(),
        evidence_payload=_evidence(),
        audience="需要可靠技术解释的读者",
        promise="讲清本地证据检索如何避免遗漏并约束事实边界",
        thesis="标题承诺不能超出当前证据",
        source_artifact_id="artifact-title-candidates",
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.candidate_count == 14
    assert first.quality_gate_passed is True
    assert len(first.top_five) == 5
    assert len({item.candidate.mechanism for item in first.top_five}) == 5
    assert all(item.eligible for item in first.top_five)
    assert first.filter_summary["EMPTY_PROMISE"] >= 1
    assert first.filter_summary["OVER_CURIOSITY"] >= 1
    assert first.filter_summary["CLICHE"] >= 1
    assert first.filter_summary["UNSUPPORTED_NUMBER"] >= 1
    assert first.filter_summary["UNSUPPORTED_PROMISE"] >= 1
    assert first.filter_summary["EVIDENCE_REF_UNKNOWN"] >= 1
    assert any(key.startswith("HOMOGENEOUS_WITH:") for key in first.filter_summary)

    selected = service.selected_candidate(first, first.top_five[0].candidate.candidate_id)
    assert selected.candidate.title == first.top_five[0].candidate.title
    with pytest.raises(ValueError, match="top 5"):
        service.selected_candidate(first, "title-08")


def test_title_tournament_fills_top_five_after_diversity_passes() -> None:
    candidates = _candidates().model_copy(deep=True)
    for item in candidates.candidates:
        if item.candidate_id in {"title-03", "title-04", "title-05", "title-06", "title-07"}:
            item.evidence_refs = ["src:missing"]
    replacements = {
        "title-08": ("来源引用进入正文后，证据遗漏如何减少", "result"),
        "title-09": ("检索更完整，标题为什么仍要克制", "conflict"),
        "title-10": ("事实边界收窄后，文章更容易核对", "result"),
        "title-11": ("来源越多，证据责任为什么越具体", "conflict"),
        "title-12": ("事实主张回到来源引用，核对不再失焦", "result"),
    }
    for item in candidates.candidates:
        replacement = replacements.get(item.candidate_id)
        if replacement:
            item.title, item.mechanism = replacement
    result = TitleTournamentService().evaluate(
        candidates,
        evidence_payload=_evidence(),
        audience="需要可靠技术解释的读者",
        promise="讲清本地证据检索如何避免遗漏并约束事实边界",
        thesis="标题承诺不能超出当前证据",
    )
    assert result.eligible_count >= 5
    assert len(result.top_five) == 5
    assert result.quality_gate_passed is True


def test_title_preference_rejects_degraded_tournament() -> None:
    candidates = _candidates().model_copy(deep=True)
    for item in candidates.candidates[2:]:
        item.evidence_refs = ["src:missing"]
    result = TitleTournamentService().evaluate(
        candidates,
        evidence_payload=_evidence(),
        audience="技术读者",
        promise="讲清检索与事实边界",
        thesis="标题不能扩大事实",
    )
    assert result.quality_gate_passed is False
    with pytest.raises(ValueError, match="不足五个"):
        TitleTournamentService.selected_candidate(
            result,
            result.top_five[0].candidate.candidate_id,
        )


def test_human_title_preference_is_immutable_and_stale_tournament_is_rejected() -> None:
    import app.domain.discovery  # noqa: F401 - register all FK targets for create_all

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        database_url="sqlite:///:memory:",
        writing_quality_mode="production",
    )
    writing = MultiAgentWritingService(settings, EditorialService(settings))
    tournament = TitleTournamentService().evaluate(
        _candidates(),
        evidence_payload=_evidence(),
        audience="技术读者",
        promise="讲清检索与事实边界",
        thesis="标题不能扩大事实",
    )
    with Session(engine) as db:
        source = SourceItem(
            provider="manual",
            platform="web",
            external_id="title-preference-source",
            canonical_url="https://example.invalid/title-preference",
            text_original="本地证据检索与标题事实边界。",
        )
        db.add(source)
        db.flush()
        project = WritingProject(
            source_id=source.id,
            reader="技术读者",
            promise="讲清检索",
            main_thesis="标题不能扩大事实",
        )
        db.add(project)
        db.flush()
        serialized = json.dumps(tournament.model_dump(mode="json"), ensure_ascii=False)
        artifact = WritingArtifact(
            project_id=project.id,
            artifact_type="title_tournament",
            version=1,
            content_json=serialized,
            content_hash=hashlib.sha256(serialized.encode()).hexdigest(),
            created_by_role="reader_simulator",
        )
        db.add(artifact)
        db.flush()

        candidate = tournament.top_five[1].candidate
        preference = writing.select_title_preference(
            db,
            project=project,
            tournament_artifact_id=artifact.id,
            candidate_id=candidate.candidate_id,
            note="作者盲选后更偏好这个角度",
        )
        payload = json.loads(preference.content_json)
        assert payload["selection_source"] == "human"
        assert payload["title"] == candidate.title
        assert artifact.approved is True
        assert writing._selected_title_payload(db, project)["title"] == candidate.title

        newer = WritingArtifact(
            project_id=project.id,
            artifact_type="title_tournament",
            version=2,
            content_json=serialized,
            content_hash=hashlib.sha256((serialized + "v2").encode()).hexdigest(),
            created_by_role="reader_simulator",
        )
        db.add(newer)
        db.flush()
        with pytest.raises(ValueError, match="已经更新"):
            writing.select_title_preference(
                db,
                project=project,
                tournament_artifact_id=artifact.id,
                candidate_id=candidate.candidate_id,
                note="过期选择",
            )


def test_selected_title_contract_rejects_writer_or_final_rewrite() -> None:
    payload = {"title": "另一个标题", "body": "正文", "tags": [], "claims": []}
    with pytest.raises(WritingAgentContractError, match="preserve the selected title"):
        validate_agent_payload(
            "draft",
            payload,
            context={"required_title": "作者已经选择的标题"},
        )
    final = {**payload, "applied_changes": []}
    with pytest.raises(WritingAgentContractError, match="preserve the selected title"):
        validate_agent_payload(
            "final_draft",
            final,
            context={"required_title": "作者已经选择的标题"},
        )

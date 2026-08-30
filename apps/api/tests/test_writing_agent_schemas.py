from __future__ import annotations

import hashlib
import importlib
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.domain.models import SourceItem
from app.domain.studio import AgentRun, AgentRunStatus, WritingProject
from app.domain.writing_agent_schemas import (
    ARTIFACT_SCHEMAS,
    WritingAgentContractError,
    validate_agent_payload,
)
from app.services.editorial import EditorialService
from app.services.model_client import StructuredOutputError
from app.services.writing_studio import MultiAgentWritingService


def _location(quote: str = "原句") -> dict:
    return {"section": "第一节", "paragraph_index": 1, "quote": quote}


def _claim(*, claim_id: str = "claim-001") -> dict:
    return {
        "claim_id": claim_id,
        "statement": "证据支持这条主张",
        "location": _location("这条主张"),
        "claim_type": "fact",
        "importance": "critical",
        "evidence_refs": ["source-1:chunk-1"],
        "evidence_quote": "证据支持这条主张",
    }


def _review_issue(prefix: str = "fact-") -> dict:
    return {
        "issue_id": f"{prefix}001",
        "category": "unsupported_claim",
        "location": _location("这条主张"),
        "severity": "critical",
        "message": "主张缺少足够证据",
        "evidence_refs": ["source-1:chunk-1"],
        "evidence_quote": "证据原文",
        "minimal_fix": "删除扩大范围的词语",
    }


def _representative_payloads() -> dict[str, dict]:
    review = {"verdict": "needs_revision", "issues": [_review_issue()], "strong_parts": []}
    return {
        "editorial_brief": {
            "reader": "技术读者",
            "article_promise": "讲清主张",
            "main_thesis": "证据决定边界",
            "reader_hook": "先看结论",
            "must_use": [],
            "must_not_claim": [],
            "article_type": "explain",
            "tone": "直接",
            "open_questions": [],
            "success_criteria": [],
        },
        "title_candidates": {
            "candidates": [
                {
                    "candidate_id": f"title-{index:02d}",
                    "title": f"证据支持的标题候选第{index}种角度",
                    "mechanism": (
                        "result",
                        "conflict",
                        "counterintuitive",
                        "scene",
                        "question",
                        "number",
                        "judgment",
                    )[(index - 1) % 7],
                    "reader_promise": "讲清证据如何约束文章主张",
                    "evidence_refs": ["source-1:chunk-1"],
                }
                for index in range(1, 13)
            ]
        },
        "evidence_pack": {
            "facts": [],
            "author_claims": [],
            "unknowns": [],
            "numbers": [],
            "terms": [],
            "source_map": [],
            "material_gaps": [],
            "usable_examples": [],
            "claims_for_draft": [],
        },
        "outline": {
            "opening": {},
            "sections": [],
            "ending": {},
            "cognitive_load_plan": [],
            "terms_first_use": [],
            "evidence_allocation": [],
            "transitions": [],
            "forbidden_moves": [],
        },
        "draft": {"title": "标题", "body": "这条主张", "tags": [], "claims": [_claim()]},
        "reader_review": {"verdict": "pass", "issues": [], "strong_parts": []},
        "fact_review": review,
        "style_review": {"verdict": "pass", "issues": [], "strong_parts": []},
        "revision_plan": {
            "decisions": [
                {
                    "issue_id": "fact-001",
                    "decision": "approve",
                    "reason": "事实问题必须修复",
                    "approved_fix": "删除扩大范围的词语",
                }
            ],
            "release_readiness": "needs_revision",
            "rationale": "修复后可发布",
        },
        "final_draft": {
            "title": "标题",
            "body": "这条主张",
            "tags": [],
            "claims": [_claim()],
            "applied_changes": [
                {
                    "issue_id": "fact-001",
                    "before": "扩大范围的主张",
                    "after": "这条主张",
                    "description": "收窄事实范围",
                }
            ],
        },
        "final_claims": {
            "claims": [
                {
                    **_claim(claim_id="final-claim-001"),
                    "exact_quote": "这条主张",
                    "origin_claim_id": "claim-001",
                    "approved_issue_ids": ["fact-001"],
                }
            ]
        },
    }


def test_every_writing_agent_schema_is_strict_and_replayable() -> None:
    payloads = _representative_payloads()
    assert set(payloads) == set(ARTIFACT_SCHEMAS)
    contexts = {
        "title_candidates": {"allowed_evidence_refs": ["source-1:chunk-1"]},
        "reader_review": {"issue_id_prefix": "reader-"},
        "fact_review": {"issue_id_prefix": "fact-"},
        "style_review": {"issue_id_prefix": "style-"},
        "revision_plan": {"allowed_issue_ids": ["fact-001"]},
        "final_draft": {
            "approved_issue_ids": ["fact-001"],
            "required_issue_ids": ["fact-001"],
            "required_title": "标题",
        },
        "final_claims": {
            "initial_claim_ids": ["claim-001"],
            "approved_issue_ids": ["fact-001"],
        },
    }
    for artifact_type, payload in payloads.items():
        parsed = validate_agent_payload(
            artifact_type,
            payload,
            context=contexts.get(artifact_type),
        )
        replayed = parsed.model_dump(mode="json")
        assert ARTIFACT_SCHEMAS[artifact_type].model_validate(replayed) == parsed
        serialized = json.dumps(replayed, ensure_ascii=False, sort_keys=True)
        assert len(hashlib.sha256(serialized.encode()).hexdigest()) == 64

    invalid = dict(payloads["editorial_brief"], unexpected="forbidden")
    with pytest.raises(ValidationError):
        validate_agent_payload("editorial_brief", invalid)


def test_review_chief_and_final_contracts_reject_untraceable_actions() -> None:
    issue = _review_issue()
    issue["location"] = {"section": "", "paragraph_index": None, "quote": ""}
    issue["evidence_refs"] = []
    issue["evidence_quote"] = ""
    with pytest.raises(ValidationError):
        validate_agent_payload(
            "fact_review",
            {"verdict": "blocked", "issues": [issue], "strong_parts": []},
            context={"issue_id_prefix": "fact-"},
        )

    grounded_issue = _review_issue()
    with pytest.raises(WritingAgentContractError, match="invented evidence refs"):
        validate_agent_payload(
            "fact_review",
            {"verdict": "blocked", "issues": [grounded_issue], "strong_parts": []},
            context={
                "issue_id_prefix": "fact-",
                "allowed_evidence_refs": ["source-1:chunk-allowed"],
            },
        )

    plan = _representative_payloads()["revision_plan"]
    with pytest.raises(WritingAgentContractError, match="invented issue ids"):
        validate_agent_payload(
            "revision_plan",
            plan,
            context={"allowed_issue_ids": ["reader-001"]},
        )

    final = _representative_payloads()["final_draft"]
    with pytest.raises(WritingAgentContractError, match="unapproved issue ids"):
        validate_agent_payload(
            "final_draft",
            final,
            context={"approved_issue_ids": [], "required_issue_ids": []},
        )
    with pytest.raises(WritingAgentContractError, match="skipped required issue ids"):
        validate_agent_payload(
            "final_draft",
            {**final, "applied_changes": []},
            context={
                "approved_issue_ids": ["fact-001"],
                "required_issue_ids": ["fact-001"],
            },
        )
    with pytest.raises(ValidationError, match="each issue id exactly once"):
        validate_agent_payload(
            "final_draft",
            {**final, "applied_changes": [*final["applied_changes"], *final["applied_changes"]]},
            context={
                "approved_issue_ids": ["fact-001"],
                "required_issue_ids": ["fact-001"],
            },
        )

    claims = _representative_payloads()["final_claims"]
    with pytest.raises(WritingAgentContractError, match="invented origin claim ids"):
        validate_agent_payload(
            "final_claims",
            claims,
            context={
                "initial_claim_ids": ["another-claim"],
                "approved_issue_ids": ["fact-001"],
            },
        )


def _writing_service() -> tuple[Session, MultiAgentWritingService, WritingProject]:
    for module_name in (
        "app.domain.discovery",
        "app.domain.jobs",
        "app.domain.platforms",
        "app.domain.review_artifacts",
        "app.domain.style_snapshot",
    ):
        importlib.import_module(module_name)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    settings = Settings(
        model_base_url="https://model.example/v1",
        model_name="test-model",
        model_api_key="test-key",
        writing_schema_mode="production",
    )
    service = MultiAgentWritingService(settings, EditorialService(settings))
    source = SourceItem(
        provider="manual",
        platform="manual",
        external_id="schema-repair-source",
        canonical_url="manual://schema-repair-source",
        author_handle="author",
        author_name="Author",
        content_kind="article",
        text_original="用于结构化输出修复测试的来源。",
        metrics_json="{}",
    )
    db.add(source)
    db.flush()
    project = service.create_project(
        db,
        source=source,
        mode="fast",
        reader="技术读者",
        promise="讲清事实",
        main_thesis="证据决定边界",
        style_profile_id=None,
        budget_limit_cents=20,
    )
    db.commit()
    db.refresh(project)
    return db, service, project


@pytest.mark.asyncio
async def test_schema_failure_gets_exactly_one_repair_and_replays() -> None:
    db, service, project = _writing_service()
    calls = 0

    async def fake_chat_json(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise StructuredOutputError(
                "模型没有返回有效 JSON",
                raw_content="```json\n{broken\n```",
            )
        return _representative_payloads()["editorial_brief"]

    service.editorial._chat_json = fake_chat_json  # type: ignore[method-assign]
    try:
        artifact = await service._run_agent(
            db,
            project=project,
            role="editor_in_chief",
            stage="editorial_brief",
            artifact_type="editorial_brief",
            system_prompt="system",
            user_prompt="user",
            temperature=0.1,
        )
        payload = json.loads(artifact.content_json)
        trace = payload.pop("_structured_output")
        assert calls == 2
        assert trace["status"] == "repaired"
        assert trace["repair_attempted"] is True
        assert trace["validation_errors"]
        validated = validate_agent_payload("editorial_brief", payload)
        serialized = json.dumps(
            validated.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
        )
        assert hashlib.sha256(serialized.encode()).hexdigest() == trace["payload_sha256"]
        run = db.scalar(select(AgentRun).where(AgentRun.project_id == project.id))
        assert run is not None
        assert run.attempts == 2
        assert run.status == AgentRunStatus.succeeded.value
    finally:
        db.close()


@pytest.mark.asyncio
async def test_second_schema_failure_is_explicit_and_never_stored_as_success() -> None:
    db, service, project = _writing_service()
    calls = 0

    async def always_invalid(**_kwargs):
        nonlocal calls
        calls += 1
        return {"reader": "仍然缺字段"}

    service.editorial._chat_json = always_invalid  # type: ignore[method-assign]
    try:
        with pytest.raises(ValidationError):
            await service._run_agent(
                db,
                project=project,
                role="editor_in_chief",
                stage="editorial_brief",
                artifact_type="editorial_brief",
                system_prompt="system",
                user_prompt="user",
                temperature=0.1,
            )
        assert calls == 2
        run = db.scalar(select(AgentRun).where(AgentRun.project_id == project.id))
        assert run is not None
        assert run.attempts == 2
        assert run.status == AgentRunStatus.failed.value
        assert run.output_artifact_id is None
        usage = json.loads(run.usage_json)
        assert usage["structured_output"]["repair_attempted"] is True
        assert len(usage["structured_output"]["validation_errors"]) == 2
    finally:
        db.close()

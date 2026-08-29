from __future__ import annotations

import importlib
import json
import types

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.domain.models import SourceItem
from app.domain.studio import WritingProject, WritingState
from app.domain.writing_agent_schemas import FinalClaimsOutput
from app.services.claim_checker import ClaimChecker
from app.services.editorial import EditorialService
from app.services.writing_studio import MultiAgentWritingService

EVIDENCE_REF = "source-1:chunk-1"
EVIDENCE_TEXT = "本地测试显示处理耗时下降百分之二十，但结论只适用于当前样本。"


def _evidence() -> dict:
    return {
        "sections": [
            {
                "section_id": "facts",
                "evidence_chunks": [
                    {
                        "evidence_ref": EVIDENCE_REF,
                        "text": EVIDENCE_TEXT,
                    }
                ],
            }
        ]
    }


def _extraction(
    *,
    importance: str = "critical",
    evidence_refs: list[str] | None = None,
    evidence_quote: str = EVIDENCE_TEXT,
    origin_claim_id: str = "claim-001",
    approved_issue_ids: list[str] | None = None,
    exact_quote: str = "处理耗时下降百分之二十",
) -> FinalClaimsOutput:
    return FinalClaimsOutput.model_validate(
        {
            "claims": [
                {
                    "claim_id": "final-claim-001",
                    "statement": "处理耗时下降百分之二十",
                    "exact_quote": exact_quote,
                    "location": {"section": "结果", "quote": exact_quote},
                    "claim_type": "number",
                    "importance": importance,
                    "evidence_refs": evidence_refs if evidence_refs is not None else [EVIDENCE_REF],
                    "evidence_quote": evidence_quote,
                    "origin_claim_id": origin_claim_id,
                    "approved_issue_ids": approved_issue_ids or [],
                }
            ]
        }
    )


def _evaluate(extraction: FinalClaimsOutput, *, approved: set[str] | None = None):
    return ClaimChecker().evaluate(
        final_artifact_id="artifact-final",
        final_claims_artifact_id="artifact-claims",
        final_body="## 结果\n\n处理耗时下降百分之二十，但不能扩大到其他样本。",
        extraction=extraction,
        evidence_retrieval=_evidence(),
        initial_claims=[
            {
                "claim_id": "claim-001",
                "statement": "处理耗时下降百分之二十",
            }
        ],
        approved_issue_ids=approved or set(),
    )


def test_supported_critical_claim_is_traceable_and_allowed() -> None:
    matrix = _evaluate(_extraction())
    assert matrix.completion_allowed is True
    assert matrix.supported_claims == 1
    assert matrix.critical_unsupported_claims == 0
    assert matrix.rows[0].support_status == "supported"
    assert matrix.rows[0].scope_status == "preserved"


def test_critical_unsupported_claim_blocks_completion() -> None:
    matrix = _evaluate(_extraction(evidence_refs=[], evidence_quote=""))
    assert matrix.completion_allowed is False
    assert matrix.critical_unsupported_claims == 1
    assert "CRITICAL_CLAIM_UNSUPPORTED" in matrix.rows[0].blocking_reasons


def test_real_quote_cannot_support_an_unrelated_claim() -> None:
    extraction = _extraction()
    extraction.claims[0].statement = "月球由奶酪构成"
    extraction.claims[0].exact_quote = "月球由奶酪构成"
    extraction.claims[0].location.quote = "月球由奶酪构成"
    matrix = ClaimChecker().evaluate(
        final_artifact_id="artifact-final",
        final_claims_artifact_id="artifact-claims",
        final_body="月球由奶酪构成",
        extraction=extraction,
        evidence_retrieval=_evidence(),
        initial_claims=[
            {
                "claim_id": "claim-001",
                "statement": "月球由奶酪构成",
            }
        ],
        approved_issue_ids=set(),
    )
    row = matrix.rows[0]
    assert row.evidence_quote_verified is True
    assert row.semantic_support == 0
    assert row.final_quote_verified is True
    assert row.support_status == "partial"
    assert matrix.critical_unsupported_claims == 1
    assert matrix.completion_allowed is False


def test_supported_major_claim_still_blocks_unauthorized_expansion() -> None:
    extraction = _extraction(
        importance="major",
        origin_claim_id="",
        approved_issue_ids=[],
    )
    matrix = _evaluate(extraction)
    assert matrix.rows[0].support_status == "supported"
    assert matrix.rows[0].scope_status == "new_claim"
    assert matrix.unauthorized_major_expansions == 1
    assert matrix.completion_allowed is False


def test_unsupported_major_claim_blocks_completion() -> None:
    matrix = _evaluate(
        _extraction(
            importance="major",
            evidence_refs=[],
            evidence_quote="",
        )
    )
    assert matrix.major_unsupported_claims == 1
    assert "MAJOR_CLAIM_UNSUPPORTED" in matrix.rows[0].blocking_reasons
    assert matrix.completion_allowed is False


def test_approved_revision_can_add_supported_major_claim() -> None:
    extraction = _extraction(
        importance="major",
        origin_claim_id="",
        approved_issue_ids=["fact-001"],
    )
    matrix = _evaluate(extraction, approved={"fact-001"})
    assert matrix.rows[0].scope_status == "approved_revision"
    assert matrix.completion_allowed is True


@pytest.mark.asyncio
async def test_claim_gate_state_never_becomes_completed_when_matrix_blocks() -> None:
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
    settings = Settings(writing_schema_mode="production")
    service = MultiAgentWritingService(settings, EditorialService(settings))
    with Session(engine) as db:
        source = SourceItem(
            provider="manual",
            platform="manual",
            external_id="claim-gate-source",
            canonical_url="manual://claim-gate-source",
            author_handle="author",
            author_name="Author",
            content_kind="article",
            text_original="用于 claim gate 状态测试的来源。",
            metrics_json="{}",
        )
        db.add(source)
        db.flush()
        project = WritingProject(
            source_id=source.id,
            mode="fast",
            state=WritingState.revising.value,
            current_stage="final_revision",
        )
        db.add(project)
        db.flush()

        async def fake_final_revision(self, session, current_project):
            final = self._store_artifact(
                session,
                project=current_project,
                artifact_type="final_draft",
                content={"title": "终稿", "body": "无证据主张", "tags": [], "claims": []},
                role="final_reviser",
                approved=False,
            )
            self._store_artifact(
                session,
                project=current_project,
                artifact_type="claim_evidence_matrix",
                content={
                    "schema_version": 1,
                    "checker_version": "claim-checker-v1",
                    "final_artifact_id": final.id,
                    "final_claims_artifact_id": "claims-1",
                    "total_claims": 1,
                    "supported_claims": 0,
                    "critical_unsupported_claims": 1,
                    "unauthorized_major_expansions": 0,
                    "completion_allowed": False,
                    "rows": [],
                },
                role="claim_checker",
                approved=True,
            )
            return final

        service._run_final_revision = types.MethodType(  # type: ignore[method-assign]
            fake_final_revision,
            service,
        )
        returned = await service.run_next(db, project)
        assert returned.artifact_type == "claim_evidence_matrix"
        assert project.state == WritingState.claims_blocked.value
        assert project.current_stage == "claim_evidence_gate"
        assert "critical unsupported=1" in project.error
        assert service.latest_artifact(db, project.id, "claim_evidence_matrix") is returned
        assert json.loads(returned.content_json)["completion_allowed"] is False

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.domain.models import DraftRevision, SourceItem
from app.domain.pool_memory import PoolMemorySnapshot
from app.domain.review_artifacts import ReviewArtifact, ReviewArtifactState
from app.domain.studio import WritingProject
from app.services.editorial import EditorialService
from app.services.pool_memory import PoolMemoryService
from app.services.style_exemplar_retrieval import StyleExemplarRetrievalService
from app.services.writing_studio import MultiAgentWritingService


def _session(tmp_path: Path) -> Session:
    import app.domain.discovery  # noqa: F401 - register all FK targets for create_all

    engine = create_engine(f"sqlite:///{tmp_path / 'style-exemplars.db'}")
    Base.metadata.create_all(engine)
    return Session(engine)


def _memory_card(
    db: Session,
    *,
    version: int,
    source_kind: str,
    examples: list[dict],
    created_by: str = "human",
    state: str = ReviewArtifactState.approved.value,
    usage_policy: str = "style_and_structure_only",
    authorized: bool = True,
) -> ReviewArtifact:
    payload = {
        "schema_version": 1,
        "title": f"memory-{version}",
        "source": {"kind": source_kind, "id": f"source-{version}", "label": "测试来源"},
        "dimensions": ["opening", "title", "transition", "judgment", "ending"],
        "scope": {"platforms": ["wechat"], "formats": ["article"]},
        "memory": {
            "rules": [],
            "avoid": [],
            "prefer": [],
            "positive_examples": examples,
            "structure": [],
            "visual_directions": [],
        },
        "usage_policy": usage_policy,
        "note": "",
        "extraction_mode": "human_edited_candidate",
        "eligibility": {
            "eligible": True,
            "requires_confirmation": False,
            "source_authorized_confirmed": authorized,
        },
        "supersedes_id": "",
    }
    artifact = ReviewArtifact(
        scope_type="pool_memory",
        scope_id="default",
        artifact_type="memory_card",
        version=version,
        payload_json=json.dumps(payload, ensure_ascii=False),
        state=state,
        created_by=created_by,
    )
    db.add(artifact)
    db.flush()
    return artifact


def test_style_exemplars_require_human_approval_rights_and_fact_free_short_text(
    tmp_path: Path,
) -> None:
    db = _session(tmp_path)
    try:
        feedback = _memory_card(
            db,
            version=1,
            source_kind="writing_feedback",
            examples=[
                {"text": "先把变化摆到桌面上。", "lesson": "开头直接给变化", "rhetorical_duty": "opening"},
                {"text": "判断到这里就够了。", "lesson": "判断克制收束", "rhetorical_duty": "judgment"},
            ],
        )
        manual = _memory_card(
            db,
            version=2,
            source_kind="manual_rule",
            examples=[
                {"text": "换个方向，再看它的边界。", "lesson": "自然转场", "rhetorical_duty": "transition"},
            ],
        )
        authorized = _memory_card(
            db,
            version=3,
            source_kind="authorized_sample",
            examples=[
                {"text": "先看结果，再谈热闹。", "lesson": "标题先给判断", "rhetorical_duty": "title"},
                {"text": "问题没有消失，只是位置变了。", "lesson": "结尾保留张力", "rhetorical_duty": "ending"},
            ],
        )
        not_human = _memory_card(
            db,
            version=4,
            source_kind="writing_feedback",
            examples=[
                {"text": "模型写出的句子不能直接入选。", "lesson": "无", "rhetorical_duty": "opening"},
            ],
            created_by="model",
        )
        rights_missing = _memory_card(
            db,
            version=5,
            source_kind="writing_artifact",
            examples=[
                {"text": "未确认权利的历史输出。", "lesson": "无", "rhetorical_duty": "ending"},
            ],
            authorized=False,
        )
        factual = _memory_card(
            db,
            version=6,
            source_kind="manual_rule",
            examples=[
                {"text": "2026年测试提升35%。", "lesson": "具体结果", "rhetorical_duty": "judgment"},
            ],
        )
        abstract = _memory_card(
            db,
            version=7,
            source_kind="manual_rule",
            examples=[
                {"text": "抽象模式不应注入原句。", "lesson": "无", "rhetorical_duty": "opening"},
            ],
            usage_policy="abstract_pattern_only",
        )
        ids = [
            feedback.id,
            manual.id,
            authorized.id,
            not_human.id,
            rights_missing.id,
            factual.id,
            abstract.id,
        ]
        snapshot = PoolMemorySnapshot(
            target_type="writing_project",
            target_id="writing-style-test",
            query_json="{}",
            memory_ids_json=json.dumps(ids),
            prompt_payload_json="{}",
            snapshot_hash="a" * 64,
            model_configured=True,
            model_name="test-model",
        )
        db.add(snapshot)
        db.flush()

        bundle = StyleExemplarRetrievalService().build(db, snapshot)
        assert 2 <= len(bundle.exemplars) <= 4
        assert bundle.exemplars[0].memory_id == feedback.id
        assert len({item.rhetorical_duty for item in bundle.exemplars}) == len(bundle.exemplars)
        assert all(item.rights_basis == "human_approved_original_or_authorized" for item in bundle.exemplars)
        assert all(len(item.text) <= 120 for item in bundle.exemplars)
        assert "2026" not in bundle.prompt_text
        assert "35%" not in bundle.prompt_text
        assert "模型写出的句子" not in bundle.prompt_text
        assert "未确认权利" not in bundle.prompt_text
        assert bundle.omitted_reasons["NOT_HUMAN_APPROVED"] == 1
        assert bundle.omitted_reasons["SOURCE_RIGHTS_NOT_CONFIRMED"] == 1
        assert bundle.omitted_reasons["HISTORICAL_FACT_RISK"] == 1
        assert bundle.omitted_reasons["ABSTRACT_OR_VISUAL_MEMORY"] == 1
        assert not StyleExemplarRetrievalService().build(
            db,
            snapshot,
            max_examples=0,
        ).exemplars
    finally:
        db.close()


def test_feedback_freezes_model_and_human_versions_with_server_diff_and_memory_status(
    tmp_path: Path,
) -> None:
    db = _session(tmp_path)
    try:
        settings = Settings(database_url="sqlite://")
        writing = MultiAgentWritingService(settings, EditorialService(settings))
        source = SourceItem(
            provider="manual",
            platform="web",
            external_id="feedback-source",
            canonical_url="https://example.invalid/feedback-source",
            text_original="用于验证真实修改反馈的本地材料。",
        )
        db.add(source)
        db.flush()
        project = WritingProject(
            source_id=source.id,
            reader="技术读者",
            promise="讲清事实边界",
            main_thesis="用户修改优先",
        )
        db.add(project)
        db.flush()
        before = DraftRevision(
            source_id=source.id,
            version=1,
            style="studio",
            title="模型给出的标题",
            body="开头先总结。\n\n正文保持匀速。",
            tags="写作",
            provenance_json=json.dumps({"writing_project_id": project.id}),
            created_by="multi-agent",
        )
        db.add(before)
        db.flush()
        after = DraftRevision(
            source_id=source.id,
            version=2,
            style="studio",
            title="先看变化，再谈结论",
            body="变化先发生在开头。\n\n正文一快一慢，最后给判断。",
            tags="写作,反馈",
            provenance_json=json.dumps(
                {"writing_project_id": project.id, "parent_draft_id": before.id}
            ),
            created_by="human",
        )
        db.add(after)
        db.flush()

        feedback = writing.add_feedback(
            db,
            project=project,
            draft_before_id=before.id,
            draft_after_id=after.id,
            article_type="technical_explainer",
            feedback_reason="不要总结腔，开头直接给变化，段落要有速度差。",
            affected_dimensions=["title", "opening", "paragraph_rhythm"],
        )
        payload = json.loads(feedback.diff_json)
        assert payload["generator"] == "server_difflib_v1"
        assert payload["article_type"] == "technical_explainer"
        assert payload["model_draft"]["body"] == before.body
        assert payload["user_final"]["body"] == after.body
        assert payload["model_draft"]["sha256"] != payload["user_final"]["sha256"]
        assert "--- model-draft-v1" in payload["changes"]["body_unified_diff"]
        assert "+++ user-final-v2" in payload["changes"]["body_unified_diff"]
        assert json.loads(feedback.affected_rules_json) == [
            "title",
            "opening",
            "paragraph_rhythm",
        ]

        memory_service = PoolMemoryService(settings, writing.editorial)
        material = memory_service._material_from_source(
            db,
            source_kind="writing_feedback",
            source_id=feedback.id,
        )
        assert material["scope"]["platforms"] == ["wechat"]
        assert material["scope"]["article_types"] == ["technical_explainer"]
        assert memory_service.source_memory_status(
            db,
            source_kind="writing_feedback",
            source_id=feedback.id,
        )["status"] == "none"

        approved_card = _memory_card(
            db,
            version=20,
            source_kind="writing_feedback",
            examples=[
                {"text": "变化先发生在开头。", "lesson": "开头给变化", "rhetorical_duty": "opening"},
            ],
        )
        approved_payload = json.loads(approved_card.payload_json)
        approved_payload["source"]["id"] = feedback.id
        approved_card.payload_json = json.dumps(approved_payload, ensure_ascii=False)
        db.flush()
        assert memory_service.source_memory_status(
            db,
            source_kind="writing_feedback",
            source_id=feedback.id,
        )["status"] == "approved"

        wrong_after = DraftRevision(
            source_id=source.id,
            version=3,
            style="studio",
            title="错误血缘",
            body="错误血缘",
            provenance_json=json.dumps(
                {"writing_project_id": project.id, "parent_draft_id": "another-draft"}
            ),
            created_by="human",
        )
        db.add(wrong_after)
        db.flush()
        with pytest.raises(ValueError, match="直接编辑保存"):
            writing.add_feedback(
                db,
                project=project,
                draft_before_id=before.id,
                draft_after_id=wrong_after.id,
                article_type="technical_explainer",
                feedback_reason="错误血缘不应被接纳",
                affected_dimensions=["opening"],
            )
    finally:
        db.close()

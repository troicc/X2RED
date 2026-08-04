from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.domain.models import SourceItem
from app.domain.platforms import PlatformVariant
from app.domain.pool_memory import PoolMemorySnapshot, PoolMemoryUsage
from app.domain.review_artifacts import ReviewArtifact, ReviewArtifactState
from app.services.editorial import EditorialService
from app.services.pool_memory import FACT_BOUNDARY, PoolMemoryError, PoolMemoryService


def _memory(
    *,
    rules: list[str] | None = None,
    avoid: list[str] | None = None,
    visual: list[str] | None = None,
) -> dict:
    return {
        "rules": rules or [],
        "avoid": avoid or [],
        "prefer": [],
        "positive_examples": [],
        "structure": [],
        "visual_directions": visual or [],
    }


def _service_session(tmp_path: Path) -> tuple[PoolMemoryService, Session]:
    import app.domain.discovery  # noqa: F401 - register FK target tables for create_all

    engine = create_engine(f"sqlite:///{tmp_path / 'pool-memory.db'}")
    Base.metadata.create_all(engine)
    return PoolMemoryService(Settings()), Session(engine)


def test_retrieval_snapshot_roles_and_real_usage_are_strict(tmp_path: Path) -> None:
    service, db = _service_session(tmp_path)
    try:
        writing = service.add_manual_memory(
            db,
            title="技术长文克制表达",
            dimensions=["opening", "tone", "forbidden_expression"],
            scope={
                "platforms": ["wechat"],
                "formats": ["article"],
                "article_types": ["technical_explainer"],
            },
            memory=_memory(
                rules=["开头先给具体变化，再解释机制"],
                avoid=["值得注意的是"],
            ),
            usage_policy="style_and_structure_only",
            note="只用于公众号技术长文",
            confirm_original_or_authorized=True,
        )
        visual = service.add_manual_memory(
            db,
            title="留白视觉",
            dimensions=["visual_direction", "layout_preference"],
            scope={"platforms": ["wechat"], "formats": ["article"]},
            memory=_memory(visual=["大面积留白，中文排版由本地画布完成"]),
            usage_policy="visual_only",
            note="视觉角色专用",
            confirm_original_or_authorized=True,
        )
        db.flush()

        query = {
            "platform": "wechat",
            "format": "article",
            "article_type": "technical_explainer",
            "source_text": "本地推理引擎如何降低延迟",
            "limit": 8,
        }
        selected = service.retrieve(db, query)
        assert {row["artifact"].id for row in selected} == {writing.id, visual.id}
        assert (
            service.retrieve(
                db,
                {
                    **query,
                    "platform": "xhs",
                    "format": "caption",
                },
            )
            == []
        )

        frozen = service.create_snapshot(
            db,
            target_type="platform_variant",
            target_id="variant_frozen",
            query=query,
            model_configured=False,
        )
        frozen_ids = json.loads(frozen.memory_ids_json)
        assert set(frozen_ids) == {writing.id, visual.id}
        no_model = service.prompt_payload(frozen, role="writer", allow_pending=True)
        assert no_model["memory_ids"] == []
        assert no_model["applied"] is False
        assert "没有注入生成器" in no_model["text"]

        later = service.add_manual_memory(
            db,
            title="后来新增的规则",
            dimensions=["tone"],
            scope={"platforms": ["wechat"], "formats": ["article"]},
            memory=_memory(rules=["语气保持自然具体"]),
            usage_policy="style_and_structure_only",
            note="快照之后新增",
            confirm_original_or_authorized=True,
        )
        db.flush()
        assert later.id not in json.loads(frozen.memory_ids_json)
        assert frozen.snapshot_hash == db.get(PoolMemorySnapshot, frozen.id).snapshot_hash

        applied = service.create_snapshot(
            db,
            target_type="platform_variant",
            target_id="variant_applied",
            query=query,
            model_configured=True,
            model_name="test-model",
        )
        writer_payload = service.prompt_payload(applied, role="writer", allow_pending=True)
        visual_payload = service.prompt_payload(
            applied,
            role="visual_director",
            allow_pending=True,
        )
        fact_payload = service.prompt_payload(
            applied,
            role="fact_reviewer",
            allow_pending=True,
        )
        assert writing.id in writer_payload["memory_ids"]
        assert visual.id not in writer_payload["memory_ids"]
        assert visual.id in visual_payload["memory_ids"]
        assert writing.id not in visual_payload["memory_ids"]
        assert fact_payload["memory_ids"] == []
        assert fact_payload["text"] == FACT_BOUNDARY

        service.mark_snapshot_applied(
            db,
            applied,
            roles=[("fact_reviewer", "fact_only_check")],
        )
        assert applied.applied is False
        assert list(db.scalars(select(PoolMemoryUsage)).all()) == []

        service.mark_snapshot_applied(
            db,
            applied,
            roles=[
                ("writer", "draft"),
                ("visual_director", "art_direction"),
                ("fact_reviewer", "fact_check"),
            ],
        )
        db.flush()
        usages = list(db.scalars(select(PoolMemoryUsage)).all())
        assert {(item.memory_id, item.agent_role) for item in usages} == {
            (writing.id, "writer"),
            (later.id, "writer"),
            (visual.id, "visual_director"),
        }
        assert all(item.agent_role != "fact_reviewer" for item in usages)
        assert applied.applied is True
    finally:
        db.close()


@pytest.mark.asyncio
async def test_ai_transform_clones_frozen_snapshot_without_rewriting_old_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool, db = _service_session(tmp_path)
    try:
        memory = pool.add_manual_memory(
            db,
            title="改写仍需保持个人语气",
            dimensions=["tone", "forbidden_expression"],
            scope={
                "platforms": ["xhs"],
                "formats": ["caption"],
                "article_types": ["technical_explainer"],
            },
            memory=_memory(
                rules=["表达自然具体"],
                avoid=["总的来说"],
            ),
            usage_policy="style_and_structure_only",
            note="用于验证 AI 改写继承",
            confirm_original_or_authorized=True,
        )
        source = SourceItem(
            provider="test",
            platform="x",
            external_id="transform-memory-source",
            canonical_url="https://x.com/example/status/transform-memory-source",
            author_handle="example",
            text_original="作者发布了本地工具，并说明结果来自一组局部测试。",
            structured_content_json="{}",
            metrics_json="{}",
        )
        db.add(source)
        db.flush()

        fallback_editorial = EditorialService(Settings())
        original = await fallback_editorial.generate(db, source, "explain")
        original_provenance = json.loads(original.provenance_json)
        original_snapshot = db.get(
            PoolMemorySnapshot,
            original_provenance["memory_snapshot_id"],
        )
        assert original_snapshot is not None
        assert original_snapshot.applied is False
        assert json.loads(original_snapshot.memory_ids_json) == [memory.id]

        modeled_editorial = EditorialService(
            Settings(model_base_url="https://model.invalid/v1", model_name="test-model")
        )

        async def fake_chat_json(**_kwargs):
            return {
                "title": original.title,
                "body": original.body.replace("总的来说", "真正值得继续看的，是"),
                "tags": original.tags.split(","),
            }

        monkeypatch.setattr(modeled_editorial, "_chat_json", fake_chat_json)
        revised = await modeled_editorial.transform(
            db,
            original,
            action="de_translate",
            instruction="保持克制语气",
        )
        revised_provenance = json.loads(revised.provenance_json)
        revised_snapshot = db.get(
            PoolMemorySnapshot,
            revised_provenance["memory_snapshot_id"],
        )
        assert revised_snapshot is not None
        assert revised_snapshot.id != original_snapshot.id
        assert revised_snapshot.target_id == revised.id
        assert revised_snapshot.snapshot_hash == original_snapshot.snapshot_hash
        assert revised_snapshot.applied is True
        assert original_snapshot.applied is False
        usages = list(
            db.scalars(
                select(PoolMemoryUsage).where(PoolMemoryUsage.snapshot_id == revised_snapshot.id)
            ).all()
        )
        assert [(item.memory_id, item.agent_role, item.stage) for item in usages] == [
            (memory.id, "transform", "de_translate")
        ]
    finally:
        db.close()


@pytest.mark.asyncio
async def test_candidate_approval_supersede_revoke_and_legacy_compatibility(
    tmp_path: Path,
) -> None:
    service, db = _service_session(tmp_path)
    try:
        source = SourceItem(
            provider="test",
            platform="x",
            external_id="memory-source",
            canonical_url="https://x.com/example/status/memory-source",
            author_handle="example",
            text_original="先交代读者能看到的变化，再说明机制和限制。",
            structured_content_json="{}",
            metrics_json="{}",
        )
        db.add(source)
        db.flush()
        variant = PlatformVariant(
            source_id=source.id,
            base_draft_id=None,
            platform="wechat",
            format="article",
            version=1,
            title="一篇尚未批准的文章",
            body_markdown="开头先给变化。正文解释机制。结尾交代限制。",
            metadata_json="{}",
        )
        db.add(variant)
        db.flush()

        candidate = await service.create_candidate(
            db,
            source_kind="platform_variant",
            source_id=variant.id,
            title="公众号结构候选",
            dimensions=["opening", "structure", "forbidden_expression"],
            scope={},
            usage_policy="style_and_structure_only",
            note="先编辑后批准",
        )
        assert service.source_memory_status(
            db,
            source_kind="platform_variant",
            source_id=variant.id,
        )["status"] == "candidate"
        with pytest.raises(PoolMemoryError, match="确认"):
            service.approve_candidate(
                db,
                candidate,
                review_note="",
                confirm_source_authorized=False,
            )

        revised = service.update_candidate(
            db,
            candidate,
            title="公众号结构候选（已编辑）",
            dimensions=["opening", "structure", "forbidden_expression"],
            scope={
                "platforms": ["wechat"],
                "formats": ["article"],
                "article_types": ["technical_explainer"],
            },
            memory={
                **_memory(
                    rules=["先写具体变化，再解释机制"],
                    avoid=["显而易见"],
                ),
                "structure": ["变化", "机制", "限制"],
            },
            usage_policy="style_and_structure_only",
            note="人工修订候选",
        )
        assert candidate.state == ReviewArtifactState.superseded.value
        card = service.approve_candidate(
            db,
            revised,
            review_note="确认来源可用于个人风格学习",
            confirm_source_authorized=True,
        )
        db.flush()
        assert service.source_memory_status(
            db,
            source_kind="platform_variant",
            source_id=variant.id,
        )["approved_memory_ids"] == [card.id]

        query = {
            "platform": "wechat",
            "format": "article",
            "article_type": "technical_explainer",
            "source_text": "推理系统机制",
        }
        assert [row["artifact"].id for row in service.retrieve(db, query)] == [card.id]

        replacement = service.supersede_memory(
            db,
            card,
            title="新公众号结构规则",
            dimensions=["opening", "structure"],
            scope={
                "platforms": ["wechat"],
                "formats": ["article"],
                "article_types": ["technical_explainer"],
            },
            memory={
                **_memory(rules=["用读者可观察到的结果开头"]),
                "structure": ["结果", "机制", "边界"],
            },
            usage_policy="style_and_structure_only",
            note="规则升级",
            reason="旧规则过于宽泛",
        )
        db.flush()
        assert [row["artifact"].id for row in service.retrieve(db, query)] == [replacement.id]
        service.revoke_memory(db, replacement, reason="暂时不再使用")
        db.flush()
        assert service.retrieve(db, query) == []
        assert (
            db.scalar(
                select(func.count(ReviewArtifact.id)).where(
                    ReviewArtifact.artifact_type == "memory_card"
                )
            )
            == 2
        )

        legacy = ReviewArtifact(
            scope_type="light_corpus",
            scope_id="comfort",
            artifact_type="light_corpus_item",
            version=1,
            payload_json=json.dumps(
                {
                    "title": "已有授权轻内容",
                    "body_markdown": "晚饭后，先把十分钟还给自己。",
                    "source_kind": "authorized_sample",
                    "visual_style": "minimal_zine",
                    "note": "学习具体场景和克制节奏",
                },
                ensure_ascii=False,
            ),
            state=ReviewArtifactState.approved.value,
            created_by="human",
        )
        db.add(legacy)
        db.flush()
        legacy_rows = service.retrieve(
            db,
            {
                "platform": "wechat",
                "format": "light_series",
                "recipe": "comfort",
                "visual_route": "minimal_zine",
                "dimensions": ["opening", "sentence_rhythm"],
            },
        )
        assert [row["artifact"].id for row in legacy_rows] == [legacy.id]
        assert legacy_rows[0]["legacy"] is True
    finally:
        db.close()


def test_pool_memory_api_and_fast_draft_do_not_fake_application(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("X2RED_DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    monkeypatch.setenv("X2RED_MEDIA_DIR", str(tmp_path / "assets"))
    monkeypatch.setenv("X2RED_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("X2RED_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("X2RED_BROWSER_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("X2RED_SCHEDULER_ENABLED", "false")
    monkeypatch.delenv("X2RED_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("X2RED_MODEL_NAME", raising=False)
    monkeypatch.delenv("X2RED_MODEL_API_KEY", raising=False)

    from app.core.config import get_settings

    get_settings.cache_clear()
    import app.db.session as db_session
    import app.main as main_module

    importlib.reload(db_session)
    importlib.reload(main_module)

    with TestClient(main_module.app) as client:
        with db_session.SessionLocal() as db:
            source = SourceItem(
                provider="test",
                platform="x",
                external_id="api-memory-source",
                canonical_url="https://x.com/example/status/api-memory-source",
                author_handle="example",
                text_original="作者发布了一个本地推理工具，并说明当前数据只来自局部测试。",
                structured_content_json="{}",
                metrics_json="{}",
            )
            db.add(source)
            db.commit()
            source_id = source.id

        created = client.post(
            "/api/pool-memory/items",
            json={
                "title": "小红书技术解释规则",
                "dimensions": ["opening", "tone", "forbidden_expression"],
                "scope": {
                    "platforms": ["xhs"],
                    "formats": ["caption"],
                    "article_types": ["technical_explainer"],
                },
                "memory": _memory(
                    rules=["先写能确认的变化"],
                    avoid=["显而易见"],
                ),
                "usage_policy": "style_and_structure_only",
                "note": "API 回归",
                "confirm_original_or_authorized": True,
            },
        )
        assert created.status_code == 201, created.text
        memory_id = created.json()["id"]

        preview = client.post(
            "/api/pool-memory/retrieve-preview",
            json={
                "platform": "xhs",
                "format": "caption",
                "article_type": "technical_explainer",
                "source_text": "本地推理工具",
            },
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["memory_ids"] == [memory_id]
        assert FACT_BOUNDARY in preview.json()["prompt_preview"]
        assert client.get(
            "/api/pool-memory/items",
            params={"article_type": "news"},
        ).json() == []

        generated = client.post(
            f"/api/sources/{source_id}/drafts",
            json={"style": "explain"},
        )
        assert generated.status_code == 200, generated.text
        draft = generated.json()
        provenance = json.loads(draft["provenance_json"])
        assert provenance["memory_ids"] == [memory_id]
        assert provenance["memory_snapshot_id"]
        assert len(provenance["memory_snapshot_hash"]) == 64
        assert provenance["memory_applied"] is False
        assert provenance["memory_status"] == "model_not_configured"

        snapshots = client.get(
            "/api/pool-memory/snapshots",
            params={"target_type": "draft_revision", "target_id": draft["id"]},
        )
        assert snapshots.status_code == 200, snapshots.text
        assert len(snapshots.json()) == 1
        assert snapshots.json()[0]["applied"] is False
        assert client.get("/api/pool-memory/usages").json() == []

        candidate = client.post(
            f"/api/drafts/{draft['id']}/memory-candidate",
            json={
                "title": "系统回退稿候选",
                "dimensions": ["opening", "structure"],
                "scope": {"platforms": ["xhs"], "formats": ["caption"]},
                "usage_policy": "style_and_structure_only",
                "note": "必须再次人工批准",
            },
        )
        assert candidate.status_code == 201, candidate.text
        candidate_id = candidate.json()["candidate_id"]
        blocked = client.post(
            f"/api/pool-memory/candidates/{candidate_id}/approve",
            json={"review_note": "", "confirm_source_authorized": False},
        )
        assert blocked.status_code == 400
        approved = client.post(
            f"/api/pool-memory/candidates/{candidate_id}/approve",
            json={
                "review_note": "已人工检查并确认可用于个人风格学习",
                "confirm_source_authorized": True,
            },
        )
        assert approved.status_code == 201, approved.text

        index = client.get("/")
        assert index.status_code == 200
        assert "pool-memory-v16.css" in index.text
        script = client.get("/static/pool-memory-v16.js")
        assert script.status_code == 200
        assert "候选不会自动进入正式池子" in script.text

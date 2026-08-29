from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient


def wait_for_job(client: TestClient, job_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    latest: dict = {}
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200, response.text
        latest = response.json()
        if latest["state"] in {"succeeded", "failed"}:
            return latest
        time.sleep(0.05)
    return latest


def test_completed_agent_stages_survive_later_model_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("X2RED_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("X2RED_MEDIA_DIR", str(tmp_path / "assets"))
    monkeypatch.setenv("X2RED_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("X2RED_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("X2RED_BROWSER_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("X2RED_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("X2RED_MODEL_BASE_URL", "https://model.example/v1")
    monkeypatch.setenv("X2RED_MODEL_NAME", "glm-5.2")
    monkeypatch.setenv("X2RED_MODEL_API_KEY", "test-key")

    from app.core.config import get_settings

    get_settings.cache_clear()

    import app.db.session as db_session
    import app.main as main_module

    importlib.reload(db_session)
    importlib.reload(main_module)

    from app.domain.models import DraftRevision, SourceItem
    from app.domain.platforms import PlatformVariant

    with TestClient(main_module.app) as client:
        with db_session.SessionLocal() as db:
            source = SourceItem(
                provider="x2pdf",
                platform="x",
                external_id="durable-article",
                canonical_url="https://x.com/author/article/durable",
                author_handle="author",
                author_name="Author",
                content_kind="article",
                text_original="A technical article with enough evidence for a durable writing test.",
                metrics_json="{}",
            )
            db.add(source)
            supporting = SourceItem(
                provider="x2pdf",
                platform="x",
                external_id="durable-comparison",
                canonical_url="https://x.com/author/article/comparison",
                author_handle="comparison",
                author_name="Comparison",
                content_kind="article",
                text_original="Fable comparison evidence: code routing, benchmark scope, and implementation tradeoffs.",
                metrics_json="{}",
            )
            db.add(supporting)
            db.flush()
            written_draft = DraftRevision(
                source_id=source.id,
                version=1,
                style="studio",
                title="已经写好的草稿版本",
                body="这份已写草稿包含需要继续整合的结构、代码示例和未完成判断。" * 6,
                tags="深度写作,版本材料",
                provenance_json="{}",
            )
            db.add(written_draft)
            db.flush()
            written_variant = PlatformVariant(
                source_id=supporting.id,
                platform="wechat",
                format="article",
                version=1,
                title="已经写好的公众号版本",
                body_markdown="这份平台版本补充了另一条论述路径，应与原始来源一起核对后整合。" * 6,
                metadata_json=json.dumps(
                    {"evidence_source_ids": [source.id, supporting.id]},
                    ensure_ascii=False,
                ),
            )
            db.add(written_variant)
            db.commit()
            db.refresh(source)
            db.refresh(supporting)
            source_id = source.id
            supporting_id = supporting.id
            written_draft_id = written_draft.id
            written_variant_id = written_variant.id

        pasted = client.post(
            "/api/sources/manual",
            json={
                "title": "同时粘贴的补充材料",
                "text_original": "这是与库内来源和已写版本同时提交的粘贴材料。" * 8,
            },
        )
        assert pasted.status_code == 201, pasted.text
        pasted_id = pasted.json()["id"]
        options = client.get("/api/writing/material-options?limit=100")
        assert options.status_code == 200, options.text
        option_refs = {item["ref"] for item in options.json()}
        assert {
            f"source:{source_id}",
            f"draft:{written_draft_id}",
            f"variant:{written_variant_id}",
        } <= option_refs

        calls = 0
        prompts: list[str] = []

        async def fake_chat_json(**kwargs):
            nonlocal calls
            calls += 1
            prompts.append(str(kwargs.get("user_prompt") or ""))
            if calls == 1:
                return {
                    "reader": "技术读者",
                    "article_promise": "讲清技术成果",
                    "main_thesis": "底层实现会改变结果",
                    "reader_hook": "先看结果",
                    "must_use": [],
                    "must_not_claim": [],
                    "article_type": "explain",
                    "tone": "直接",
                    "open_questions": [],
                    "success_criteria": [],
                }
            if calls == 2:
                return {
                    "facts": [],
                    "author_claims": [],
                    "unknowns": [],
                    "numbers": [],
                    "terms": [],
                    "source_map": [],
                    "material_gaps": [],
                    "usable_examples": [],
                    "claims_for_draft": [],
                }
            if calls == 3:
                return {
                    "opening": {},
                    "sections": [],
                    "ending": {},
                    "cognitive_load_plan": [],
                    "terms_first_use": [],
                    "evidence_allocation": [],
                    "transitions": [],
                    "forbidden_moves": [],
                }
            raise httpx.ConnectError("temporary model outage")

        monkeypatch.setattr(
            main_module.app.state.writing_service.editorial,
            "_chat_json",
            fake_chat_json,
        )

        project_response = client.post(
            "/api/writing/projects",
            json={
                "source_id": source_id,
                "supporting_source_ids": [supporting_id],
                "material_refs": [
                    f"source:{source_id}",
                    f"source:{supporting_id}",
                    f"draft:{written_draft_id}",
                    f"variant:{written_variant_id}",
                    f"source:{pasted_id}",
                ],
                "mode": "fast",
                "reader": "技术读者",
                "promise": "讲清技术成果",
                "budget_limit_cents": 20,
            },
        )
        assert project_response.status_code == 201, project_response.text
        project_id = project_response.json()["id"]
        queued = client.post(
            f"/api/writing/projects/{project_id}/run",
            json={"continuous": True},
        )
        assert queued.status_code == 202, queued.text
        job = wait_for_job(client, queued.json()["id"])
        assert job["state"] == "failed", job
        assert job["attempts"] == 2

        project = client.get(f"/api/writing/projects/{project_id}").json()
        assert project["source_ids"] == [source_id, supporting_id, pasted_id]
        assert project["source_summaries"][1]["role"] == "supporting"
        assert {item["kind"] for item in project["material_summaries"]} == {
            "source",
            "draft_revision",
            "platform_variant",
        }
        assert any("Fable comparison evidence" in prompt for prompt in prompts[:2])
        assert any("已经写好的草稿版本" in prompt for prompt in prompts[:2])
        assert any("已经写好的公众号版本" in prompt for prompt in prompts[:2])
        assert any("同时提交的粘贴材料" in prompt for prompt in prompts[:2])
        assert any('"selection_role": "supporting"' in prompt for prompt in prompts[:2])
        assert any('"selection_role": "written_version"' in prompt for prompt in prompts[:2])
        assert project["state"] == "drafting"
        assert "temporary model outage" in project["error"]
        artifact_types = {item["artifact_type"] for item in project["artifacts"]}
        assert {"editorial_brief", "evidence_pack", "outline"} <= artifact_types
        assert "draft" not in artifact_types
        traced = [
            json.loads(item["content_json"])["evidence_retrieval"]
            for item in project["artifacts"]
            if item["artifact_type"] in {"editorial_brief", "evidence_pack"}
        ]
        assert traced and all(item["mode"] == "hybrid" for item in traced)
        assert all(
            section["evidence_chunks"]
            for item in traced
            for section in item["sections"]
        )
        assert all(
            ":" in chunk["evidence_ref"]
            for item in traced
            for section in item["sections"]
            for chunk in section["evidence_chunks"]
        )

        runs = project["runs"]
        succeeded_roles = {item["role"] for item in runs if item["status"] == "succeeded"}
        failed_writer_runs = [
            item for item in runs if item["role"] == "writer" and item["status"] == "failed"
        ]
        assert {"editor_in_chief", "evidence_researcher", "outline_architect"} <= succeeded_roles
        assert len(failed_writer_runs) == 2
        assert all("temporary model outage" in item["error"] for item in failed_writer_runs)

        # The durable job result is separate from the project history; both failures
        # remain queryable even after the worker transaction rolls back and retries.
        assert json.loads(job["result_json"] or "{}") == {}


def test_deep_writing_preserves_complete_longform_and_links_wechat_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("X2RED_DATABASE_URL", f"sqlite:///{tmp_path / 'longform.db'}")
    monkeypatch.setenv("X2RED_MEDIA_DIR", str(tmp_path / "assets"))
    monkeypatch.setenv("X2RED_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("X2RED_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("X2RED_BROWSER_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("X2RED_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("X2RED_MODEL_BASE_URL", "https://model.example/v1")
    monkeypatch.setenv("X2RED_MODEL_NAME", "glm-5.2")
    monkeypatch.setenv("X2RED_MODEL_API_KEY", "test-key")

    from app.core.config import get_settings

    get_settings.cache_clear()

    import app.db.session as db_session
    import app.main as main_module

    importlib.reload(db_session)
    importlib.reload(main_module)

    from app.domain.models import DraftRevision, SourceItem

    sentence = "这段论述只使用已冻结证据，解释成果、边界与对读者的实际意义。"
    long_body = "开头先说明成果为什么值得关注。\n\n" + "\n\n".join(
        f"## 章节{index}\n\n{sentence * 47}" for index in range(1, 4)
    )
    assert 4000 < len(long_body) < 4500

    with TestClient(main_module.app) as client:
        with db_session.SessionLocal() as db:
            source = SourceItem(
                provider="x2pdf",
                platform="x",
                external_id="complete-longform",
                canonical_url="https://x.com/author/article/complete-longform",
                author_handle="author",
                author_name="Author",
                content_kind="article",
                text_original=("这是支持完整公众号长文的原始事实材料。" * 80),
                metrics_json="{}",
            )
            db.add(source)
            db.commit()
            db.refresh(source)
            source_id = source.id

        responses = [
            {
                "reader": "技术读者",
                "article_promise": "讲清技术成果与边界",
                "main_thesis": "底层实现会改变最终结果",
                "reader_hook": "先看成果",
                "must_use": [],
                "must_not_claim": [],
                "article_type": "explain",
                "tone": "直接",
                "open_questions": [],
                "success_criteria": [],
            },
            {
                "facts": [], "author_claims": [], "unknowns": [], "numbers": [],
                "terms": [], "source_map": [], "material_gaps": [],
                "usable_examples": [], "claims_for_draft": [],
            },
            {
                "opening": {}, "sections": [], "ending": {}, "cognitive_load_plan": [],
                "terms_first_use": [], "evidence_allocation": [], "transitions": [],
                "forbidden_moves": [],
            },
            {
                "title": "被长度上限截断的初稿",
                "body": "## 第一节\n\n正文尚未完成。\n\n## 第二节\n\n仍在输出。\n\n## 第三节\n\n半句",
                "tags": ["长文"],
                "claims": [],
                "_finish_reason": "length",
            },
            {"title": "完整公众号初稿", "body": long_body, "tags": ["长文"], "claims": []},
            {"verdict": "pass", "minimal_fixes": []},
            {"verdict": "pass", "minimal_fixes": []},
            {"verdict": "pass", "minimal_fixes": []},
            {
                "must_fix": [], "should_fix": [], "reject_suggestions": [],
                "author_decisions": [], "revision_instructions": [],
                "release_readiness": "ready",
            },
            {
                "title": "完整公众号终稿",
                "body": long_body.replace("成果", "技术成果", 1),
                "tags": ["长文"],
                "claims": [],
                "applied_changes": ["完成审稿修订"],
            },
        ]
        calls: list[dict] = []

        async def fake_chat_json(**kwargs):
            calls.append(kwargs)
            response = dict(responses.pop(0))
            finish_reason = response.pop("_finish_reason", "stop")
            if kwargs.get("capture_response_meta"):
                response["_x2red_response_meta"] = {
                    "finish_reason": finish_reason,
                    "completion_tokens": 6200,
                }
            return response

        monkeypatch.setattr(
            main_module.app.state.writing_service.editorial,
            "_chat_json",
            fake_chat_json,
        )

        created = client.post(
            "/api/writing/projects",
            json={
                "source_id": source_id,
                "material_refs": [f"source:{source_id}"],
                "mode": "fast",
                "reader": "技术读者",
                "promise": "讲清技术成果与边界",
                "budget_limit_cents": 30,
            },
        )
        assert created.status_code == 201, created.text
        project_id = created.json()["id"]
        queued = client.post(
            f"/api/writing/projects/{project_id}/run",
            json={"continuous": True},
        )
        assert queued.status_code == 202, queued.text
        job = wait_for_job(client, queued.json()["id"], timeout=30)
        assert job["state"] == "succeeded", job
        assert responses == []

        longform_calls = [call for call in calls if call.get("capture_response_meta")]
        assert len(longform_calls) == 3
        assert all(call["max_tokens"] == 12000 for call in longform_calls)
        assert all(call["request_timeout_seconds"] == 360 for call in longform_calls)
        assert "公众号长文未通过完整度检查" in longform_calls[1]["user_prompt"]
        assert "1800—4500" in longform_calls[0]["user_prompt"]

        project = client.get(f"/api/writing/projects/{project_id}").json()
        assert project["state"] == "completed"
        assert project["output_draft_id"]
        assert project["output_draft_version"] == 1
        assert project["output_draft_chars"] > 4000
        assert len([item for item in project["artifacts"] if item["artifact_type"] == "draft"]) == 2

        with db_session.SessionLocal() as db:
            output_draft = db.get(DraftRevision, project["output_draft_id"])
            assert output_draft is not None
            assert len(output_draft.body) == project["output_draft_chars"]
            assert len(output_draft.body) > 4000
            provenance = json.loads(output_draft.provenance_json)
            assert provenance["writing_project_id"] == project_id
            assert provenance["final_artifact_id"]

        async def use_structured_fallback(*args, **kwargs):
            return None

        monkeypatch.setattr(
            main_module.app.state.platform_service,
            "_generate_platform_copy",
            use_structured_fallback,
        )
        variant_response = client.post(
            "/api/platforms/wechat/variants",
            json={
                "source_id": source_id,
                "material_refs": [
                    f"source:{source_id}",
                    f"draft:{project['output_draft_id']}",
                ],
                "draft_id": project["output_draft_id"],
                "theme": "auto",
                "mode": "preserve",
                "include_citations": False,
                "include_illustration_plan": False,
                "author": "",
            },
        )
        assert variant_response.status_code == 201, variant_response.text
        variant = variant_response.json()
        metadata = json.loads(variant["metadata_json"])
        assert metadata["writing_project_id"] == project_id
        assert metadata["writing_final_artifact_id"] == provenance["final_artifact_id"]

        refreshed = client.get(f"/api/writing/projects/{project_id}").json()
        assert refreshed["wechat_variant_id"] == variant["id"]
        assert refreshed["wechat_variant_version"] == variant["version"]
        assert refreshed["wechat_variant_status"] == variant["status"]


def test_deep_longform_gate_rejects_short_or_overcompressed_model_output() -> None:
    from app.services.writing_agents import WritingAgentsMixin

    short_body = "\n\n".join(
        f"## 章节{index}\n\n{'短段落。' * 70}" for index in range(1, 4)
    )
    short_issues = WritingAgentsMixin._longform_completion_issues(
        {
            "body": short_body,
            "_completion": {"finish_reason": "stop", "completion_tokens": 1800},
        }
    )
    assert any("深度长文最低 1200 字符" in issue for issue in short_issues)

    reference_body = "完整初稿内容。" * 700
    compressed_body = "\n\n".join(
        f"## 章节{index}\n\n{'终稿保留事实。' * 90}" for index in range(1, 4)
    )
    compressed_issues = WritingAgentsMixin._longform_completion_issues(
        {
            "body": compressed_body,
            "_completion": {"finish_reason": "stop", "completion_tokens": 2600},
        },
        reference_body=reference_body,
    )
    assert any("疑似过度压缩" in issue for issue in compressed_issues)

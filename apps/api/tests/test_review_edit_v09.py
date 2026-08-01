from __future__ import annotations

import importlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_review_edit_render_and_wechat_publisher_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("X2RED_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
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

    from app.domain.models import DraftRevision, SourceItem
    from app.domain.platforms import PlatformVariant

    with TestClient(main_module.app) as client:
        with db_session.SessionLocal() as db:
            source = SourceItem(
                provider="x2pdf",
                platform="x",
                external_id="review-v09-source",
                canonical_url="https://x.com/engineer/article/review-v09",
                author_handle="engineer",
                author_name="Engineer",
                content_kind="article",
                text_original=(
                    "The author rewrote the slowest CUDA attention kernel for Blackwell. "
                    "The local step fell from 5 seconds to 0.16 seconds, while the end-to-end "
                    "latency reached 2.5 seconds."
                ),
                metrics_json="{}",
            )
            db.add(source)
            db.flush()
            draft = DraftRevision(
                source_id=source.id,
                version=1,
                style="explain",
                title="重写 CUDA 内核后，视频模型为什么快了 54 倍",
                body=(
                    "这次优化没有更换模型，而是重写了最慢的注意力计算。\n\n"
                    "过去，所有 token 都进入昂贵计算；现在先筛出真正有贡献的部分。\n\n"
                    "局部内核从约 5 秒降至 0.16 秒，端到端延迟约为 2.5 秒。\n\n"
                    "真正值得关注的是，模型速度也取决于底层执行方式。"
                ),
                tags="CUDA,AI工程,视频生成",
                provenance_json=json.dumps(
                    {
                        "editorial_analysis": {
                            "topic": "视频模型底层优化",
                            "one_sentence_summary": "不换模型，通过稀疏计算和 CUDA 内核重写大幅降低最慢步骤。",
                            "audience_value": [
                                "看懂 54 倍发生在哪一层",
                                "理解模型之外的性能空间",
                            ],
                            "verified_facts": [
                                {"statement": "局部步骤从约 5 秒降至 0.16 秒"},
                                {"statement": "端到端延迟约 2.5 秒"},
                            ],
                            "recommended_angle": {
                                "reason": "真正的变化是底层执行方式，而不是模型参数。"
                            },
                        }
                    },
                    ensure_ascii=False,
                ),
            )
            db.add(draft)
            db.flush()
            variant = PlatformVariant(
                source_id=source.id,
                base_draft_id=draft.id,
                platform="wechat",
                format="article",
                version=1,
                title="重写 CUDA 内核后，视频模型为什么快了 54 倍",
                subtitle="性能突破不只发生在模型层",
                summary="从局部内核到端到端延迟，拆解这次优化真正发生在哪里。",
                body_markdown=(
                    "## 先看结果\n\n局部计算从约 5 秒降至 0.16 秒。\n\n"
                    "## 为什么有效\n\n系统先筛出真正有贡献的 token，再重写底层 CUDA 内核。\n\n"
                    "> 真正值得关注的是底层执行方式。"
                ),
                body_html=(
                    '<section style="padding:20px"><h1 style="font-size:30px">重复标题</h1>'
                    '<h2 style="font-size:22px">先看结果</h2><p style="font-size:16px">正文内容</p></section>'
                ),
                tags="CUDA,视频生成",
                theme="graphite",
                metadata_json=json.dumps(
                    {
                        "author": "技术观察员",
                        "short_share_title": "CUDA 内核重写",
                        "validation": {"warnings": []},
                    },
                    ensure_ascii=False,
                ),
                output_paths_json="{}",
                status="rendered",
            )
            db.add(variant)
            db.commit()
            source_id = source.id
            draft_id = draft.id
            variant_id = variant.id

        storyboard_response = client.post(
            "/api/reviews/artifacts",
            json={
                "artifact_type": "xhs_storyboard",
                "scope_type": "draft",
                "scope_id": draft_id,
            },
        )
        assert storyboard_response.status_code == 201, storyboard_response.text
        storyboard = storyboard_response.json()
        storyboard_payload = json.loads(storyboard["payload_json"])
        assert 3 <= len(storyboard_payload["pages"]) <= 9
        assert storyboard_payload["pages"][0]["kind"] == "hero_cover"
        assert storyboard_payload["art_direction"]["style"] == "technical_blueprint"

        storyboard_payload["art_direction"]["palette"] = "acid_green"
        storyboard_payload["pages"][0]["title"] = "不换模型，底层内核让速度起飞"
        revised_response = client.put(
            f"/api/reviews/artifacts/{storyboard['id']}",
            json={"payload": storyboard_payload, "note": "增强封面判断"},
        )
        assert revised_response.status_code == 200, revised_response.text
        revised_storyboard = revised_response.json()
        assert revised_storyboard["version"] == 2
        assert revised_storyboard["parent_id"] == storyboard["id"]

        approved_response = client.post(
            f"/api/reviews/artifacts/{revised_storyboard['id']}/decision",
            json={"decision": "approved", "note": "故事线确认"},
        )
        assert approved_response.status_code == 200, approved_response.text
        rendered_response = client.post(
            f"/api/reviews/artifacts/{revised_storyboard['id']}/render-storyboard",
            json={"template": "tech_minimal", "preview": False},
        )
        assert rendered_response.status_code == 200, rendered_response.text
        rendered = rendered_response.json()
        assert rendered["output_count"] == len(storyboard_payload["pages"])
        cards_response = client.get(f"/api/drafts/{draft_id}/cards")
        assert cards_response.status_code == 200
        assert cards_response.json()[0]["id"] == rendered["card_render_id"]

        modules_response = client.post(
            "/api/reviews/artifacts",
            json={
                "artifact_type": "wechat_module_tree",
                "scope_type": "platform_variant",
                "scope_id": variant_id,
            },
        )
        assert modules_response.status_code == 201, modules_response.text
        module_artifact = modules_response.json()
        module_payload = json.loads(module_artifact["payload_json"])
        assert any(item["type"] == "heading" for item in module_payload["modules"])
        module_payload["modules"].append(
            {
                "id": "module-human-judgment",
                "type": "quote",
                "text": "真正的突破，是把模型能力落到硬件执行路径上。",
            }
        )
        module_revision = client.put(
            f"/api/reviews/artifacts/{module_artifact['id']}",
            json={"payload": module_payload, "note": "加入编辑判断"},
        ).json()
        module_approved = client.post(
            f"/api/reviews/artifacts/{module_revision['id']}/decision",
            json={"decision": "approved", "note": "模块确认"},
        )
        assert module_approved.status_code == 200
        applied_response = client.post(
            f"/api/reviews/artifacts/{module_revision['id']}/apply-wechat-modules"
        )
        assert applied_response.status_code == 200, applied_response.text
        applied_variant_id = applied_response.json()["applied_to_id"]
        assert applied_variant_id != variant_id
        applied_variant = client.get(f"/api/platforms/variants/{applied_variant_id}").json()
        assert "真正的突破" in applied_variant["body_markdown"]

        render_wechat = client.post(
            f"/api/platforms/variants/{applied_variant_id}/render",
            json={"package": True},
        )
        assert render_wechat.status_code == 200, render_wechat.text
        rendered_variant = render_wechat.json()["variant"]
        assert rendered_variant["status"] == "packaged"

        publisher_payload = client.get(
            f"/api/reviews/wechat/{applied_variant_id}/publisher-payload"
        )
        assert publisher_payload.status_code == 200, publisher_payload.text
        publisher = publisher_payload.json()
        assert publisher["title"] == applied_variant["title"]
        assert "<h1" not in publisher["body_html"].lower()
        assert "正文" in publisher["body_html"] or "局部" in publisher["body_html"]

        cover_response = client.post(
            "/api/reviews/artifacts",
            json={
                "artifact_type": "wechat_cover_brief",
                "scope_type": "platform_variant",
                "scope_id": applied_variant_id,
            },
        )
        assert cover_response.status_code == 201, cover_response.text
        cover_artifact = cover_response.json()
        cover_payload = json.loads(cover_artifact["payload_json"])
        cover_payload.update(
            {
                "cover_style": "data_poster",
                "emphasis": "54倍",
                "series_label": "AI 工程观察",
            }
        )
        cover_revision = client.put(
            f"/api/reviews/artifacts/{cover_artifact['id']}",
            json={"payload": cover_payload, "note": "强调性能数字"},
        ).json()
        cover_approved = client.post(
            f"/api/reviews/artifacts/{cover_revision['id']}/decision",
            json={"decision": "approved", "note": "封面确认"},
        )
        assert cover_approved.status_code == 200
        cover_render = client.post(
            f"/api/reviews/artifacts/{cover_revision['id']}/render-wechat-cover"
        )
        assert cover_render.status_code == 200, cover_render.text
        final_variant = client.get(f"/api/platforms/variants/{applied_variant_id}").json()
        output_paths = json.loads(final_variant["output_paths_json"])
        assert Path(output_paths["wide"]).is_file()
        assert Path(output_paths["square"]).is_file()

        extension = client.get("/api/reviews/wechat-assistant/extension.zip")
        assert extension.status_code == 200
        with zipfile.ZipFile(io.BytesIO(extension.content)) as archive:
            names = set(archive.namelist())
            assert {"manifest.json", "popup.html", "popup.js", "content.js"} <= names

        artifacts = client.get(
            f"/api/reviews/artifacts?scope_type=draft&scope_id={draft_id}"
        ).json()
        assert {item["version"] for item in artifacts} >= {1, 2}
        assert any(item["state"] == "superseded" for item in artifacts)

        health = client.get("/health").json()
        assert health["version"] == "0.11.0"
        assert health["review_pipeline"] == (
            "storyboard-module-tree-cover-brief-versioned-approval"
        )
        assert health["wechat_publisher_assistant"] is True
        assert health["card_renderer"] == "reviewed-semantic-playwright"
        assert source_id

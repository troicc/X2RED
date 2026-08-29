from __future__ import annotations

import importlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image


def test_wechat_workbench_api_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("X2RED_DATABASE_URL", f"sqlite:///{tmp_path / 'platform.db'}")
    monkeypatch.setenv("X2RED_MEDIA_DIR", str(tmp_path / "assets"))
    monkeypatch.setenv("X2RED_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("X2RED_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("X2RED_BROWSER_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("X2RED_SCHEDULER_ENABLED", "false")
    # This V0.8 compatibility flow predates the production CJK typography gate.
    # Dedicated renderer tests cover fail-closed production mode separately.
    monkeypatch.setenv("X2RED_TYPOGRAPHY_RECIPE_MODE", "legacy")
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

    with TestClient(main_module.app) as client:
        pasted_text = (
            "这是用户直接粘贴进公众号工作台的一段完整材料。"
            "它需要先进入统一来源库，再参与后续写作、配图和发布。"
        ) * 3
        manual = client.post(
            "/api/sources/manual",
            json={
                "title": "手工粘贴材料",
                "author_name": "本地作者",
                "canonical_url": "https://example.com/manual-source",
                "text_original": pasted_text,
            },
        )
        assert manual.status_code == 201, manual.text
        manual_source = manual.json()
        assert manual_source["provider"] == "manual"
        assert manual_source["platform"] == "web"
        assert manual_source["text_original"] == pasted_text
        duplicate = client.post(
            "/api/sources/manual",
            json={"title": "重复粘贴", "text_original": pasted_text},
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] == manual_source["id"]

        with db_session.SessionLocal() as db:
            source = SourceItem(
                provider="x2pdf",
                platform="x",
                external_id="wechat-api-1",
                canonical_url="https://x.com/kernel/article/wechat-api-1",
                author_handle="kernel",
                author_name="Kernel Writer",
                content_kind="article",
                text_original=(
                    "作者重新设计了视频模型里最慢的注意力计算。"
                    "这次工作先筛掉无效 token，再利用 Blackwell GPU 的数据搬运能力。"
                    "作者给出的局部测试从约五秒下降到零点一六秒。"
                ) * 5,
                structured_content_json='{"title":"底层内核如何改变视频生成速度"}',
            )
            db.add(source)
            db.flush()
            supporting = SourceItem(
                provider="x2pdf",
                platform="x",
                external_id="wechat-api-supporting",
                canonical_url="https://x.com/kernel/article/supporting",
                author_handle="comparison_author",
                author_name="Comparison Author",
                content_kind="article",
                text_original=(
                    "对比来源说明另一套实现先做路由再执行专家计算，"
                    "并明确区分局部内核测试和端到端结果。"
                ) * 5,
                structured_content_json='{"title":"另一套实现的证据"}',
            )
            db.add(supporting)
            db.flush()
            draft = DraftRevision(
                source_id=source.id,
                version=1,
                style="explain",
                title="视频生成提速，关键可能不在换模型",
                body=(
                    "一个视频模型里最耗时间的计算，被重新写成了面向新一代 GPU 的底层内核。\n\n"
                    "VSA 可以理解为先筛掉大量无效 token，只让真正重要的部分参与计算。\n\n"
                    "作者在 Blackwell GPU 上展示了局部测试结果，但它不等于端到端视频生成也会快同样倍数。"
                ),
                tags="AI工程,CUDA,视频生成",
                provenance_json="{}",
            )
            db.add(draft)
            db.commit()
            source_id = source.id
            draft_id = draft.id
            supporting_id = supporting.id

        catalog = client.get("/api/platforms/catalog")
        assert catalog.status_code == 200, catalog.text
        catalog_data = catalog.json()
        assert len(catalog_data["wechat_themes"]) == 6
        assert any(item["id"] == "wechat-editorial-adapter" for item in catalog_data["skill_packs"])
        assert catalog_data["platform_capabilities"]["wechat"]["ratios"] == ["21:9", "1:1"]

        created = client.post(
            "/api/platforms/wechat/variants",
            json={
                "source_id": source_id,
                "supporting_source_ids": [supporting_id],
                "material_refs": [
                    f"source:{source_id}",
                    f"source:{supporting_id}",
                    f"draft:{draft_id}",
                    f"source:{manual_source['id']}",
                ],
                "draft_id": draft_id,
                "theme": "graphite",
                "mode": "adapt",
                "include_citations": True,
                "include_illustration_plan": True,
                "author": "EasyMaker",
            },
        )
        assert created.status_code == 201, created.text
        variant = created.json()
        assert variant["version"] == 1
        assert variant["platform"] == "wechat"
        assert variant["theme"] == "graphite"
        assert "来源与延伸阅读" in variant["body_markdown"]
        metadata = json.loads(variant["metadata_json"])
        assert metadata["evidence_source_ids"] == [
            source_id,
            supporting_id,
            manual_source["id"],
        ]
        assert metadata["evidence_sources"][1]["role"] == "supporting"
        assert metadata["input_material_refs"] == [
            f"source:{source_id}",
            f"source:{supporting_id}",
            f"draft:{draft_id}",
            f"source:{manual_source['id']}",
        ]
        assert {item["kind"] for item in metadata["input_materials"]} == {
            "source",
            "draft_revision",
        }
        assert "另一套实现" in variant["body_markdown"]
        assert "本地作者" in variant["body_markdown"]
        assert metadata["visual_handoff_mode"] == "codex_skill_prompt_upload"
        assert metadata["visual_prompts"][0]["slot_id"] == "cover_visual"
        assert any(item["kind"] == "section" for item in metadata["visual_prompts"])
        assert all("不得出现中文、英文" in item["prompt"] for item in metadata["visual_prompts"])

        extended_body = variant["body_markdown"] + "\n\n" + "\n\n".join(
            f"## 验收章节 {index}\n这是第 {index} 个需要独立配图 Prompt 的正文部分。"
            for index in range(1, 8)
        )
        revised = client.put(
            f"/api/platforms/variants/{variant['id']}",
            json={
                "title": "不换模型，底层内核也能改变视频生成速度",
                "subtitle": "从 VSA 到 Blackwell 数据搬运",
                "summary": "这次优化展示了模型之外的另一条性能路径。",
                "body_markdown": extended_body,
                "tags": variant["tags"],
                "theme": "vermillion",
            },
        )
        assert revised.status_code == 200, revised.text
        revised_variant = revised.json()
        assert revised_variant["version"] == 2
        assert revised_variant["created_by"] == "human"
        assert revised_variant["theme"] == "vermillion"

        revised_metadata = json.loads(revised_variant["metadata_json"])
        acceptance_prompts = [
            item
            for item in revised_metadata["visual_prompts"]
            if str(item.get("after_heading") or "").startswith("验收章节")
        ]
        assert len(acceptance_prompts) == 7
        section_slot = next(
            item for item in revised_metadata["visual_prompts"] if item["kind"] == "section"
        )
        image_buffer = io.BytesIO()
        Image.new("RGB", (1600, 900), (82, 96, 122)).save(image_buffer, format="PNG")
        uploaded = client.post(
            f"/api/platforms/variants/{revised_variant['id']}/visuals/{section_slot['slot_id']}",
            files={"file": ("section.png", image_buffer.getvalue(), "image/png")},
        )
        assert uploaded.status_code == 200, uploaded.text
        uploaded_variant = uploaded.json()
        uploaded_metadata = json.loads(uploaded_variant["metadata_json"])
        uploaded_slot = next(
            item
            for item in uploaded_metadata["visual_prompts"]
            if item["slot_id"] == section_slot["slot_id"]
        )
        assert uploaded_slot["asset_id"].startswith("asset_")
        assert uploaded_variant["status"] == "draft"
        asset_file = client.get(f"/api/assets/{uploaded_slot['asset_id']}/file")
        assert asset_file.status_code == 200
        assert asset_file.headers["content-type"].startswith("image/")

        rendered = client.post(
            f"/api/platforms/variants/{uploaded_variant['id']}/render",
            json={"package": True},
        )
        assert rendered.status_code == 200, rendered.text
        result = rendered.json()
        assert result["variant"]["status"] == "packaged"
        assert result["validation"]["errors"] == []
        assert {"markdown", "html", "preview", "wide", "square", "visual_handoff", "manifest", "package"} <= set(
            result["download_urls"]
        )
        assert f"visual_{section_slot['slot_id']}" in result["download_urls"]

        preview = client.get(result["preview_url"])
        assert preview.status_code == 200
        assert "复制到公众号" in preview.text
        assert f"/api/assets/{uploaded_slot['asset_id']}/file" in preview.text
        clean_html = client.get(result["download_urls"]["html"])
        assert clean_html.status_code == 200
        assert "<style" not in clean_html.text
        assert "<script" not in clean_html.text
        assert "illustrations/section_" in clean_html.text
        handoff = client.get(result["download_urls"]["visual_handoff"])
        assert handoff.status_code == 200
        assert "公众号视觉交接清单" in handoff.text
        assert "只输出一张完成图" in handoff.text
        package = client.get(result["download_urls"]["package"])
        assert package.status_code == 200
        assert package.headers["content-type"].startswith("application/zip")
        with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
            names = set(archive.namelist())
            assert "visual-handoff.md" in names
            assert any(name.startswith("illustrations/section_") for name in names)
            assert "illustrations/visual-handoff.md" not in names

        listed = client.get(f"/api/platforms/variants?platform=wechat&source_id={source_id}")
        assert listed.status_code == 200
        assert [item["version"] for item in listed.json()] == [2, 1]

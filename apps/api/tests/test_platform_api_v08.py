from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


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

        revised = client.put(
            f"/api/platforms/variants/{variant['id']}",
            json={
                "title": "不换模型，底层内核也能改变视频生成速度",
                "subtitle": "从 VSA 到 Blackwell 数据搬运",
                "summary": "这次优化展示了模型之外的另一条性能路径。",
                "body_markdown": variant["body_markdown"],
                "tags": variant["tags"],
                "theme": "vermillion",
            },
        )
        assert revised.status_code == 200, revised.text
        revised_variant = revised.json()
        assert revised_variant["version"] == 2
        assert revised_variant["created_by"] == "human"
        assert revised_variant["theme"] == "vermillion"

        rendered = client.post(
            f"/api/platforms/variants/{revised_variant['id']}/render",
            json={"package": True},
        )
        assert rendered.status_code == 200, rendered.text
        result = rendered.json()
        assert result["variant"]["status"] == "packaged"
        assert result["validation"]["errors"] == []
        assert {"markdown", "html", "preview", "wide", "square", "manifest", "package"} <= set(
            result["download_urls"]
        )

        preview = client.get(result["preview_url"])
        assert preview.status_code == 200
        assert "复制到公众号" in preview.text
        clean_html = client.get(result["download_urls"]["html"])
        assert clean_html.status_code == 200
        assert "<style" not in clean_html.text
        assert "<script" not in clean_html.text
        package = client.get(result["download_urls"]["package"])
        assert package.status_code == 200
        assert package.headers["content-type"].startswith("application/zip")

        listed = client.get(f"/api/platforms/variants?platform=wechat&source_id={source_id}")
        assert listed.status_code == 200
        assert [item["version"] for item in listed.json()] == [2, 1]

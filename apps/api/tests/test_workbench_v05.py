from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image


def test_skill_pipeline_transform_and_storyboard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("X2RED_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("X2RED_MEDIA_DIR", str(tmp_path / "assets"))
    monkeypatch.setenv("X2RED_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("X2RED_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("X2RED_BROWSER_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("X2RED_DOWNLOAD_MEDIA", "false")
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

    from app.domain.models import SourceItem

    with TestClient(main_module.app) as client:
        with db_session.SessionLocal() as db:
            source = SourceItem(
                provider="fxtwitter",
                platform="x",
                external_id="workbench-1",
                canonical_url="https://x.com/designer/status/workbench-1",
                author_handle="designer",
                author_name="Design Author",
                text_original=(
                    "A navigation pattern combines tabs with a contextual dropdown. "
                    "The author calls it a possible answer to increasingly complex app navigation."
                ),
                metrics_json="{}",
            )
            db.add(source)
            db.commit()
            db.refresh(source)
            source_id = source.id

        service = client.app.state.editorial_service
        responses = iter(
            [
                {
                    "topic": "Tab 与下拉菜单正在合并成新的导航模式",
                    "one_sentence_summary": "设计师开始用标签承载主路径，再用下拉菜单容纳复杂操作。",
                    "verified_facts": [
                        {"statement": "原帖描述了标签与上下文下拉菜单的组合", "source_index": 1}
                    ],
                    "author_claims": [
                        {"statement": "作者认为它可能缓解复杂应用的导航压力", "source_index": 1}
                    ],
                    "uncertainties": ["这种模式是否能在真实产品中降低认知成本仍需验证"],
                    "audience_value": ["帮助产品设计师区分主导航和上下文操作"],
                    "angles": [
                        {
                            "name": "复杂产品的导航分层",
                            "thesis": "这不是多加一个菜单，而是重新分配导航职责",
                            "why": "原帖同时提到标签和上下文操作",
                        }
                    ],
                    "recommended_angle": {
                        "name": "复杂产品的导航分层",
                        "reason": "它能把一个新名词转化为可复用的设计判断。",
                    },
                    "title_candidates": ["Tab 和下拉菜单为何开始合流"],
                    "outline": [],
                    "avoid": ["不要把作者设想写成行业趋势"],
                },
                {
                    "title": "Tab 和下拉菜单为何开始合流",
                    "body": "先说结论\n\n这不是给标签页再塞一个菜单，而是在复杂产品里重新分配导航职责。",
                    "tags": ["UI设计", "交互设计", "产品设计", "导航设计"],
                    "claims": [
                        {
                            "statement": "原帖描述了标签与上下文下拉菜单的组合",
                            "source_index": 1,
                            "verification": "source_only",
                        }
                    ],
                },
                {
                    "title": "Tab 和下拉菜单为何开始合流",
                    "body": (
                        "先说结论\n\n它不是给标签页硬塞一个菜单，而是在复杂产品里重新分配导航职责。"
                        "\n\n标签负责稳定的主路径，下拉菜单承接只在当前场景出现的操作。"
                    ),
                    "tags": ["UI设计", "交互设计", "产品设计", "导航设计"],
                },
            ]
        )

        async def fake_chat_json(**_: object) -> dict:
            return next(responses)

        monkeypatch.setattr(service, "_chat_json", fake_chat_json)

        generated = client.post(
            f"/api/sources/{source_id}/drafts",
            json={"style": "explain"},
        )
        assert generated.status_code == 200, generated.text
        draft = generated.json()
        provenance = json.loads(draft["provenance_json"])
        assert provenance["generator"] == "model-skill-pipeline"
        assert provenance["quality_passes"] == [
            "editorial.analysis",
            "writing.draft",
            "writing.de_translate",
        ]
        assert provenance["editorial_analysis"]["recommended_angle"]["name"] == "复杂产品的导航分层"
        assert "硬塞一个菜单" in draft["body"]

        async def fake_transform(**_: object) -> dict:
            return {
                "title": "复杂产品需要新的导航分层",
                "body": "这不是多一个控件，而是把稳定路径和临时操作分开。",
                "tags": ["UI设计", "交互设计", "产品设计"],
            }

        monkeypatch.setattr(service, "_chat_json", fake_transform)
        transformed = client.post(
            f"/api/drafts/{draft['id']}/transform",
            json={"action": "stronger_insight", "instruction": ""},
        )
        assert transformed.status_code == 200, transformed.text
        transformed_draft = transformed.json()
        assert transformed_draft["version"] == 2
        assert transformed_draft["created_by"] == "model-polish"
        assert transformed_draft["title"] == "复杂产品需要新的导航分层"

        cards = client.post(
            f"/api/drafts/{draft['id']}/cards",
            json={"template": "clean_news", "max_cards": 7},
        )
        assert cards.status_code == 200, cards.text
        render = cards.json()
        specs = json.loads(render["spec_json"])
        kinds = [spec["kind"] for spec in specs]
        assert kinds[0] == "cover"
        assert "thesis" in kinds
        assert "facts" in kinds
        assert kinds[-1] == "source"
        assert specs[0]["renderer"] in {"html-playwright", "pillow-fallback"}
        paths = json.loads(render["output_paths_json"])
        with Image.open(paths[0]) as image:
            assert image.size == (1242, 1656)

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["version"] == "0.7.0"
        assert health.json()["model_configured"] is True
        assert health.json()["editorial_pipeline"] == "multi-agent-signal-to-story"
        assert health.json()["intelligence_pipeline"] == "monitor-score-l1-l2"
        assert health.json()["card_renderer"] == "html-playwright"

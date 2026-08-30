from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def wait_for_job(client: TestClient, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    latest: dict = {}
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200, response.text
        latest = response.json()
        if latest["state"] in {"succeeded", "failed", "dead_letter"}:
            return latest
        time.sleep(0.05)
    return latest


def test_style_training_uses_originals_held_out_and_feedback(
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
    from app.db.schema import upgrade_database

    upgrade_database(db_session.settings.database_url)
    importlib.reload(main_module)

    with TestClient(main_module.app) as client:
        responses = iter(
            [
                {
                    "identity": "技术实践者",
                    "reader_relationship": "与读者一起拆解问题",
                    "fact_boundaries": ["不编造亲历"],
                    "language_rhythm": "短段落，关键判断后停顿",
                    "paragraph_habits": ["先结果后机制"],
                    "judgment_style": "证据后给判断",
                    "article_type_patterns": {"技术拆解": ["结果", "机制", "意义"]},
                    "forbidden_expressions": ["总的来说", "不难发现"],
                    "positive_examples": ["先把结果讲明白"],
                    "negative_examples": ["连续三段匀速排比"],
                    "confidence_notes": ["基于三篇同类型样本"],
                },
                {
                    "held_out_differences": ["留出样本段落更短"],
                    "feedback_adjustments": ["作者明确反对总结腔"],
                    "rules_to_keep": ["先结果后机制"],
                    "rules_to_remove": [],
                    "final_rules": {
                        "identity": "技术实践者",
                        "reader_relationship": "与读者一起拆解问题",
                        "fact_boundaries": ["不编造亲历"],
                        "language_rhythm": "短段落，关键判断后停顿",
                        "paragraph_habits": ["先结果后机制"],
                        "judgment_style": "证据后给判断",
                        "article_type_patterns": {"技术拆解": ["结果", "机制", "意义"]},
                        "forbidden_expressions": ["总的来说", "不难发现", "值得注意的是"],
                        "positive_examples": ["先把结果讲明白"],
                        "negative_examples": ["连续三段匀速排比"],
                    },
                    "remaining_uncertainties": [],
                },
            ]
        )
        calls: list[dict] = []

        async def fake_chat_json(**kwargs):
            calls.append(kwargs)
            return next(responses)

        monkeypatch.setattr(main_module.app.state.writing_service.editorial, "_chat_json", fake_chat_json)

        queued = client.post(
            "/api/writing/styles/train",
            json={
                "name": "我的技术写作",
                "description": "用于技术长文",
                "original_samples": [
                    "第一篇原创：先说工程结果，再解释方法。",
                    "第二篇原创：用具体数字支持判断。",
                    "第三篇原创：短段落，不使用总结腔。",
                ],
                "held_out_samples": ["留出样本：开头直接进入问题。"],
                "author_feedback": ["删掉‘值得注意的是’，太像 AI。"],
                "confirm_original_or_authorized": True,
            },
        )
        assert queued.status_code == 202, queued.text
        job = wait_for_job(client, queued.json()["id"])
        assert job["state"] == "succeeded", job
        result = json.loads(job["result_json"])
        assert result["name"] == "我的技术写作"
        assert result["version"] == 1
        assert len(calls) == 2
        assert "只分析作者明确授权的原创文章" in calls[0]["user_prompt"]
        assert "留出样本" in calls[1]["user_prompt"]
        assert "作者真实改稿反馈" in calls[1]["user_prompt"]

        styles = client.get("/api/writing/styles")
        assert styles.status_code == 200
        profile = next(item for item in styles.json() if item["name"] == "我的技术写作")
        rules = json.loads(profile["rules_json"])
        forbidden = json.loads(profile["forbidden_json"])
        samples = json.loads(profile["samples_json"])
        assert rules["paragraph_habits"] == ["先结果后机制"]
        assert "值得注意的是" in forbidden
        assert samples["held_out_samples"]
        assert samples["author_feedback"]
        assert samples["rights"]["confirmed_original_or_authorized"] is True
        assert rules["author_overrides"][0]["rule"].startswith("删掉")
        assert rules["rule_priority"][0] == "explicit_author_override"

        skills = client.get("/api/settings/skills").json()
        assert "writing.style_train" in {item["skill_name"] for item in skills}
        health = client.get("/health").json()
        assert health["style_pipeline"] == (
            "authorized-originals-held-out-author-overrides-short-exemplars-real-feedback"
        )
        assert health["writing_quality_mode"] == "production"
        assert health["title_tournament"] is True

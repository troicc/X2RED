from __future__ import annotations

import importlib
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


def test_rejected_brief_returns_to_editor_with_author_feedback(
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

    from app.domain.models import SourceItem

    with TestClient(main_module.app) as client:
        with db_session.SessionLocal() as db:
            source = SourceItem(
                provider="x2pdf",
                platform="x",
                external_id="gate-article",
                canonical_url="https://x.com/author/article/gate",
                author_handle="author",
                author_name="Author",
                content_kind="article",
                text_original="A source about GPU kernel optimization.",
                metrics_json="{}",
            )
            db.add(source)
            db.commit()
            db.refresh(source)
            source_id = source.id

        prompts: list[str] = []

        async def fake_chat_json(**kwargs):
            prompts.append(kwargs["user_prompt"])
            return {
                "reader": "技术读者",
                "article_promise": "解释 GPU 优化",
                "main_thesis": "第一次主线" if len(prompts) == 1 else "聚焦底层内核而不是模型",
                "reader_hook": "先看结果",
                "must_use": [],
                "must_not_claim": [],
                "article_type": "explain",
                "tone": "直接",
                "open_questions": [],
                "success_criteria": [],
            }

        monkeypatch.setattr(
            main_module.app.state.writing_service.editorial,
            "_chat_json",
            fake_chat_json,
        )
        project = client.post(
            "/api/writing/projects",
            json={"source_id": source_id, "mode": "studio", "budget_limit_cents": 10},
        ).json()
        queued = client.post(
            f"/api/writing/projects/{project['id']}/run",
            json={"continuous": True},
        )
        assert wait_for_job(client, queued.json()["id"])["state"] == "succeeded"
        first = client.get(f"/api/writing/projects/{project['id']}").json()
        brief_v1 = next(
            item for item in first["artifacts"] if item["artifact_type"] == "editorial_brief"
        )
        assert brief_v1["version"] == 1

        rejected = client.post(
            f"/api/writing/projects/{project['id']}/artifacts/{brief_v1['id']}/approve",
            json={"approved": False, "note": "不要泛讲 GPU，聚焦底层内核为什么比换模型更关键。"},
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["state"] == "clarifying"
        assert rejected.json()["current_stage"] == "editorial_brief"

        rerun = client.post(
            f"/api/writing/projects/{project['id']}/run",
            json={"continuous": True},
        )
        assert wait_for_job(client, rerun.json()["id"])["state"] == "succeeded"
        second = client.get(f"/api/writing/projects/{project['id']}").json()
        briefs = [
            item for item in second["artifacts"] if item["artifact_type"] == "editorial_brief"
        ]
        assert [item["version"] for item in briefs] == [1, 2]
        assert second["state"] == "awaiting_brief_approval"
        assert "作者最近一次阶段决定" in prompts[1]
        assert "聚焦底层内核" in prompts[1]
        assert "不要把已否决版本原样返回" in prompts[1]

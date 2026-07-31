from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_x2pdf_bridge_lifecycle_skills_and_publish_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("X2RED_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("X2RED_MEDIA_DIR", str(tmp_path / "assets"))
    monkeypatch.setenv("X2RED_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("X2RED_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("X2RED_BROWSER_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("X2RED_MODEL_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    monkeypatch.setenv("X2RED_MODEL_NAME", "glm-5.2")

    from app.core.config import get_settings

    get_settings.cache_clear()

    import app.db.session as db_session
    import app.main as main_module

    importlib.reload(db_session)
    importlib.reload(main_module)

    document = {
        "version": 1,
        "type": "article",
        "source": {
            "url": "https://x.com/designer/article/1234567890",
            "postId": "1234567890",
            "capturedAt": "2026-07-31T12:00:00Z",
        },
        "metadata": {
            "title": "Designing navigation for increasingly complex products",
            "authorName": "Design Author",
            "authorHandle": "designer",
            "publishedAt": "2026-07-31T08:00:00Z",
            "coverImage": "https://pbs.twimg.com/media/article-cover.jpg",
        },
        "blocks": [
            {"type": "heading", "level": 2, "html": "<strong>The navigation problem</strong>"},
            {
                "type": "paragraph",
                "html": "Tabs keep stable destinations visible, while a contextual dropdown holds secondary actions.",
            },
            {"type": "blockquote", "paragraphs": ["Complexity should be organized, not hidden."]},
            {"type": "code", "language": "json", "text": '{"pattern":"tab-dropdown"}'},
            {
                "type": "image",
                "url": "https://pbs.twimg.com/media/article-diagram.jpg",
                "alt": "Navigation diagram",
            },
        ],
        "diagnostics": {"acquisition": {"method": "captured-response"}},
    }

    with TestClient(main_module.app) as client:
        imported = client.post(
            "/api/integrations/x2pdf/documents",
            json={"document": document},
            headers={"Origin": "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        )
        assert imported.status_code == 200, imported.text
        result = imported.json()
        assert result["content_kind"] == "article"
        assert result["block_count"] == 5
        assert result["asset_count"] == 2
        source_id = result["source_id"]

        detail = client.get(f"/api/sources/{source_id}")
        assert detail.status_code == 200, detail.text
        source = detail.json()
        assert source["provider"] == "x2pdf"
        assert source["content_kind"] == "article"
        assert source["workspace_state"] == "active"
        assert "navigation problem" in source["text_original"]
        assert "article-diagram.jpg" in source["structured_content_json"]
        assert len(source["assets"]) == 2

        note = client.put(
            f"/api/sources/{source_id}/note",
            json={"editor_note": "重点写复杂产品如何分配稳定路径和临时操作。"},
        )
        assert note.status_code == 200
        assert "稳定路径" in note.json()["editor_note"]

        active = client.get("/api/sources?workspace_state=active")
        assert any(item["id"] == source_id for item in active.json())
        archived = client.post(f"/api/sources/{source_id}/archive")
        assert archived.status_code == 200
        assert archived.json()["workspace_state"] == "archived"
        assert not any(
            item["id"] == source_id
            for item in client.get("/api/sources?workspace_state=active").json()
        )
        assert any(
            item["id"] == source_id
            for item in client.get("/api/sources?workspace_state=archived").json()
        )
        restored = client.post(f"/api/sources/{source_id}/restore")
        assert restored.status_code == 200
        assert restored.json()["workspace_state"] == "active"

        skills = client.get("/api/settings/skills")
        assert skills.status_code == 200
        assert {item["skill_name"] for item in skills.json()} >= {
            "editorial.analysis",
            "writing.draft",
            "visual.storyboard",
        }
        disabled = client.put(
            "/api/settings/skills/writing.de_translate",
            json={
                "enabled": False,
                "model_name": "glm-5.2",
                "reasoning_effort": "low",
                "prompt_version": "v1",
            },
        )
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False

        from app.domain.models import DraftRevision, PublishState, PublishTask

        with db_session.SessionLocal() as db:
            draft = DraftRevision(
                source_id=source_id,
                version=1,
                title="Test title",
                body="Test body",
                tags="test",
            )
            db.add(draft)
            db.flush()
            task = PublishTask(
                draft_id=draft.id,
                state=PublishState.awaiting_user_confirmation.value,
                title=draft.title,
                body=draft.body,
                tags=draft.tags,
            )
            db.add(task)
            db.commit()
            task_id = task.id

        published = client.post(
            f"/api/publish/{task_id}/mark-published",
            json={"result_url": "https://www.xiaohongshu.com/explore/test-note"},
        )
        assert published.status_code == 200, published.text
        after_publish = client.get(f"/api/sources/{source_id}").json()
        assert after_publish["workspace_state"] == "archived"
        assert after_publish["published_count"] == 1
        assert after_publish["last_published_at"] is not None

        deleted = client.delete(f"/api/sources/{source_id}")
        assert deleted.status_code == 204, deleted.text
        assert client.get(f"/api/sources/{source_id}").status_code == 404

        health = client.get("/health").json()
        assert health["version"] == "0.6.1"
        assert health["editorial_pipeline"] == "reader-first-skill-pipeline"
        assert health["x2pdf_bridge"] == "/api/integrations/x2pdf/documents"

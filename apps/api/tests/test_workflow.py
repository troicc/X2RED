from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("X2RED_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("X2RED_MEDIA_DIR", str(tmp_path / "assets"))
    monkeypatch.setenv("X2RED_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("X2RED_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("X2RED_BROWSER_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("X2RED_DOWNLOAD_MEDIA", "false")

    from app.core.config import get_settings

    get_settings.cache_clear()

    import importlib
    import app.db.session as db_session
    import app.main as main_module

    importlib.reload(db_session)
    importlib.reload(main_module)

    class DummyProvider:
        name = "fxtwitter"

        async def get_thread(self, post_id: str) -> dict:
            return {
                "code": 200,
                "status": {
                    "type": "status",
                    "id": post_id,
                    "url": f"https://x.com/tester/status/{post_id}",
                    "text": "A new local-first editorial workflow is available.",
                    "created_at": "2026-07-31T01:00:00+00:00",
                    "likes": 12,
                    "reposts": 3,
                    "quotes": 1,
                    "replies": 2,
                    "author": {
                        "id": "u1",
                        "screen_name": "tester",
                        "name": "Test Author",
                    },
                    "media": {
                        "photos": [
                            {
                                "type": "photo",
                                "url": "https://pbs.twimg.com/media/test.jpg",
                                "width": 1600,
                                "height": 900,
                                "altText": "test image",
                            }
                        ]
                    },
                },
                "thread": [
                    {
                        "type": "status",
                        "id": "9876543211",
                        "url": "https://x.com/tester/status/9876543211",
                        "text": "The second post explains the review gate.",
                        "created_at": "2026-07-31T01:01:00+00:00",
                        "author": {
                            "id": "u1",
                            "screen_name": "tester",
                            "name": "Test Author",
                        },
                    }
                ],
            }

        async def get_conversation(self, post_id: str) -> dict:
            return await self.get_thread(post_id)

        async def close(self) -> None:
            return None

    with TestClient(main_module.app) as test_client:
        dummy = DummyProvider()
        main_module.app.state.provider = dummy
        main_module.app.state.intake_service.provider = dummy
        yield test_client


def test_durable_intake_job(client: TestClient) -> None:
    queued = client.post(
        "/api/jobs/intake",
        json={
            "url": "https://x.com/tester/status/8876543210",
            "mode": "thread",
            "download_media": False,
        },
    )
    assert queued.status_code == 202, queued.text
    job = queued.json()
    assert job["state"] in {"pending", "running"}

    for _ in range(100):
        current = client.get(f"/api/jobs/{job['id']}")
        assert current.status_code == 200
        job = current.json()
        if job["state"] in {"succeeded", "failed"}:
            break
        time.sleep(0.05)

    assert job["state"] == "succeeded", job
    result = json.loads(job["result_json"])
    assert result["external_id"] == "8876543210"
    assert result["imported_count"] == 2
    assert client.get(f"/api/sources/{result['source_id']}").status_code == 200


def test_end_to_end_editorial_workflow(client: TestClient, tmp_path: Path) -> None:
    intake = client.post(
        "/api/intake/x",
        json={
            "url": "https://x.com/tester/status/9876543210",
            "mode": "thread",
            "download_media": False,
        },
    )
    assert intake.status_code == 200, intake.text
    intake_data = intake.json()
    assert intake_data["imported_count"] == 2
    assert intake_data["asset_count"] == 1
    source_id = intake_data["source_id"]

    detail = client.get(f"/api/sources/{source_id}")
    assert detail.status_code == 200
    assert detail.json()["author_handle"] == "tester"
    assert detail.json()["rights_status"] == "needs_review"
    assert len(detail.json()["assets"]) == 1

    rights = client.put(
        f"/api/sources/{source_id}/rights",
        json={
            "source_status": "limited_quote",
            "source_note": "仅引用文本并保留原始链接",
            "asset_status": "licensed",
            "asset_note": "测试授权",
            "apply_to_related": True,
        },
    )
    assert rights.status_code == 200, rights.text
    assert rights.json()["rights_status"] == "limited_quote"
    assert rights.json()["assets"][0]["rights_status"] == "licensed"

    generated = client.post(
        f"/api/sources/{source_id}/drafts",
        json={"style": "explain"},
    )
    assert generated.status_code == 200, generated.text
    first_draft = generated.json()
    assert first_draft["version"] == 1
    assert "先说结论" in first_draft["body"]

    revised = client.put(
        f"/api/drafts/{first_draft['id']}",
        json={
            "title": "本地编辑工作流",
            "body": "这是人工修订后的正文。",
            "tags": "本地工具,内容编辑",
        },
    )
    assert revised.status_code == 200
    revised_draft = revised.json()
    assert revised_draft["version"] == 2
    assert revised_draft["created_by"] == "human"

    blocked = client.post(
        f"/api/publish/drafts/{revised_draft['id']}/prepare",
        json={"include_cards": True, "include_source_assets": False},
    )
    assert blocked.status_code == 400

    incomplete_review = client.post(
        f"/api/drafts/{revised_draft['id']}/review",
        json={"decision": "approved", "reason": "", "facts_checked": False, "rights_checked": True},
    )
    assert incomplete_review.status_code == 400

    cards = client.post(
        f"/api/drafts/{revised_draft['id']}/cards",
        json={"template": "warm_editorial", "max_cards": 6},
    )
    assert cards.status_code == 200, cards.text
    card_render = cards.json()
    card_paths = json.loads(card_render["output_paths_json"])
    assert len(card_paths) >= 2
    assert all(Path(path).is_file() for path in card_paths)

    review = client.post(
        f"/api/drafts/{revised_draft['id']}/review",
        json={
            "decision": "approved",
            "reason": "已核对来源",
            "facts_checked": True,
            "rights_checked": True,
        },
    )
    assert review.status_code == 200

    prepared = client.post(
        f"/api/publish/drafts/{revised_draft['id']}/prepare",
        json={"include_cards": True, "include_source_assets": False},
    )
    assert prepared.status_code == 200, prepared.text
    task = prepared.json()
    assert task["state"] == "packaged"
    package_path = Path(task["package_path"])
    assert package_path.is_file()
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    assert payload["title"] == "本地编辑工作流"
    assert payload["body"] == "这是人工修订后的正文。"
    assert payload["card_render_id"] == card_render["id"]
    assert len(payload["assets"]) >= 2
    assert all(Path(path).is_file() for path in payload["assets"])


def test_rejects_non_x_url(client: TestClient) -> None:
    response = client.post(
        "/api/intake/x",
        json={"url": "https://example.com/status/12345", "mode": "thread"},
    )
    assert response.status_code == 400

from __future__ import annotations

import importlib
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.scoring import baseline_median, calculate_score, core_engagement


def test_scoring_uses_relative_and_breakout_signals() -> None:
    baseline = baseline_median([10, 11, 9, 10, 12, 8])
    engagement = core_engagement({"likes": 350, "reposts": 10, "quotes": 5, "replies": 20})
    score = calculate_score(
        current_engagement=engagement,
        baseline_value=baseline,
        followers=1_000,
        views=50_000,
        age_hours=4,
    )
    assert score.grade == "T3"
    assert score.r_value > 8
    assert score.m_value > 0.3
    assert score.baseline_value == 10


def wait_for_job(client: TestClient, job_id: str, timeout: float = 10.0) -> dict:
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


def test_signal_monitor_and_multi_agent_writing_studio(
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
    monkeypatch.delenv("X2RED_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("X2RED_MODEL_NAME", raising=False)
    monkeypatch.delenv("X2RED_MODEL_API_KEY", raising=False)

    from app.core.config import get_settings

    get_settings.cache_clear()

    import app.db.session as db_session
    import app.main as main_module

    importlib.reload(db_session)
    importlib.reload(main_module)

    class DummyProvider:
        name = "fxtwitter"

        async def get_profile(self, handle: str, *, about_account: bool = True) -> dict:
            return {
                "code": 200,
                "user": {
                    "id": "author-1",
                    "screen_name": handle,
                    "name": "Kernel Author",
                    "followers": 1_000,
                    "about_account": {"available": about_account},
                },
            }

        async def get_timeline(
            self,
            handle: str,
            *,
            count: int = 20,
            cursor: str | None = None,
            since: int | None = None,
            media_only: bool = False,
        ) -> dict:
            now = datetime.now(UTC)
            results = []
            for index in range(8):
                breakout = index == 0
                results.append(
                    {
                        "type": "status",
                        "id": f"post-{index}",
                        "url": f"https://x.com/{handle}/status/post-{index}",
                        "text": (
                            "A Blackwell CUDA kernel cuts the slowest attention step dramatically."
                            if breakout
                            else f"Routine engineering note {index}."
                        ),
                        "created_at": (now - timedelta(hours=index + 1)).isoformat(),
                        "likes": 1000 if breakout else 10,
                        "reposts": 0,
                        "quotes": 0,
                        "replies": 0,
                        "views": 50_000 if breakout else 500,
                        "author": {
                            "id": "author-1",
                            "screen_name": handle,
                            "name": "Kernel Author",
                        },
                    }
                )
            return {
                "code": 200,
                "results": results[:count],
                "cursor": {"bottom": cursor or "next"},
            }

        async def search(self, *args, **kwargs) -> dict:
            return {"code": 200, "results": [], "cursor": {}}

        async def get_quotes(self, *args, **kwargs) -> dict:
            return {"code": 200, "results": [], "cursor": {}}

        async def trends(self, *, count: int = 20) -> dict:
            return {"code": 200, "trends": []}

        async def get_status(self, post_id: str) -> dict:
            return {"code": 404}

        async def get_thread(self, post_id: str) -> dict:
            return {"code": 404}

        async def get_conversation(self, post_id: str) -> dict:
            return {"code": 404}

        async def close(self) -> None:
            return None

    with TestClient(main_module.app) as client:
        dummy = DummyProvider()
        main_module.app.state.provider = dummy
        main_module.app.state.discovery_service.provider = dummy
        main_module.app.state.signal_service.provider = dummy
        main_module.app.state.signal_service.discovery.provider = dummy

        target_response = client.post(
            "/api/signals/targets",
            json={
                "name": "Kernel Author",
                "kind": "profile",
                "target": "kernel_author",
                "interval_minutes": 360,
                "enabled": True,
                "config": {"count": 8, "minimum_baseline_samples": 5},
            },
        )
        assert target_response.status_code == 201, target_response.text
        target = target_response.json()

        queued = client.post(f"/api/signals/targets/{target['id']}/run")
        assert queued.status_code == 202, queued.text
        job = wait_for_job(client, queued.json()["id"])
        assert job["state"] == "succeeded", job

        feed = client.get("/api/signals/feed?grade=T3")
        assert feed.status_code == 200, feed.text
        items = feed.json()
        assert len(items) == 1
        breakout = items[0]
        assert breakout["score"]["grade"] == "T3"
        assert breakout["score"]["r_value"] >= 50
        assert len(json.loads(breakout["score"]["baseline_sample_json"])) >= 5

        l1 = client.post(
            f"/api/signals/candidates/{breakout['candidate_id']}/analyze",
            json={"level": "l1"},
        )
        assert l1.status_code == 202, l1.text
        l1_job = wait_for_job(client, l1.json()["id"])
        assert l1_job["state"] == "succeeded", l1_job
        analyses = client.get(
            f"/api/signals/candidates/{breakout['candidate_id']}/analyses"
        ).json()
        analyses_by_level = {item["level"]: item for item in analyses}
        assert {"l1", "l2"} <= set(analyses_by_level)
        assert json.loads(analyses_by_level["l1"]["result_json"])["summary"]

        from app.domain.models import SourceItem

        with db_session.SessionLocal() as db:
            source = SourceItem(
                provider="x2pdf",
                platform="x",
                external_id="article-writing-1",
                canonical_url="https://x.com/kernel_author/article/1",
                author_handle="kernel_author",
                author_name="Kernel Author",
                content_kind="article",
                text_original=(
                    "The author rewrote a sparse attention kernel for Blackwell GPUs. "
                    "The local kernel benchmark improved from 7444 microseconds to 4719 microseconds."
                ),
                editor_note="重点解释为什么模型没换，底层内核却能显著提速。",
                metrics_json="{}",
            )
            db.add(source)
            db.commit()
            db.refresh(source)
            source_id = source.id

        project_response = client.post(
            "/api/writing/projects",
            json={
                "source_id": source_id,
                "mode": "fast",
                "reader": "关注 AI 工程但不写 CUDA 的技术读者",
                "promise": "看懂提速发生在哪一层",
                "main_thesis": "模型速度也取决于底层内核",
                "budget_limit_cents": 20,
            },
        )
        assert project_response.status_code == 201, project_response.text
        project_id = project_response.json()["id"]
        run = client.post(
            f"/api/writing/projects/{project_id}/run",
            json={"continuous": True},
        )
        assert run.status_code == 202, run.text
        run_job = wait_for_job(client, run.json()["id"], timeout=15)
        assert run_job["state"] == "succeeded", run_job

        project = client.get(f"/api/writing/projects/{project_id}").json()
        assert project["state"] == "completed"
        artifact_types = {item["artifact_type"] for item in project["artifacts"]}
        assert {
            "editorial_brief",
            "evidence_pack",
            "outline",
            "draft",
            "reader_review",
            "fact_review",
            "style_review",
            "revision_plan",
            "final_draft",
        } <= artifact_types
        assert len(project["runs"]) == 9

        drafts = client.get(f"/api/sources/{source_id}/drafts").json()
        assert drafts[0]["created_by"] == "multi-agent"
        provenance = json.loads(drafts[0]["provenance_json"])
        assert provenance["generator"] == "multi-agent-writing-studio"

        studio_project = client.post(
            "/api/writing/projects",
            json={"source_id": source_id, "mode": "studio", "budget_limit_cents": 20},
        ).json()
        studio_run = client.post(
            f"/api/writing/projects/{studio_project['id']}/run",
            json={"continuous": True},
        )
        assert wait_for_job(client, studio_run.json()["id"])["state"] == "succeeded"
        gated = client.get(f"/api/writing/projects/{studio_project['id']}").json()
        assert gated["state"] == "awaiting_brief_approval"
        brief = next(
            item
            for item in gated["artifacts"]
            if item["artifact_type"] == "editorial_brief"
        )
        approved = client.post(
            f"/api/writing/projects/{gated['id']}/artifacts/{brief['id']}/approve",
            json={"approved": True, "note": "主线确认"},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["state"] == "researching"

        health = client.get("/health").json()
        assert health["version"] == "0.12.0"
        assert health["intelligence_pipeline"] == "monitor-score-l1-l2"
        assert "three-reviews" in health["writing_pipeline"]
        assert health["platform_pipeline"] == (
            "reviewable-artifacts-shared-evidence-platform-variants"
        )
        assert health["review_pipeline"] == (
            "storyboard-module-tree-cover-brief-versioned-approval"
        )
        assert health["sqlite_wal"] is True

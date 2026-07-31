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

    from app.domain.models import SourceItem

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
            db.commit()
            db.refresh(source)
            source_id = source.id

        calls = 0

        async def fake_chat_json(**_kwargs):
            nonlocal calls
            calls += 1
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
        assert project["state"] == "drafting"
        assert "temporary model outage" in project["error"]
        artifact_types = {item["artifact_type"] for item in project["artifacts"]}
        assert {"editorial_brief", "evidence_pack", "outline"} <= artifact_types
        assert "draft" not in artifact_types

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

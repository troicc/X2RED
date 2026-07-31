from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_writing_project_freezes_style_profile_version(
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

    from app.domain.models import SourceItem
    from app.domain.studio import StyleProfile, WritingProject
    from app.domain.style_snapshot import WritingStyleSnapshot

    with TestClient(main_module.app) as client:
        with db_session.SessionLocal() as db:
            source = SourceItem(
                provider="x2pdf",
                platform="x",
                external_id="snapshot-article",
                canonical_url="https://x.com/author/article/snapshot",
                author_handle="author",
                author_name="Author",
                content_kind="article",
                text_original="A technical source used to verify immutable style rules.",
                metrics_json="{}",
            )
            profile = StyleProfile(
                name="技术写作",
                description="版本化测试",
                rules_json=json.dumps(
                    {
                        "identity": "技术实践者",
                        "paragraph_habits": ["先结果后机制"],
                    },
                    ensure_ascii=False,
                ),
                forbidden_json=json.dumps(["总的来说"], ensure_ascii=False),
                samples_json="{}",
                version=1,
            )
            db.add_all([source, profile])
            db.commit()
            db.refresh(source)
            db.refresh(profile)
            source_id = source.id
            profile_id = profile.id

        created = client.post(
            "/api/writing/projects",
            json={
                "source_id": source_id,
                "mode": "fast",
                "style_profile_id": profile_id,
                "budget_limit_cents": 20,
            },
        )
        assert created.status_code == 201, created.text
        project_id = created.json()["id"]

        with db_session.SessionLocal() as db:
            snapshot = db.query(WritingStyleSnapshot).filter_by(project_id=project_id).one()
            frozen_hash = snapshot.snapshot_hash
            frozen_payload = json.loads(snapshot.snapshot_json)
            assert snapshot.style_profile_version == 1
            assert frozen_payload["rules"]["paragraph_habits"] == ["先结果后机制"]
            assert frozen_payload["forbidden"] == ["总的来说"]

            profile = db.get(StyleProfile, profile_id)
            assert profile is not None
            profile.version = 2
            profile.rules_json = json.dumps(
                {"identity": "新版本", "paragraph_habits": ["先机制后结果"]},
                ensure_ascii=False,
            )
            profile.forbidden_json = json.dumps(["旧规则已删除"], ensure_ascii=False)
            db.commit()

            project = db.get(WritingProject, project_id)
            assert project is not None
            service = main_module.app.state.writing_service
            payload_after_update = service._style_payload(db, project)
            snapshot_after_update = service.style_snapshot(db, project_id)
            assert payload_after_update["rules"]["paragraph_habits"] == ["先结果后机制"]
            assert payload_after_update["forbidden"] == ["总的来说"]
            assert snapshot_after_update is not None
            assert snapshot_after_update.snapshot_hash == frozen_hash
            assert snapshot_after_update.style_profile_version == 1

        run = client.post(
            f"/api/writing/projects/{project_id}/run",
            json={"continuous": True},
        )
        assert run.status_code == 202, run.text

        # Structured fallback completes the same nine-role chain without a model.
        import time

        for _ in range(200):
            job = client.get(f"/api/jobs/{run.json()['id']}").json()
            if job["state"] in {"succeeded", "failed"}:
                break
            time.sleep(0.05)
        assert job["state"] == "succeeded", job

        drafts = client.get(f"/api/sources/{source_id}/drafts").json()
        assert drafts
        provenance = json.loads(drafts[0]["provenance_json"])
        assert provenance["style_profile_version"] == 1
        assert provenance["style_snapshot_hash"] == frozen_hash
        assert provenance["style_snapshot_id"]

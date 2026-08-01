from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image


def test_signal_promotion_and_light_series(
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

    from app.domain.discovery import DiscoveryCandidate, DiscoveryRun
    from app.domain.models import SourceItem
    from app.domain.studio import ContentAnalysis, WritingProject

    with TestClient(main_module.app) as client:
        with db_session.SessionLocal() as db:
            run = DiscoveryRun(provider="test", kind="search", query="生活节奏")
            db.add(run)
            db.flush()
            candidate = DiscoveryCandidate(
                run_id=run.id,
                dedupe_key="signal-light-v10",
                kind="status",
                external_id="signal-light-v10",
                canonical_url="https://x.com/example/status/100",
                author_handle="example",
                author_name="Example",
                text="越是着急的时代，越需要给普通生活留一点余地。",
                metadata_json=json.dumps({"likes": 120, "views": 8000}),
            )
            db.add(candidate)
            db.flush()
            analysis = ContentAnalysis(
                candidate_id=candidate.id,
                level="l2",
                status="succeeded",
                result_json=json.dumps(
                    {
                        "hook": "高压环境里，人们需要的不是更多命令，而是一点允许。",
                        "audience_triggers": ["长期工作压力", "照顾家庭后忽略自己"],
                        "distribution_mechanism": "一句可转发的共鸣判断",
                        "replicable_elements": ["短句", "生活物件", "留白"],
                        "writing_angles": ["给忙碌生活的一点安静"],
                        "fact_risks": ["不要把生活建议写成确定效果"],
                        "pattern_card": {},
                    },
                    ensure_ascii=False,
                ),
                evidence_json="{}",
                model_name="test-model",
                input_hash="signal-light-v10-l2",
            )
            db.add(analysis)
            db.commit()
            candidate_id = candidate.id

        feed = client.get("/api/signals/feed")
        assert feed.status_code == 200, feed.text
        item = next(value for value in feed.json() if value["candidate_id"] == candidate_id)
        assert item["l2_analysis"]["hook"].startswith("高压环境")

        promoted = client.post(
            f"/api/signals/candidates/{candidate_id}/promote",
            json={"mode": "studio"},
        )
        assert promoted.status_code == 201, promoted.text
        promoted_payload = promoted.json()
        assert promoted_payload["source_created"] is True
        assert "长期工作压力" in promoted_payload["reader"]

        with db_session.SessionLocal() as db:
            source = db.get(SourceItem, promoted_payload["source_id"])
            project = db.get(WritingProject, promoted_payload["project_id"])
            assert source is not None and project is not None
            structured = json.loads(source.structured_content_json)
            assert structured["signal_intelligence"]["l2"]["replicable_elements"]

        created = client.post(
            "/api/platforms/wechat/light/variants",
            json={
                "source_id": promoted_payload["source_id"],
                "recipe": "seasonal",
                "image_count": 4,
                "seasonal_topic": "入伏吃什么",
                "audience": "关注日常饮食的中年与年长读者",
                "theme": "zen",
            },
        )
        assert created.status_code == 201, created.text
        variant = created.json()
        assert variant["format"] == "light_series"
        metadata = json.loads(variant["metadata_json"])
        assert metadata["source_skill"]["repository"] == "LiamGvchi/gc-minimal-zine-poster"
        assert len(metadata["poster_specs"]) == 4

        rendered = client.post(
            f"/api/platforms/variants/{variant['id']}/render",
            json={"package": True},
        )
        assert rendered.status_code == 200, rendered.text
        payload = rendered.json()
        assert payload["variant"]["status"] == "packaged"
        files = payload["files"]
        poster_keys = sorted(key for key in files if key.startswith("poster_"))
        assert poster_keys == ["poster_01", "poster_02", "poster_03", "poster_04"]
        for key in poster_keys:
            with Image.open(files[key]) as image:
                assert image.size == (1200, 2000)
        assert Path(files["preview"]).is_file()
        assert Path(files["package"]).is_file()

        fresh = client.get(f"/api/platforms/variants/{variant['id']}").json()
        fresh_metadata = json.loads(fresh["metadata_json"])
        assert fresh_metadata["render_engine"] == "x2red-distinct-light-visual-v12"
        assert all(spec["final_prompt"].strip() for spec in fresh_metadata["poster_specs"])
        assert all(spec["visual_style"] for spec in fresh_metadata["poster_specs"])

        catalog = client.get("/api/platforms/catalog").json()
        assert any(pack["id"] == "wechat-light-zine" for pack in catalog["skill_packs"])
        assert "light_series" in catalog["platform_capabilities"]["wechat"]["formats"]

        health = client.get("/health").json()
        assert health["signal_to_studio"] is True
        assert health["wechat_light_series"] is True

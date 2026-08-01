from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageStat


def _luminance(path: str) -> float:
    with Image.open(path).convert("L") as image:
        return float(ImageStat.Stat(image.resize((60, 100))).mean[0])


def test_light_content_lab_candidates_corpus_iteration_and_distinct_visuals(
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

    with TestClient(main_module.app) as client:
        with db_session.SessionLocal() as db:
            source = SourceItem(
                provider="test",
                platform="x",
                external_id="light-lab-v12",
                canonical_url="https://x.com/example/status/120",
                author_handle="example",
                author_name="Example",
                text_original=(
                    "很多人不是不努力，而是在工作、照顾家庭和回应别人之后，"
                    "已经没有力气处理自己的情绪。真正需要的不是另一条命令，"
                    "而是把今天过稳、把边界说清。"
                ),
                content_kind="post",
                structured_content_json="{}",
                metrics_json="{}",
            )
            technical = SourceItem(
                provider="test",
                platform="x",
                external_id="technical-light-lab-v12",
                canonical_url="https://x.com/example/status/121",
                author_handle="engineer",
                author_name="Engineer",
                text_original=(
                    "Claude Fable 5 connects to Blender through MCP. The GPU renderer uses CUDA kernels, "
                    "Python plugins and a new inference model to inspect frames and revise the 3D scene."
                ),
                content_kind="article",
                structured_content_json="{}",
                metrics_json="{}",
            )
            db.add_all([source, technical])
            db.commit()
            source_id = source.id
            technical_id = technical.id

        rejected = client.post(
            "/api/platforms/wechat/light/variants",
            json={
                "source_id": technical_id,
                "recipe": "mature_life",
                "image_count": 4,
                "audience": "50岁以上读者",
                "visual_style": "minimal_zine",
            },
        )
        assert rejected.status_code == 409, rejected.text
        assert "技术/工具内容" in rejected.json()["detail"]
        assert "泛鸡汤" in rejected.json()["detail"]

        technical_commentary = client.post(
            "/api/platforms/wechat/light/variants",
            json={
                "source_id": technical_id,
                "recipe": "short_commentary",
                "image_count": 3,
                "visual_style": "old_newspaper",
                "quality_mode": "fast",
            },
        )
        assert technical_commentary.status_code == 201, technical_commentary.text
        technical_meta = json.loads(technical_commentary.json()["metadata_json"])
        assert technical_meta["source_fit"]["source_kind"] == "technical"
        assert technical_meta["source_fit"]["allowed"] is True

        dark_created = client.post(
            "/api/platforms/wechat/light/variants",
            json={
                "source_id": source_id,
                "recipe": "comfort",
                "image_count": 4,
                "audience": "长期工作并照顾家庭的城市读者",
                "tone": "自然、具体、克制",
                "visual_style": "dark_contemplative",
                "quality_mode": "studio",
                "feedback": "不要泛泛鼓励，要写出力气被工作和家庭同时消耗的处境",
            },
        )
        assert dark_created.status_code == 201, dark_created.text
        dark = dark_created.json()
        dark_meta = json.loads(dark["metadata_json"])
        assert dark_meta["pipeline_version"] == "light-lab-v12"
        assert dark_meta["visual_style"] == "dark_contemplative"
        assert dark_meta["source_fit"]["score"] > 0.8
        assert len(dark_meta["candidates"]) == 3
        assert dark_meta["reviews"]["audience"]
        assert dark_meta["reviews"]["culture"]
        assert dark_meta["quality_score"] > 0
        assert dark_meta["human_approved"] is False

        dark_rendered = client.post(
            f"/api/platforms/variants/{dark['id']}/render",
            json={"package": True},
        )
        assert dark_rendered.status_code == 200, dark_rendered.text
        dark_files = dark_rendered.json()["files"]
        assert Path(dark_files["poster_01"]).is_file()
        dark_luma = _luminance(dark_files["poster_01"])

        ink_created = client.post(
            "/api/platforms/wechat/light/variants",
            json={
                "source_id": source_id,
                "recipe": "comfort",
                "image_count": 4,
                "audience": "长期工作并照顾家庭的城市读者",
                "visual_style": "classical_ink",
                "quality_mode": "fast",
            },
        )
        assert ink_created.status_code == 201, ink_created.text
        ink = ink_created.json()
        ink_rendered = client.post(
            f"/api/platforms/variants/{ink['id']}/render",
            json={"package": True},
        )
        assert ink_rendered.status_code == 200, ink_rendered.text
        ink_files = ink_rendered.json()["files"]
        ink_luma = _luminance(ink_files["poster_01"])
        assert abs(dark_luma - ink_luma) > 45
        assert Path(dark_files["poster_01"]).read_bytes() != Path(ink_files["poster_01"]).read_bytes()

        selected = client.post(
            f"/api/platforms/wechat/light/variants/{dark['id']}/select-candidate",
            json={"candidate_index": 1},
        )
        assert selected.status_code == 201, selected.text
        selected_payload = selected.json()
        selected_meta = json.loads(selected_payload["metadata_json"])
        assert selected_meta["selected_candidate_index"] == 1
        assert selected_payload["version"] > dark["version"]

        edited = client.put(
            f"/api/platforms/variants/{selected_payload['id']}",
            json={
                "title": "晚饭后，先把自己的十分钟还回来",
                "subtitle": "不是解决所有问题，只是停止继续透支",
                "summary": "工作和家庭都需要回应时，人很容易把自己排到最后。",
                "body_markdown": (
                    "晚饭收拾完，屋里终于安静下来。先不要打开下一条消息。\n\n"
                    "给自己十分钟，不解决问题，只确认今天已经够累。\n\n"
                    "边界不是拒绝所有人，而是不再把自己永远放到最后。"
                ),
                "tags": "生活,边界",
                "theme": "zen",
            },
        )
        assert edited.status_code == 200, edited.text
        edited_payload = edited.json()
        edited_meta = json.loads(edited_payload["metadata_json"])
        assert edited_meta["human_edited"] is True
        assert edited_meta["human_approved"] is False
        assert edited_meta["poster_specs"][0]["phrase"] == "晚饭后，先把自己的十分钟还回来"
        assert "晚饭收拾完" in edited_meta["poster_specs"][1]["phrase"]
        assert edited_payload["output_paths_json"] == "{}"

        edited_rendered = client.post(
            f"/api/platforms/variants/{edited_payload['id']}/render",
            json={"package": False},
        )
        assert edited_rendered.status_code == 200, edited_rendered.text
        edited_fresh = client.get(f"/api/platforms/variants/{edited_payload['id']}").json()
        edited_fresh_meta = json.loads(edited_fresh["metadata_json"])
        assert "晚饭后" in edited_fresh_meta["poster_specs"][0]["final_prompt"]

        iterated = client.post(
            f"/api/platforms/wechat/light/variants/{selected_payload['id']}/iterate",
            json={
                "feedback": "开头仍然太像总结，请从晚饭后终于安静下来的具体场景写起。",
                "quality_mode": "studio",
            },
        )
        assert iterated.status_code == 201, iterated.text
        iterated_payload = iterated.json()
        iterated_meta = json.loads(iterated_payload["metadata_json"])
        assert iterated_meta["iteration_round"] == 2
        assert "晚饭后" in iterated_meta["feedback"]
        assert len(iterated_meta["candidates"]) == 3

        approved = client.post(
            f"/api/platforms/wechat/light/variants/{iterated_payload['id']}/approve",
            json={"note": "这版生活场景具体，语气自然，可作为正向样本。"},
        )
        assert approved.status_code == 200, approved.text
        corpus = client.get("/api/platforms/wechat/light/corpus?recipe=comfort").json()
        assert any(item["variant_id"] == iterated_payload["id"] for item in corpus)

        manual = client.post(
            "/api/platforms/wechat/light/corpus",
            json={
                "recipe": "comfort",
                "title": "先把今天过稳",
                "body_markdown": "晚饭后的十分钟，不解决问题，只把呼吸放慢一点。",
                "visual_style": "photo_editorial",
                "note": "用户原创授权样本，学习具体场景和克制节奏。",
            },
        )
        assert manual.status_code == 201, manual.text
        assert len(client.get("/api/platforms/wechat/light/corpus?recipe=comfort").json()) == 2

        catalog = client.get("/api/platforms/catalog").json()
        styles = catalog["platform_capabilities"]["wechat"]["light_visual_styles"]
        assert {item["id"] for item in styles} >= {
            "photo_editorial",
            "classical_ink",
            "dark_contemplative",
            "seasonal_folk",
            "old_newspaper",
        }

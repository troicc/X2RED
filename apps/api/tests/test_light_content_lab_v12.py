from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageStat

from app.services.light_content import poster_copy_issues
from app.services.light_content_lab import LightContentLabService


def test_poster_copy_quality_gate_detects_shifted_carousel_chain() -> None:
    broken = [
        {"phrase": "没干重活，为什么下班后累得不想说话", "note": "一天下来大多是坐着看文件"},
        {"phrase": "一天下来大多是坐着看文件", "note": "没搬砖没流汗"},
        {"phrase": "没搬砖没流汗", "note": "真正消耗的是持续防备"},
        {"phrase": "真正消耗的是持续防备", "note": "先给神经十分钟落地"},
    ]
    assert "page_1_note_repeats_page_2_phrase" in poster_copy_issues(broken)
    assert "page_2_note_repeats_page_3_phrase" in poster_copy_issues(broken)

    distinct = [
        {"phrase": "准点下班，为什么还像逃了一天命", "note": "真正消耗的是持续防备"},
        {"phrase": "领导一个皱眉，大脑能琢磨半天", "note": "不确定的小信号，会把神经一直吊着"},
        {"phrase": "回家那句关心，为什么会点着你", "note": "最亲的人常替职场压力承受余波"},
        {"phrase": "下班不是换个地方继续值班", "note": "先留十分钟独处，再把情绪带进家门"},
    ]
    assert poster_copy_issues(distinct) == []


def test_corpus_batch_evidence_scope_records_full_pool_and_frozen_sources() -> None:
    source = SimpleNamespace(
        id="src_batch",
        external_id="batch_01",
        content_kind="corpus_batch",
        structured_content_json=json.dumps(
            {
                "document_type": "corpus_batch",
                "pool_id": "pool_01",
                "batch_id": "batch_01",
                "batch_source_ids": ["src_1", "src_2", "src_3", "src_4"],
            }
        ),
    )
    text = "【全池语义记忆】\n来源数：18\n语料字符：40280\n【本批详细来源】"
    scope = LightContentLabService._source_evidence_scope(source, text)
    assert scope["input_type"] == "corpus_batch"
    assert scope["pool_source_count"] == 18
    assert scope["pool_corpus_chars"] == 40280
    assert scope["detailed_source_count"] == 4
    assert scope["full_pool_memory_included"] is True


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
        assert dark_meta["pipeline_version"] == "light-lab-v14"
        assert dark_meta["visual_brief_mode"] == "production"
        assert dark_meta["visual_distinctness"]["passed"] is True
        assert len(dark_meta["visual_distinctness"]["layout_families"]) >= 3
        assert all(
            len(page["candidates"]) == 3
            for page in dark_meta["visual_brief"]["pages"]
        )
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
        selected_specs = selected_meta["poster_specs"]
        selected_first_phrase = selected_specs[0]["phrase"]
        assert selected_meta["selected_candidate_index"] == 1
        assert selected_meta["pipeline_version"] == "light-lab-v14"
        assert all(
            spec["page_visual_brief"]["evidence_refs"] != ["当前来源"]
            for spec in selected_specs
        )
        assert selected_payload["version"] > dark["version"]

        invalid_storyboard = []
        for index, spec in enumerate(selected_specs, start=1):
            invalid_storyboard.append(
                {
                    "page": index,
                    "page_visual_brief": spec.get("page_visual_brief"),
                    "phrase": spec["phrase"],
                    "note": spec.get("note", ""),
                    "visual_metaphor": spec.get("visual_metaphor") or "一件日常物件",
                    "layout": spec.get("layout") or "center-fragment",
                    "anchor": spec.get("anchor") or "object-specimen",
                    "accent": spec.get("accent") or "#1646d8",
                    "texture": spec.get("texture") or "xerox-softness",
                    "mood": spec.get("mood") or "quiet",
                    "focus_x": spec.get("focus_x", 0.5),
                    "focus_y": spec.get("focus_y", 0.42),
                    "zoom": spec.get("zoom", 1),
                }
            )
        invalid_storyboard[0]["note"] = invalid_storyboard[1]["phrase"]
        rejected_storyboard = client.post(
            f"/api/platforms/wechat/light/variants/{selected_payload['id']}/storyboard",
            json={"pages": invalid_storyboard},
        )
        assert rejected_storyboard.status_code == 400, rejected_storyboard.text
        assert "跨页重复" in rejected_storyboard.json()["detail"]

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
        assert edited_meta["poster_specs"] == selected_specs
        assert edited_meta["storyboard_copy_sync"]["mode"] == "preserved-after-article-edit"
        assert edited_meta["storyboard_copy_sync"]["copy_changed"] is False
        assert edited_meta["storyboard_copy_sync"]["quality_issues"] == []
        assert edited_payload["output_paths_json"] == "{}"

        edited_rendered = client.post(
            f"/api/platforms/variants/{edited_payload['id']}/render",
            json={"package": False},
        )
        assert edited_rendered.status_code == 200, edited_rendered.text
        edited_fresh = client.get(f"/api/platforms/variants/{edited_payload['id']}").json()
        edited_fresh_meta = json.loads(edited_fresh["metadata_json"])
        assert selected_first_phrase in edited_fresh_meta["poster_specs"][0]["final_prompt"]

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

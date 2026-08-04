from __future__ import annotations

import hashlib
import importlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.domain.models import SourceItem
from app.domain.platforms import PlatformVariant, PlatformVariantState
from app.services.light_visual_renderer import CJKFontError, LightVisualRenderer
from app.services.minimal_zine_native import (
    MinimalZineNativeService,
    _model_input_fingerprint,
    storyboard_model_input_changed,
)
from app.services.native_skill_manager import NativeSkillError


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'minimal-zine.db'}",
        media_dir=tmp_path / "assets",
        raw_dir=tmp_path / "raw",
        export_dir=tmp_path / "exports",
        browser_profile_dir=tmp_path / "profile",
        native_skill_dir=tmp_path / "native-skills",
        scheduler_enabled=False,
    )


def image_bytes(*, accent: str = "#c91f2c") -> bytes:
    image = Image.new("RGB", (1024, 1536), "#e6dcc8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((310, 320, 650, 640), fill="#55514d")
    draw.ellipse((550, 470, 690, 610), fill=accent)
    data = io.BytesIO()
    image.save(data, "PNG")
    return data.getvalue()


def muted_accent_image_bytes() -> bytes:
    """A deliberately faded blue source accent, not a saturated red proxy."""

    image = Image.new("RGB", (1024, 1536), "#d8d8d8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((466, 500, 536, 596), fill="#8297ac")
    data = io.BytesIO()
    image.save(data, "PNG")
    return data.getvalue()


def monochrome_image_bytes() -> bytes:
    image = Image.new("RGB", (1024, 1536), "#d8d8d8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((310, 320, 650, 640), fill="#555555")
    data = io.BytesIO()
    image.save(data, "PNG")
    return data.getvalue()


def session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'minimal-zine.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def allow_portable_render_font(
    service: MinimalZineNativeService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pass the font preflight in tests whose subject is not font discovery.

    GitHub's stock Ubuntu image has no CJK font.  The dedicated resolver test below
    still verifies both the real success and failure paths; artifact lifecycle tests
    inject this boundary so they exercise their own contract on every CI platform.
    """

    diagnostics = {
        "available": True,
        "selected": {
            "path": "test-injected-cjk-font",
            "face_index": 0,
            "coverage_verified": True,
        },
        "serif_selected": {
            "path": "test-injected-cjk-font",
            "face_index": 0,
            "coverage_verified": True,
        },
        "coverage_probe": list("中文测试页，。"),
        "card_font_path": "",
        "attempts": [],
    }
    monkeypatch.setattr(service.local_renderer, "require_cjk_font", lambda: diagnostics)


def storyboard_specs() -> list[dict]:
    return [
        {
            "page": page,
            "phrase": f"第 {page} 页的本地中文",
            "note": "只由本地合成器排版。",
            "visual_metaphor": f"第 {page} 个孤立物件",
            "layout": layout,
            "anchor": "object-specimen",
            "accent": "vermilion",
            "texture": "xerox-softness",
            "mood": "quiet",
            "focus_x": 0.5,
            "focus_y": 0.5,
            "zoom": 1.0,
        }
        for page, layout in enumerate(
            ("center-fragment", "upper-right-block", "single-specimen"), start=1
        )
    ]


def stored_variant(
    db: Session,
    service: MinimalZineNativeService,
    *,
    variant_id: str = "variant_v15",
    source_id: str = "source_v15",
) -> PlatformVariant:
    if db.get(SourceItem, source_id) is None:
        db.add(
            SourceItem(
                id=source_id,
                provider="test",
                platform="x",
                external_id=source_id,
                canonical_url=f"https://x.com/example/{source_id}",
                author_handle="minimal_zine_test",
                author_name="Minimal Zine Test",
                content_kind="post",
                text_original="Minimal Zine v15 fixture source",
                structured_content_json="{}",
                metrics_json="{}",
            )
        )
        db.flush()
    variant = PlatformVariant(
        id=variant_id,
        source_id=source_id,
        platform="wechat",
        format="light_series",
        version=1,
        title="Minimal Zine v15 测试",
        subtitle="",
        summary="测试原始视觉锚点和最终海报分离。",
        body_markdown="测试正文",
        tags="测试",
        theme="zen",
    )
    db.add(variant)
    db.flush()
    output_dir = service.settings.export_dir / "wechat" / variant.id
    output_dir.mkdir(parents=True)
    specs = storyboard_specs()
    outputs: dict[str, str] = {}
    for page, spec in enumerate(specs, start=1):
        raw = output_dir / f"anchor-{page:02d}.png"
        poster = output_dir / f"poster-{page:02d}.png"
        raw.write_bytes(image_bytes())
        recipe = service._recipe_for(spec)
        diagnostics = service._compose_poster(
            raw.read_bytes(),
            poster,
            spec=spec,
            recipe=recipe,
            page=page,
            total=len(specs),
        )
        fingerprint = _model_input_fingerprint(spec)
        spec.update(
            {
                "final_prompt": f"persisted prompt {page}",
                "native_zine_recipe": recipe,
                "native_zine_interpretation": f"第 {page} 页的视觉隐喻",
                "model_input_fingerprint": fingerprint,
                "raw_anchor_fingerprint": fingerprint,
                "raw_anchor_source_variant_id": variant.id,
                "final_composition_fingerprint": service._composition_fingerprint(
                    spec, recipe
                ),
                "compositor_version": service.compositor_version,
                "composition_diagnostics": diagnostics,
            }
        )
        outputs[f"anchor_{page:02d}"] = str(raw.resolve())
        outputs[f"poster_{page:02d}"] = str(poster.resolve())
    metadata = {
        "poster_specs": specs,
        "render_engine": "gc-minimal-zine-local-compositor-v4",
        "native_zine": {"compositor_version": service.compositor_version},
    }
    outputs = service._rebuild_artifacts(
        variant=variant,
        metadata=metadata,
        specs=specs,
        output_dir=output_dir,
        output_paths=outputs,
    )
    variant.metadata_json = json.dumps(metadata, ensure_ascii=False)
    variant.output_paths_json = json.dumps(outputs, ensure_ascii=False)
    variant.status = PlatformVariantState.packaged.value
    db.flush()
    return variant


def test_recompose_selected_page_preserves_complete_set_and_excludes_raw_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = session(tmp_path)
    service = MinimalZineNativeService(settings(tmp_path))
    variant = stored_variant(db, service)
    allow_portable_render_font(service, monkeypatch)
    model_calls = {"compile": 0, "image": 0}

    def no_compile(**_: object) -> dict:
        model_calls["compile"] += 1
        raise AssertionError("recompose must not compile a prompt")

    def no_image(_: str) -> bytes:
        model_calls["image"] += 1
        raise AssertionError("recompose must not call the image model")

    monkeypatch.setattr(service, "_compile_prompt", no_compile)
    monkeypatch.setattr(service, "_generate_image", no_image)
    rendered, pages = service.render_variant(db, variant, mode="recompose", pages=[2])

    assert model_calls == {"compile": 0, "image": 0}
    assert [item["page"] for item in pages] == [2]
    assert pages[0]["action"] == "recomposed"
    assert pages[0]["anchor_key"] == "anchor_02"
    assert pages[0]["poster_key"] == "poster_02"
    outputs = json.loads(rendered.output_paths_json)
    assert {"anchor_01", "anchor_02", "anchor_03", "poster_01", "poster_02", "poster_03"} <= set(outputs)
    assert Path(outputs["anchor_02"]).read_bytes() != Path(outputs["poster_02"]).read_bytes()
    with zipfile.ZipFile(outputs["package"]) as archive:
        names = set(archive.namelist())
    assert {"poster-01.png", "poster-02.png", "poster-03.png", "article.md", "manifest.json", "preview.html"} == names
    assert not any(name.startswith("anchor-") for name in names)
    manifest = json.loads(Path(outputs["manifest"]).read_text(encoding="utf-8"))
    assert manifest["raw_anchors"] == ["anchor-01.png", "anchor-02.png", "anchor-03.png"]
    assert manifest["pages"][1]["anchor_key"] == "anchor_02"


def test_recompose_rejects_missing_anchor_and_never_uses_final_as_raw(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = session(tmp_path)
    service = MinimalZineNativeService(settings(tmp_path))
    variant = stored_variant(db, service)
    allow_portable_render_font(service, monkeypatch)
    outputs = json.loads(variant.output_paths_json)
    Path(outputs["anchor_02"]).unlink()
    outputs.pop("anchor_02")
    variant.output_paths_json = json.dumps(outputs)
    db.flush()
    monkeypatch.setattr(service, "_generate_image", lambda _: (_ for _ in ()).throw(AssertionError("no model")))
    monkeypatch.setattr(service, "_compile_prompt", lambda **_: (_ for _ in ()).throw(AssertionError("no compiler")))

    with pytest.raises(NativeSkillError, match="raw anchor"):
        service.render_variant(db, variant, mode="recompose", pages=[2])


def test_staging_failure_rolls_back_existing_package_and_db_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = session(tmp_path)
    service = MinimalZineNativeService(settings(tmp_path))
    variant = stored_variant(db, service)
    allow_portable_render_font(service, monkeypatch)
    original_outputs = variant.output_paths_json
    package_path = Path(json.loads(original_outputs)["package"])
    original_hash = hashlib.sha256(package_path.read_bytes()).hexdigest()
    original_rebuild = service._rebuild_artifacts

    def fail_after_staging(**kwargs: object) -> dict[str, str]:
        original_rebuild(**kwargs)  # type: ignore[arg-type]
        raise NativeSkillError("forced late staging failure")

    monkeypatch.setattr(service, "_rebuild_artifacts", fail_after_staging)
    with pytest.raises(NativeSkillError, match="forced late"):
        service.render_variant(db, variant, mode="recompose", pages=[1])

    assert variant.output_paths_json == original_outputs
    assert hashlib.sha256(package_path.read_bytes()).hexdigest() == original_hash
    assert not list((service.settings.export_dir / "wechat").glob(".variant_v15.staging-*"))


def test_cjk_resolver_reports_actual_coverage_and_honors_configured_font(
    tmp_path: Path,
) -> None:
    default_renderer = LightVisualRenderer(settings(tmp_path))
    diagnostics = default_renderer.cjk_font_diagnostics()
    if diagnostics["available"]:
        assert diagnostics["selected"]["coverage_verified"] is True
        selected_path = Path(diagnostics["selected"]["path"])
        configured = Settings(card_font_path=selected_path)
        configured_renderer = LightVisualRenderer(configured)
        configured_diagnostics = configured_renderer.require_cjk_font()
        assert Path(configured_diagnostics["selected"]["path"]) == selected_path
    else:
        with pytest.raises(CJKFontError, match="中文字符覆盖"):
            default_renderer.require_cjk_font()


def test_custom_storyboard_mood_remains_part_of_the_frozen_model_input() -> None:
    previous = storyboard_specs()[0]
    revised = {**previous, "mood": "雨后安静但仍有一点温暖"}

    assert storyboard_model_input_changed(previous, revised) is True
    assert _model_input_fingerprint(previous) != _model_input_fingerprint(revised)


def test_compositor_preserves_muted_upstream_accent_and_bounds_local_fallback(
    tmp_path: Path,
) -> None:
    service = MinimalZineNativeService(settings(tmp_path))
    spec = storyboard_specs()[0]
    recipe = service._recipe_for(spec)

    faded_diagnostics = service._compose_poster(
        muted_accent_image_bytes(),
        tmp_path / "faded-upstream-accent.png",
        spec=spec,
        recipe=recipe,
        page=1,
        total=3,
    )
    assert faded_diagnostics["high_chroma_ratio"] < service.high_chroma_threshold
    assert faded_diagnostics["muted_chroma_ratio"] >= service.muted_chroma_threshold
    assert faded_diagnostics["local_accent_added"] is False
    assert faded_diagnostics["local_accent_reason"] == "upstream-muted-accent"
    assert faded_diagnostics["local_accent_actual_share"] == 0.0

    fallback_diagnostics = service._compose_poster(
        monochrome_image_bytes(),
        tmp_path / "color-starved-fallback.png",
        spec=spec,
        recipe=recipe,
        page=1,
        total=3,
    )
    assert fallback_diagnostics["local_accent_added"] is True
    assert fallback_diagnostics["local_accent_reason"] == "color-starved"
    assert fallback_diagnostics["local_accent_actual_share"] <= service.local_accent_max_share
    assert fallback_diagnostics["local_accent_actual_share"] <= fallback_diagnostics[
        "local_accent_target_share"
    ]
    assert fallback_diagnostics["local_accent_shape"] == "registration-stamp"
    assert fallback_diagnostics["local_accent_outside_text_safe_zone"] is True
    assert fallback_diagnostics["local_accent_outside_principal_cluster"] is True
    bbox = fallback_diagnostics["local_accent_bbox"]
    assert bbox["width"] <= 96
    assert bbox["height"] <= 48

    # The solid-block recipe produces the widest possible local mark.  Every
    # layout's slot must still stay outside its own art and typography fields.
    for layout in (
        "center-fragment",
        "lower-left-float",
        "upper-right-block",
        "dual-panel",
        "irregular-cutout",
        "type-led",
        "dot-orbit",
        "single-specimen",
    ):
        canvas = Image.new("RGB", (service.local_renderer.width, service.local_renderer.height))
        slot_diagnostics = service._draw_local_accent(
            ImageDraw.Draw(canvas),
            layout=layout,
            anchor="solid-color-block",
            color="#c91f2c",
            share=service.local_accent_target_share,
            safe_zone=service._safe_zone(layout),
        )
        assert slot_diagnostics["actual_share"] <= service.local_accent_max_share
        assert slot_diagnostics["outside_text_safe_zone"] is True
        assert slot_diagnostics["outside_principal_cluster"] is True


def test_storyboard_revision_is_immutable_and_render_request_validates_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("X2RED_DATABASE_URL", f"sqlite:///{tmp_path / 'api.db'}")
    monkeypatch.setenv("X2RED_MEDIA_DIR", str(tmp_path / "assets"))
    monkeypatch.setenv("X2RED_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("X2RED_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("X2RED_BROWSER_PROFILE_DIR", str(tmp_path / "profile"))
    monkeypatch.setenv("X2RED_SCHEDULER_ENABLED", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()
    import app.db.session as db_session
    import app.main as main_module

    importlib.reload(db_session)
    importlib.reload(main_module)
    with TestClient(main_module.app) as client:
        with db_session.SessionLocal() as db:
            source = SourceItem(
                id="source_storyboard_v15",
                provider="test",
                platform="x",
                external_id="storyboard-v15",
                canonical_url="https://x.com/example/storyboard-v15",
                author_handle="example",
                author_name="Example",
                content_kind="post",
                text_original="故事板测试来源",
                structured_content_json="{}",
                metrics_json="{}",
            )
            specs = storyboard_specs()
            for spec in specs:
                fingerprint = _model_input_fingerprint(spec)
                spec.update(
                    {
                        "final_prompt": "persisted frozen prompt",
                        "native_zine_recipe": {
                            "layout": spec["layout"],
                            "anchor": spec["anchor"],
                            "typography": "local-cjk",
                            "accent": spec["accent"],
                            "texture": spec["texture"],
                            "mood": spec["mood"],
                        },
                        "raw_anchor_fingerprint": fingerprint,
                    }
                )
            current = PlatformVariant(
                id="variant_storyboard_v15",
                source_id=source.id,
                platform="wechat",
                format="light_series",
                version=1,
                title="冻结故事板",
                subtitle="",
                summary="",
                body_markdown="正文",
                tags="测试",
                theme="zen",
                metadata_json=json.dumps({"poster_specs": specs}, ensure_ascii=False),
                output_paths_json="{}",
            )
            db.add_all([source, current])
            db.commit()

        body_pages = storyboard_specs()
        body_pages[0]["phrase"] = "只改本地中文，不重生原始锚点"
        response = client.post(
            "/api/platforms/wechat/light/variants/variant_storyboard_v15/storyboard",
            json={"pages": body_pages},
        )
        assert response.status_code == 201, response.text
        child = response.json()
        child_meta = json.loads(child["metadata_json"])
        assert child["id"] != "variant_storyboard_v15"
        assert child_meta["parent_variant_id"] == "variant_storyboard_v15"
        assert child["output_paths_json"] == "{}"
        assert child_meta["poster_specs"][0]["final_prompt"] == "persisted frozen prompt"

        original = client.get("/api/platforms/variants/variant_storyboard_v15").json()
        assert json.loads(original["metadata_json"])["poster_specs"][0]["phrase"] == "第 1 页的本地中文"

        bad_mode = client.post(
            "/api/native-skills/minimal-zine/variants/missing/render",
            json={"mode": "recompose", "regenerate": True},
        )
        assert bad_mode.status_code == 422
        duplicate_pages = client.post(
            "/api/native-skills/minimal-zine/variants/missing/render",
            json={"mode": "recompose", "pages": [1, 1]},
        )
        assert duplicate_pages.status_code == 422

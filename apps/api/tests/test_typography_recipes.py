from __future__ import annotations

import itertools
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat
from pydantic import ValidationError

from app.core.config import Settings
from app.domain.typography_schemas import TextRegion, TypographyRecipe
from app.services.light_visual_renderer import CJKFontError, LightVisualRenderer
from app.services.typography_recipes import (
    ALL_TYPOGRAPHY_MODES,
    TEMPLATES,
    TypographyRecipeEngine,
)
from app.services.wechat_cover_renderer import WeChatCoverRenderer

PHRASE = "字体不是装饰，它参与构图"
NOTE = "中文由本地排版器准确合成，并为关键主体保留空间。"


def portable_font(
    size: int,
    *,
    bold: bool,
    serif: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/Songti.ttc" if serif else "",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc" if serif else "",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def rendered_text(diagnostic: object, *roles: str) -> str:
    regions = diagnostic.regions
    return "".join(
        line
        for region in regions
        if region.role in roles
        for line in region.lines
    )


def test_recipe_schema_is_strict_and_all_required_modes_are_registered() -> None:
    assert set(TEMPLATES) == set(ALL_TYPOGRAPHY_MODES)
    assert len(TEMPLATES) == 8
    for mode, recipe in TEMPLATES.items():
        assert isinstance(recipe, TypographyRecipe)
        assert recipe.mode == mode
        assert recipe.text_regions
        assert recipe.font_role
        assert 300 <= recipe.weight <= 900
        assert recipe.collision_policy

    with pytest.raises(ValidationError, match="完整位于"):
        TextRegion(
            region_id="overflow",
            role="title",
            source="phrase",
            x=0.9,
            y=0.1,
            width=0.2,
            height=0.2,
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        TypographyRecipe.model_validate(
            {
                **TEMPLATES["type_led_large"].model_dump(mode="json"),
                "unknown_layout_switch": True,
            }
        )


@pytest.mark.parametrize(
    ("size", "ratio"),
    [
        ((900, 1500), "3:5"),
        ((900, 1200), "3:4"),
        ((2100, 900), "21:9"),
        ((1080, 1080), "1:1"),
    ],
)
def test_local_chinese_has_no_overflow_at_required_ratios(
    size: tuple[int, int],
    ratio: str,
) -> None:
    engine = TypographyRecipeEngine()
    selection = engine.select(
        size=size,
        phrase=PHRASE,
        note=NOTE,
        page=1,
        total=4,
        layout="type-led",
        visual_role="cover",
        requested_mode="type_led_large",
    )
    canvas = Image.new("RGB", size, "#ece3d3")
    rendered, diagnostic = engine.render(
        canvas,
        selection=selection,
        phrase=PHRASE,
        note=NOTE,
        folio="01 / 04",
        label="LOCAL CJK",
        font_resolver=portable_font,
    )

    assert rendered.size == size
    assert diagnostic.canvas_ratio == ratio
    assert diagnostic.no_overflow is True
    assert diagnostic.subject_clear is True
    assert diagnostic.visible_text_region_count >= 2
    assert rendered_text(diagnostic, "title") == PHRASE
    assert rendered_text(diagnostic, "caption") == NOTE
    assert all(not region.clipped for region in diagnostic.regions)


def test_subject_collision_is_resolved_by_layout_transform() -> None:
    size = (900, 1500)
    protected = ((630, 420, 720, 510),)
    engine = TypographyRecipeEngine()
    selection = engine.select(
        size=size,
        phrase=PHRASE,
        note=NOTE,
        page=1,
        total=4,
        layout="type-led",
        visual_role="",
        requested_mode="type_led_large",
        protected_regions=protected,
    )
    canvas = Image.new("RGB", size, "#ece3d3")
    ImageDraw.Draw(canvas).rounded_rectangle(protected[0], radius=20, fill="#766c61")
    _, diagnostic = engine.render(
        canvas,
        selection=selection,
        phrase=PHRASE,
        note=NOTE,
        folio="01 / 04",
        label="LOCAL CJK",
        font_resolver=portable_font,
    )

    assert selection.recipe.mode == "type_led_large"
    assert selection.recipe.transform == "mirror_y"
    assert diagnostic.subject_clear is True
    assert all(
        not region.overlaps_subject
        for region in diagnostic.regions
        if region.role not in {"folio", "microtype"}
    )


def test_page_layouts_choose_multiple_modes_without_defaulting_to_safe_caption() -> None:
    engine = TypographyRecipeEngine()
    layouts = (
        "type-led",
        "diagonal-notes",
        "edge-counterweight",
        "single-specimen",
        "dot-orbit",
        "dual-panel",
        "irregular-cutout",
    )
    modes = {
        engine.select(
            size=(900, 1500),
            phrase=f"第 {page} 页让字体进入构图",
            note=NOTE,
            page=page,
            total=len(layouts),
            layout=layout,
        ).recipe.mode
        for page, layout in enumerate(layouts, start=1)
    }

    assert len(modes) >= 6
    assert "safe_zone_caption" not in modes


@pytest.mark.parametrize(
    "layout",
    (
        "type-led",
        "diagonal-notes",
        "edge-counterweight",
        "single-specimen",
        "dot-orbit",
        "dual-panel",
        "irregular-cutout",
    ),
)
def test_safe_caption_is_the_last_automatic_candidate(layout: str) -> None:
    modes = TypographyRecipeEngine()._candidate_modes(
        requested_mode="",
        layout=layout,
        visual_role="scene",
        page=1,
        phrase=PHRASE,
    )

    assert modes[-1] == "safe_zone_caption"
    assert modes.count("safe_zone_caption") == 1


def test_four_modes_remain_visibly_distinct_as_thumbnails() -> None:
    engine = TypographyRecipeEngine()
    size = (600, 1000)
    modes = (
        "type_led_large",
        "diagonal_fragments",
        "archive_microtype",
        "type_in_color_block",
    )
    thumbnails: dict[str, Image.Image] = {}
    for mode in modes:
        selection = engine.select(
            size=size,
            phrase=PHRASE,
            note=NOTE,
            page=1,
            total=4,
            layout="test",
            requested_mode=mode,
        )
        rendered, diagnostic = engine.render(
            Image.new("RGB", size, "#ece3d3"),
            selection=selection,
            phrase=PHRASE,
            note=NOTE,
            folio="01 / 04",
            label="ARCHIVE · LOCAL CJK",
            font_resolver=portable_font,
        )
        assert diagnostic.mode == mode
        thumbnails[mode] = rendered.resize((90, 150), Image.Resampling.LANCZOS).convert("L")

    for left, right in itertools.combinations(modes, 2):
        difference = ImageChops.difference(thumbnails[left], thumbnails[right])
        assert ImageStat.Stat(difference).mean[0] >= 2.0, f"{left} 与 {right} 缩略图过于相似"


@pytest.mark.parametrize("mode", ALL_TYPOGRAPHY_MODES)
def test_every_mode_renders_at_native_minimal_zine_dimensions(mode: str) -> None:
    engine = TypographyRecipeEngine()
    size = (1200, 2000)
    selection = engine.select(
        size=size,
        phrase=PHRASE,
        note=NOTE,
        page=3,
        total=8,
        layout="native-poster",
        requested_mode=mode,
    )
    _, diagnostic = engine.render(
        Image.new("RGB", size, "#ece3d3"),
        selection=selection,
        phrase=PHRASE,
        note=NOTE,
        folio="03 / 08",
        label="PAGE 03 · LOCAL CJK",
        font_resolver=portable_font,
    )

    assert diagnostic.mode == mode
    assert diagnostic.no_overflow is True
    assert diagnostic.subject_clear is True


def test_frozen_recipe_is_reused_only_for_the_same_source_fingerprint() -> None:
    engine = TypographyRecipeEngine()
    inputs = {
        "size": (900, 1500),
        "phrase": PHRASE,
        "note": NOTE,
        "page": 2,
        "total": 4,
        "layout": "diagonal-notes",
        "visual_role": "process",
        "requested_mode": "",
        "protected_regions": ((360, 580, 540, 800),),
    }
    original = engine.select(**inputs)
    reused = engine.select(
        **inputs,
        stored_recipe=original.recipe.model_dump(mode="json"),
    )
    changed = engine.select(
        **{**inputs, "phrase": f"{PHRASE}。"},
        stored_recipe=original.recipe.model_dump(mode="json"),
    )

    assert reused.recipe == original.recipe
    assert changed.recipe.source_fingerprint != original.recipe.source_fingerprint


def test_cjk_preflight_never_silently_accepts_an_unverified_font(tmp_path: Path) -> None:
    renderer = LightVisualRenderer(Settings(export_dir=tmp_path / "exports"))
    diagnostics = renderer.cjk_font_diagnostics()
    if diagnostics["available"]:
        verified = renderer.require_cjk_font()
        assert verified["selected"]["coverage_verified"] is True
        assert verified["serif_selected"]["coverage_verified"] is True
    else:
        with pytest.raises(CJKFontError, match="中文字符覆盖"):
            renderer.require_cjk_font()


@pytest.mark.parametrize(
    "style",
    ["editorial_split", "data_poster", "tech_blueprint", "image_cinema"],
)
def test_wechat_cover_uses_recipe_on_wide_and_square_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    style: str,
) -> None:
    renderer = WeChatCoverRenderer(
        Settings(
            export_dir=tmp_path / "exports",
            typography_recipe_mode="production",
        )
    )
    monkeypatch.setattr(renderer, "_playwright_available", lambda: False)
    monkeypatch.setattr(renderer.local_renderer, "require_cjk_font", lambda: {"available": True})
    monkeypatch.setattr(renderer.local_renderer, "_font", portable_font)
    paths = renderer.render_pair(
        tmp_path,
        title=PHRASE,
        short_title="字体参与构图",
        subtitle=NOTE,
        theme_id="zen",
        hero_image=None,
        series_label="本地中文",
        cover_style=style,
        emphasis="构图",
    )

    with Image.open(paths["wide"]) as wide, Image.open(paths["square"]) as square:
        assert wide.size == renderer.wide_size
        assert square.size == renderer.square_size
        assert wide.getbbox() is not None
        assert square.getbbox() is not None


def test_wechat_cover_legacy_flag_skips_recipe_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = WeChatCoverRenderer(
        Settings(
            export_dir=tmp_path / "exports",
            typography_recipe_mode="legacy",
        )
    )
    monkeypatch.setattr(renderer, "_playwright_available", lambda: False)
    monkeypatch.setattr(
        renderer,
        "_apply_typography_recipe",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy cover must not use typography recipe v2")
        ),
    )

    paths = renderer.render_pair(
        tmp_path,
        title=PHRASE,
        short_title="字体参与构图",
        subtitle=NOTE,
        theme_id="zen",
        cover_style="editorial_split",
    )

    assert Path(paths["wide"]).is_file()
    assert Path(paths["square"]).is_file()

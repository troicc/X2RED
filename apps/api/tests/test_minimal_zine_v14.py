from __future__ import annotations

import io
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from app.core.config import Settings
from app.domain.platforms import PlatformVariant
from app.services.minimal_zine_native import MinimalZineNativeService


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        media_dir=tmp_path / "assets",
        raw_dir=tmp_path / "raw",
        export_dir=tmp_path / "exports",
        browser_profile_dir=tmp_path / "profile",
        native_skill_dir=tmp_path / "native-skills",
        scheduler_enabled=False,
    )


def generated_image_with_edge_badge() -> bytes:
    image = Image.new("RGB", (1024, 1536), "#ded4bf")
    draw = ImageDraw.Draw(image)
    draw.ellipse((230, 220, 800, 790), fill="#555555")
    draw.ellipse((455, 430, 660, 635), fill="#b51f2d")
    # Simulates a provider badge in the lower-right edge region.
    draw.rounded_rectangle((690, 1240, 1005, 1490), radius=45, fill="#ff00ff")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def test_minimal_zine_composes_local_text_and_drops_edge_badge(tmp_path: Path) -> None:
    service = MinimalZineNativeService(settings(tmp_path))
    path = tmp_path / "poster.png"
    service._compose_poster(
        generated_image_with_edge_badge(),
        path,
        spec={
            "phrase": "拦住你的不是想象力，是繁琐步骤",
            "note": "先把步骤缩短，再谈创意。",
            "accent": "#c91f2c",
        },
        recipe={"layout": "centered", "accent": "vermilion"},
        page=1,
        total=4,
    )

    with Image.open(path) as output:
        assert output.size == (1200, 2000)
        pixels = list(output.convert("RGB").getdata())
    magenta = sum(1 for red, green, blue in pixels if red > 240 and blue > 220 and green < 40)
    red_accent = sum(1 for red, green, blue in pixels if red > 150 and green < 80 and blue < 90)
    assert magenta == 0
    assert red_accent > 1000


def test_minimal_zine_rebuilds_preview_manifest_and_package_in_exports(
    tmp_path: Path,
) -> None:
    service = MinimalZineNativeService(settings(tmp_path))
    variant = PlatformVariant(
        id="variant_demo",
        source_id="source_demo",
        platform="wechat",
        format="light_series",
        version=1,
        title="复杂系统需要更短的步骤",
        subtitle="",
        summary="测试摘要",
        body_markdown="测试正文",
        tags="测试",
        theme="zen",
    )
    output_dir = service.settings.export_dir / "wechat" / variant.id
    output_dir.mkdir(parents=True)
    poster = output_dir / "poster-01.png"
    Image.new("RGB", (1200, 2000), "#e8ddc8").save(poster)

    files = service._rebuild_artifacts(
        variant=variant,
        metadata={
            "render_engine": "gc-minimal-zine-local-compositor-v2",
            "native_zine": {"compositor_version": service.compositor_version},
        },
        specs=[{"phrase": "复杂系统需要更短的步骤"}],
        output_dir=output_dir,
        output_paths={"poster_01": str(poster)},
    )

    export_root = service.settings.export_dir.resolve()
    assert all(export_root in Path(value).resolve().parents for value in files.values())
    assert Path(files["preview"]).is_file()
    assert Path(files["manifest"]).is_file()
    assert Path(files["package"]).is_file()
    with zipfile.ZipFile(files["package"]) as archive:
        names = set(archive.namelist())
    assert {"poster-01.png", "article.md", "manifest.json", "preview.html"}.issubset(names)


def test_minimal_zine_prompt_forbids_model_typography(tmp_path: Path) -> None:
    service = MinimalZineNativeService(settings(tmp_path))
    service.model.chat_json = lambda **_: {
        "final_prompt": (
            "A quiet aged paper art plate with one isolated rope knot sculpture, "
            "large negative space, restrained grayscale fibers and one red accent. "
            "The subject occupies a small visual cluster in the upper half."
        ),
        "recipe": {
            "layout": "centered",
            "anchor": "rope knot",
            "typography": "local-cjk",
            "accent": "vermilion",
            "texture": "aged paper",
            "mood": "quiet",
        },
        "interpretation": "用绳结表达流程阻力。",
    }
    result = service._compile_prompt(
        skill_text="Minimal Zine skill rules",
        variant=PlatformVariant(
            id="variant_prompt",
            source_id="source_prompt",
            platform="wechat",
            format="light_series",
            version=1,
            title="步骤比想象更重要",
            subtitle="",
            summary="",
            body_markdown="",
            tags="",
            theme="zen",
        ),
        spec={"phrase": "步骤比想象更重要", "visual_metaphor": "绳结"},
        page=1,
        total=3,
        recent_recipes=[],
    )
    prompt = result["final_prompt"]
    assert "NO TEXT" in prompt
    assert "NO WATERMARK" in prompt
    assert "NO BADGE" in prompt
    assert "bottom 30 percent blank" in prompt

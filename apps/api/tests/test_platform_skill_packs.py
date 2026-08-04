from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.domain.models import DraftRevision, SourceItem
from app.domain.platforms import PlatformVariant
from app.services.platform_studio import PlatformStudioService
from app.services.reader_editorial import ReaderFirstEditorialService
from app.services.rich_cards import RichCardService
from app.services.skill_packs import PACKS, pack_payloads
from app.services.wechat_renderer import WeChatHtmlRenderer
from app.services.wechat_themes import list_theme_payloads


def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def settings(tmp_path: Path) -> Settings:
    values = Settings(
        database_url="sqlite+pysqlite:///:memory:",
        media_dir=tmp_path / "assets",
        raw_dir=tmp_path / "raw",
        export_dir=tmp_path / "exports",
        browser_profile_dir=tmp_path / "profiles",
        scheduler_enabled=False,
        model_base_url="",
        model_name="",
    )
    values.ensure_directories()
    return values


def source_and_draft(db: Session) -> tuple[SourceItem, DraftRevision]:
    source = SourceItem(
        provider="x2pdf",
        platform="x",
        external_id="article-001",
        canonical_url="https://x.com/example/article/1",
        author_handle="example",
        author_name="Example Author",
        content_kind="article",
        text_original=(
            "作者把视频模型中最慢的一段注意力计算重写成了专门面向 Blackwell GPU 的 CUDA 内核。"
            "在作者给出的局部测试里，成本从约五秒降到零点一六秒。"
            "真正重要的不是标题里的倍数，而是先筛掉无效 token，再利用新硬件的数据搬运能力。"
        ) * 4,
        structured_content_json=json.dumps({"title": "一次底层内核优化如何改变视频生成速度"}),
    )
    db.add(source)
    db.flush()
    draft = DraftRevision(
        source_id=source.id,
        version=1,
        style="explain",
        title="视频生成提速，关键可能不在换模型",
        body=(
            "一个视频模型里最耗时间的那段计算，被重新写成了面向新一代 GPU 的底层内核。\n\n"
            "这次优化先筛掉大量无效计算，再重新安排数据搬运。VSA 可以理解为只让真正重要的 token 参与计算。\n\n"
            "据作者在 Blackwell GPU 上的局部测试，相关计算从约 5 秒降到 0.16 秒。"
            "这不等于整段视频生成快了同样倍数，但说明模型速度很大程度上取决于底层实现。"
        ),
        tags="AI工程,CUDA,视频生成",
        provenance_json="{}",
    )
    db.add(draft)
    db.flush()
    return source, draft


def test_wechat_renderer_outputs_constrained_inline_html() -> None:
    renderer = WeChatHtmlRenderer()
    fragment = renderer.render_fragment(
        title="一段 CUDA 内核为什么能改变视频生成速度",
        summary="不换模型，只重写最慢的一段计算，也可能带来巨大变化。",
        markdown="""
开头先用普通读者能理解的语言说明问题。

## 真正优化的是什么

VSA 可以理解为先筛掉大量无效 token，只保留真正影响结果的部分。

- 局部延迟从 5 秒降到 0.16 秒
- 优化利用了 Blackwell GPU 的 TMA 与 TMEM

## 数字意味着什么

> 54 倍是局部注意力内核的结果，不是端到端视频生成速度。

```python
latency_ms = 160
```
""".strip(),
        theme_id="graphite",
        author="EasyMaker",
        source_url="https://x.com/example/article/1",
    )
    validation = renderer.validate(fragment)
    assert validation.errors == []
    assert fragment.startswith("<section")
    assert fragment.endswith("</section>")
    assert "<style" not in fragment
    assert "<script" not in fragment
    assert "<div" not in fragment
    assert " class=" not in fragment
    assert "VSA" in fragment
    assert fragment.count("<h2") == 2


def test_skill_pack_registry_preserves_license_boundaries(tmp_path: Path) -> None:
    db = session()
    payloads = {item.id: item for item in pack_payloads(db, settings(tmp_path))}
    assert "xhs-editorial-growth" in payloads
    assert "wechat-inline-design-system" in payloads
    assert payloads["xhs-editorial-growth"].integration_mode == "native-adaptation"
    assert payloads["wechat-inline-design-system"].licenses == ["AGPL-3.0"]
    assert payloads["wechat-inline-design-system"].integration_mode == "independent-reimplementation"
    assert payloads["material-first-social-design"].integration_mode == "independent-reimplementation"
    assert all(pack.skills for pack in PACKS)
    assert len(list_theme_payloads()) == 6


@pytest.mark.asyncio
async def test_wechat_variant_fallback_renders_package(tmp_path: Path) -> None:
    db = session()
    source, draft = source_and_draft(db)
    config = settings(tmp_path)
    service = PlatformStudioService(config, ReaderFirstEditorialService(config))
    variant = await service.create_wechat_variant(
        db,
        source=source,
        draft=draft,
        theme="auto",
        mode="adapt",
        include_citations=True,
        include_illustration_plan=True,
        author="EasyMaker",
    )
    assert variant.platform == "wechat"
    assert variant.version == 1
    assert "来源与延伸阅读" in variant.body_markdown
    rendered, validation, files = service.render_wechat_variant(db, variant, package=True)
    assert validation.errors == []
    assert rendered.status == "packaged"
    assert Path(files["html"]).is_file()
    assert Path(files["preview"]).is_file()
    assert Path(files["wide"]).is_file()
    assert Path(files["square"]).is_file()
    assert Path(files["package"]).is_file()
    assert Image.open(files["wide"]).size == (2100, 900)
    assert Image.open(files["square"]).size == (1080, 1080)
    assert db.scalar(select(PlatformVariant).where(PlatformVariant.id == variant.id)) is variant


def test_rich_cards_store_style_layout_palette_and_material(tmp_path: Path) -> None:
    db = session()
    _, draft = source_and_draft(db)
    service = RichCardService(settings(tmp_path))
    render = service.render(
        db,
        draft,
        template="tech_minimal",
        visual_style="swiss",
        layout="comparison",
        palette="macaron",
        material_strategy="text_only",
        max_cards=5,
    )
    specs = json.loads(render.spec_json)
    assert specs
    assert all(item["visual_style"] == "swiss" for item in specs)
    assert all(item["palette"] == "macaron" for item in specs)
    assert all(item["material_strategy"] == "text_only" for item in specs)
    assert all(item["visibility_mode"] == "public" for item in specs)
    assert all(not item.get("source") and not item.get("footer") for item in specs)
    assert "X2RED" not in json.dumps(specs, ensure_ascii=False)
    assert all(not item.get("hero_image") for item in specs)
    paths = json.loads(render.output_paths_json)
    assert len(paths) == len(specs)
    assert all(Path(path).is_file() for path in paths)


def test_platform_frontend_and_health_contracts() -> None:
    root = Path(__file__).resolve().parents[3]
    platform_js = (root / "apps/api/app/static/platform-v08.js").read_text(encoding="utf-8")
    studio_js = (root / "apps/api/app/static/studio-v07.js").read_text(encoding="utf-8")
    card_js = (root / "apps/api/app/static/card-skill-v08.js").read_text(encoding="utf-8")
    review_js = (root / "apps/api/app/static/review-v09.js").read_text(encoding="utf-8")
    product_shell_js = (root / "apps/api/app/static/product-shell-v15.js").read_text(
        encoding="utf-8"
    )
    light_v15_js = (root / "apps/api/app/static/light-content-v15.js").read_text(
        encoding="utf-8"
    )
    light_v15_css = (root / "apps/api/app/static/light-content-v15.css").read_text(
        encoding="utf-8"
    )
    product_shell_css = (root / "apps/api/app/static/product-shell-v15.css").read_text(
        encoding="utf-8"
    )
    native_js = (root / "apps/api/app/static/native-skills-v11.js").read_text(
        encoding="utf-8"
    )
    platforms_api = (root / "apps/api/app/api/platforms.py").read_text(encoding="utf-8")
    native_api = (root / "apps/api/app/api/native_skills.py").read_text(encoding="utf-8")
    ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    main_py = (root / "apps/api/app/main.py").read_text(encoding="utf-8")
    notices = (root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "公众号工作台" in platform_js
    assert "skill-packs" in platform_js
    assert "去公众号" in platform_js
    assert "card-visual-style" in card_js
    assert 'actions.querySelector(":scope > #card-template")' in card_js
    assert "parentElement || document.getElementById(\"card-template\")" not in card_js
    assert "审阅故事板" in review_js
    assert "模块 Review" in review_js
    assert "发布助手" in review_js
    assert "const controller" in light_v15_js
    assert "任务设置" in light_v15_js
    assert "文案候选" in light_v15_js
    assert "视觉分镜" in light_v15_js
    assert "成品交付" in light_v15_js
    assert 'const tab = button("", "light-stage-tab"' in light_v15_js
    assert 'tab.setAttribute("aria-label", `阶段 ${String(number).padStart(2, "0")}：${title}`);' in light_v15_js
    assert 'button(title, "light-stage-tab"' not in light_v15_js
    assert "light-storyboard-card-compact" in light_v15_js
    assert "if (item.page !== state.selectedPage) return renderStoryboardSummary(item);" in light_v15_js
    assert 'storyboardSelectField(item, "layout", "版式", LAYOUT_OPTIONS)' in light_v15_js
    assert 'storyboardSelectField(item, "anchor", "视觉锚点", ANCHOR_OPTIONS)' in light_v15_js
    assert 'storyboardSelectField(item, "texture", "质感", TEXTURE_OPTIONS)' in light_v15_js
    assert "storyboardAccentField(item)" in light_v15_js
    assert 'type: "number", min: 0, max: 1, step: 0.01' in light_v15_js
    assert 'type: "number", min: 0.65, max: 2, step: 0.05' in light_v15_js
    assert ".light-storyboard-card-compact" in light_v15_css
    assert ".light-storyboard-summary" in light_v15_css
    assert ".light-action-bar {\n  position: static;" in light_v15_css
    assert "position: sticky;\n  bottom: 16px;" not in light_v15_css
    assert "@media (min-width: 801px) and (max-width: 900px)" in product_shell_css
    assert "@media (max-width: 800px)" in product_shell_css
    assert "/wechat/light/variants/${encodeURIComponent(variant.id)}/storyboard" in light_v15_js
    assert "仅重新排版（不调用图片模型）" in light_v15_js
    assert "重新生成本页（调用图片模型）" in light_v15_js
    assert "mode, pages: uniquePages" in light_v15_js
    assert "meta.poster_specs" in light_v15_js
    assert "state.currentVariant?.source_id === state.brief.sourceId" in light_v15_js
    assert 'const preferredVariantId = sourceId ? ""' in light_v15_js
    assert "state.variants.find((item) => item.source_id === state.brief.sourceId) || null" in light_v15_js
    assert 'view: "signals-view"' in product_shell_js
    assert 'view: "materials-view"' in product_shell_js
    assert 'view: "corpus-pools-view"' in product_shell_js
    assert 'view: "workbench-view"' in product_shell_js
    assert 'view: "writing-view"' in product_shell_js
    assert 'view: "wechat-view"' in product_shell_js
    assert 'view: "publish-view"' in product_shell_js
    assert 'view: "style-lab-view"' in product_shell_js
    assert 'view: "settings-view"' in product_shell_js
    assert "button.dataset.projectId === expectedId" in product_shell_js
    assert "button.dataset.projectId = project.id" in studio_js
    assert "native-zine-render" not in native_js
    assert "window.fetch =" not in native_js
    assert "/minimal-zine/variants/" not in native_js
    assert "/wechat/light/variants/{variant_id}/storyboard" in platforms_api
    assert 'Literal["render_missing", "recompose", "regenerate"]' in native_api
    assert main_py.count('src="/static/product-shell-v15.js"') == 1
    assert main_py.count('src="/static/light-content-v15.js"') == 1
    for retired in (
        "studio-navigation-v071.js",
        "light-content-v10.js",
        "light-content-lab-v12.js",
        "light-content-fixes-v14.js",
        "information-architecture-v14.js",
    ):
        assert retired not in main_py
        assert retired not in ci
    assert 'version="0.11.0"' in main_py
    assert "reviewed-semantic-playwright" in main_py
    assert "reviewed-module-tree-plus-cover-brief" in main_py
    assert "six-route-distinct-visual-v12" in main_py
    assert "review-v09.js" in main_py
    assert "review-bridge-v09.js" in main_py
    assert "No upstream code" in notices

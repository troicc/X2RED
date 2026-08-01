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
    card_js = (root / "apps/api/app/static/card-skill-v08.js").read_text(encoding="utf-8")
    review_js = (root / "apps/api/app/static/review-v09.js").read_text(encoding="utf-8")
    light_lab_js = (root / "apps/api/app/static/light-content-lab-v12.js").read_text(encoding="utf-8")
    main_py = (root / "apps/api/app/main.py").read_text(encoding="utf-8")
    notices = (root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "公众号工作台" in platform_js
    assert "skill-packs" in platform_js
    assert "去公众号" in platform_js
    assert "card-visual-style" in card_js
    assert "审阅故事板" in review_js
    assert "模块 Review" in review_js
    assert "发布助手" in review_js
    assert "长文编辑" in light_lab_js
    assert "轻内容图组" in light_lab_js
    assert "多 Agent 生成 3 个候选" in light_lab_js
    assert "批准并加入优质语料" in light_lab_js
    assert 'version="0.10.0"' in main_py
    assert "reviewed-semantic-playwright" in main_py
    assert "reviewed-module-tree-plus-cover-brief" in main_py
    assert "six-route-distinct-visual-v12" in main_py
    assert "review-v09.js" in main_py
    assert "review-bridge-v09.js" in main_py
    assert "No upstream code" in notices

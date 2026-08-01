from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.domain.models import DraftRevision, SourceItem
from app.services.cards import CardService
from app.services.publication_safety import contains_internal_marker
from app.services.rich_cards import RichHtmlCardRenderer
from app.services.skill_pack_editorial import SkillPackEditorialService
from app.services.wechat_cover_renderer import WeChatCoverRenderer


def test_wechat_cover_is_publish_ready_by_default() -> None:
    renderer = WeChatCoverRenderer()
    document = renderer._document(
        width=2100,
        height=900,
        mode="wide",
        title="视觉反馈闭环如何改变 3D 创作",
        subtitle="从盲发指令到边看边改",
        theme_id="editorial_blue",
        hero_image="",
        series_label="",
        cover_style="auto",
        emphasis="",
    )
    assert "视觉反馈闭环如何改变 3D 创作" in document
    assert "WECHAT / X2RED" not in document
    assert "从一份来源" not in document
    assert "X2PDF" not in document
    assert not contains_internal_marker(document)


def test_xhs_skill_storyboard_is_normalized_for_public_cards() -> None:
    normalized = SkillPackEditorialService._normalize_storyboard(
        [
            {
                "kind": "hero_cover",
                "label": "技术趋势",
                "title": "AI 开始看见自己的 3D 结果",
                "subtitle": "从盲发指令到视觉反馈闭环",
                "items": [],
                "visual_brief": "使用来源截图",
                "asset_role": "source",
            },
            {
                "kind": "concept_diagram",
                "label": "拆开来看",
                "title": "闭环由四个动作组成",
                "items": ["生成场景", "观察结果", "识别错误", "继续修改"],
                "visual_brief": "四节点闭环",
                "asset_role": "diagram",
            },
        ]
    )
    assert [item["kind"] for item in normalized] == ["hero_cover", "concept_diagram"]
    assert normalized[1]["items"] == ["生成场景", "观察结果", "识别错误", "继续修改"]


def test_card_builder_prefers_skill_storyboard_and_removes_internal_metadata(
    tmp_path: Path,
) -> None:
    source = SourceItem(
        id="src-public-card",
        provider="x2pdf",
        platform="x",
        external_id="article-public-card",
        canonical_url="https://x.com/example/article/1",
        author_handle="example",
        author_name="Example",
        content_kind="article",
        text_original="AI 先生成 3D 场景，再根据视觉结果纠错并继续修改。",
        metrics_json="{}",
    )
    storyboard = [
        {
            "kind": "hero_cover",
            "label": "技术趋势",
            "title": "AI 开始看见自己的 3D 结果",
            "subtitle": "从盲发指令到视觉反馈闭环",
            "items": [],
            "asset_role": "none",
        },
        {
            "kind": "workflow_flow",
            "label": "工作方式",
            "title": "3D 创作进入反馈闭环",
            "items": ["生成场景", "观察结果", "识别错误", "继续修改"],
            "asset_role": "diagram",
        },
        {
            "kind": "opinion_close",
            "label": "我的判断",
            "title": "真正变化的是创作起点",
            "subtitle": "AI 不再只会执行，也开始根据结果修正下一步。",
            "items": [],
            "asset_role": "none",
        },
    ]
    draft = DraftRevision(
        id="draft-public-card",
        source_id=source.id,
        version=1,
        style="explain",
        title="AI 开始看见自己的 3D 结果",
        body="AI 先生成场景，再观察结果、识别错误并继续修改。",
        tags="AI,3D创作",
        provenance_json=json.dumps(
            {
                "xhs_skill_pack": {
                    "content_type": "technology",
                    "card_storyboard": storyboard,
                }
            },
            ensure_ascii=False,
        ),
    )
    draft.source = source
    service = CardService(
        Settings(
            media_dir=tmp_path / "assets",
            raw_dir=tmp_path / "raw",
            export_dir=tmp_path / "exports",
            browser_profile_dir=tmp_path / "profiles",
        )
    )
    specs = service._build_specs(draft, max_cards=6)
    assert [item["kind"] for item in specs] == [
        "hero_cover",
        "workflow_flow",
        "opinion_close",
    ]
    assert specs[1]["items"] == ["生成场景", "观察结果", "识别错误", "继续修改"]
    assert all(item["visibility_mode"] == "public" for item in specs)
    assert all(not item["source"] and not item["footer"] for item in specs)
    assert not contains_internal_marker(json.dumps(specs, ensure_ascii=False))

    for index, spec in enumerate(specs, start=1):
        spec.update(
            {
                "page": index,
                "total": len(specs),
                "visual_style": "minimal",
                "layout": "auto",
                "palette": "neutral",
            }
        )
    document = RichHtmlCardRenderer()._document(specs[0], "clean_news")
    assert "AI 开始看见自己的 3D 结果" in document
    assert "X2RED" not in document
    assert "X SOURCE" not in document

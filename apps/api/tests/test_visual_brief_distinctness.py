from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.domain.platforms import PlatformVariant
from app.domain.visual_brief_schemas import (
    PageVisualBrief,
    PageVisualConceptCandidate,
)
from app.services.minimal_zine_native import (
    MinimalZineNativeService,
    storyboard_model_input_changed,
)
from app.services.native_skill_manager import NativeSkillError
from app.services.visual_brief import (
    LAYOUT_FAMILIES,
    VISUAL_BRIEF_DEGRADED,
    VisualBriefError,
    VisualBriefService,
)
from app.services.visual_distinctness import VisualDistinctnessService


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'brief.db'}",
        media_dir=tmp_path / "assets",
        raw_dir=tmp_path / "raw",
        export_dir=tmp_path / "exports",
        browser_profile_dir=tmp_path / "profile",
        native_skill_dir=tmp_path / "skills",
        scheduler_enabled=False,
        model_base_url="",
        model_api_key="",
        model_name="",
        visual_brief_mode="production",
    )


def posters() -> list[dict[str, Any]]:
    return [
        {
            "phrase": "压力不是工作量本身",
            "note": "大脑一直在预演坏情况",
            "visual_metaphor": "同一只发光屏幕",
            "photo_direction": "夜间办公室的工作台",
            "layout": "center-fragment",
            "accent": "#b65d3c",
            "mood": "紧绷",
            "evidence_basis": "来源 1 描述下班后仍保持警觉",
            "source_refs": ["详细来源 1"],
        },
        {
            "phrase": "领导一个皱眉能琢磨半天",
            "note": "不确定性让警报迟迟不关",
            "visual_metaphor": "同一只发光屏幕",
            "photo_direction": "会议结束后的空会议室",
            "layout": "center-fragment",
            "accent": "#b65d3c",
            "mood": "警觉",
            "evidence_basis": "来源 3 的领导细节触发反复揣测",
            "source_refs": ["详细来源 3"],
        },
        {
            "phrase": "一句关心为什么会点着你",
            "note": "安全关系承接了白天的损耗",
            "visual_metaphor": "同一只发光屏幕",
            "photo_direction": "家门口与餐桌之间",
            "layout": "center-fragment",
            "accent": "#b65d3c",
            "mood": "刺痛",
            "evidence_basis": "来源 5 的回家迁怒案例",
            "source_refs": ["详细来源 5"],
        },
        {
            "phrase": "下班要真正结束值班",
            "note": "先给大脑一个明确缓冲带",
            "visual_metaphor": "同一只发光屏幕",
            "photo_direction": "玄关里放下工牌",
            "layout": "center-fragment",
            "accent": "#b65d3c",
            "mood": "松开",
            "evidence_basis": "来源 7 的进门前缓冲方案",
            "source_refs": ["详细来源 7"],
        },
    ]


class FakeEditorial:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def _chat_json(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_deterministic_bundle_freezes_three_candidates_and_a_distinct_series(
    tmp_path: Path,
) -> None:
    service = VisualBriefService(settings(tmp_path), FakeEditorial([]))  # type: ignore[arg-type]
    bundle = service.build_deterministic(
        article_thesis="长期不确定性让大脑在下班后仍处于应激值班",
        posters=posters(),
        visual_style="minimal_zine",
        content_recipe="comfort",
    )
    selected = bundle.selected_candidates()
    bible_text = json.dumps(bundle.visual_bible.model_dump(mode="json"), ensure_ascii=False)

    assert len(bundle.pages) == 4
    assert all(len(page.candidates) == 3 for page in bundle.pages)
    assert bundle.distinctness.passed is True
    assert len(bundle.distinctness.layout_families) >= 3
    assert len({item.brief.concrete_subject for item in selected}) == 4
    assert [item.brief.visual_role for item in selected] == [
        "cover",
        "scene",
        "evidence",
        "conclusion",
    ]
    assert all(item.brief.evidence_refs for item in selected)
    assert all(
        set(bundle.visual_bible.invariants).issubset(item.brief.must_preserve)
        for item in selected
    )
    assert all(item.brief.concrete_subject not in bible_text for item in selected)

    applied = service.apply_bundle(posters(), bundle)
    assert all("series_motif" not in item for item in applied)
    assert len({item["layout"] for item in applied}) >= 3
    assert len({item["visual_metaphor"] for item in applied}) == 4
    assert all(item["page_visual_brief"]["evidence_refs"] for item in applied)


def test_c0_visual_fixture_series_all_pass_v2_editorial_acceptance(
    tmp_path: Path,
) -> None:
    fixture_path = Path(__file__).parent / "evals" / "visual_cases.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in fixture["cases"]:
        grouped.setdefault(case["article_thesis"], []).append(case)

    service = VisualBriefService(settings(tmp_path), FakeEditorial([]))  # type: ignore[arg-type]
    assert len(grouped) == 5
    for thesis, cases in grouped.items():
        series = [
            {
                "phrase": case["phrase"],
                "note": case["note"],
                "visual_metaphor": case["storyboard"]["visual_metaphor"],
                "photo_direction": case["storyboard"]["visual_metaphor"],
                "layout": case["storyboard"]["layout"],
                "accent": "#b65d3c",
                "mood": case["storyboard"]["mood"],
                "evidence_basis": case["evidence_summary"],
                "source_refs": [case["id"]],
            }
            for case in cases
        ]
        bundle = service.build_deterministic(
            article_thesis=thesis,
            posters=series,
            visual_style="minimal_zine",
            content_recipe="fixture-eval",
        )
        selected = bundle.selected_candidates()
        bible_text = json.dumps(
            bundle.visual_bible.model_dump(mode="json"),
            ensure_ascii=False,
        )

        assert bundle.distinctness.passed is True
        assert len(bundle.distinctness.layout_families) >= 3
        assert len({item.brief.concrete_subject for item in selected}) == 4
        assert all(item.brief.visual_role for item in selected)
        assert all(item.brief.evidence_refs for item in selected)
        assert all(item.brief.concrete_subject not in bible_text for item in selected)
        assert all(
            case["storyboard"]["visual_metaphor"] not in bible_text
            for case in cases
        )


def candidate(
    *,
    page: int,
    candidate_index: int,
    subject: str,
    layout: str,
    anchor: str,
) -> PageVisualConceptCandidate:
    brief = PageVisualBrief(
        page=page,
        section_id=f"page-{page:02d}",
        visual_role="cover" if page == 1 else "conclusion" if page == 4 else "evidence",
        claim=f"第 {page} 页判断",
        reader_emotion="清晰",
        concrete_subject=subject,
        secondary_subject="",
        action_or_relation="形成一个可见、可核对的空间关系",
        setting="纸本工作台",
        viewpoint="正俯视",
        crop="完整主体",
        lighting="漫射光",
        materials=["吸墨纸"],
        layout_family=layout,
        typography_mode="local-cjk-editorial",
        palette_delta=["#b65d3c"],
        must_preserve=["中文本地排版"],
        must_avoid=["可读模型文字"],
        evidence_refs=[f"详细来源 {page}"],
    )
    return PageVisualConceptCandidate(
        candidate_id=f"p{page}-c{candidate_index}",
        brief=brief,
        anchor_family=anchor,
        rationale="依据本页证据选择",
        editor_score=8,
    )


def test_distinctness_editor_avoids_shared_subject_anchor_and_layout() -> None:
    candidate_sets: list[list[PageVisualConceptCandidate]] = []
    distinct_subjects = (
        "会议桌上展开的打卡记录",
        "玄关地面刚放下的工牌",
        "餐桌边缘倾倒的水杯",
        "夜班手机上未读的提醒",
    )
    backup_subjects = (
        "贴有时间标签的纸质日程",
        "被用钥匙压住的进门清单",
        "停在半张对话记录上的铅笔",
        "收进档案袋的下班核对单",
    )
    for page in range(1, 5):
        candidate_sets.append(
            [
                candidate(
                    page=page,
                    candidate_index=1,
                    subject="同一只玻璃杯",
                    layout="center-fragment",
                    anchor="object-specimen",
                ),
                candidate(
                    page=page,
                    candidate_index=2,
                    subject=distinct_subjects[page - 1],
                    layout=LAYOUT_FAMILIES[page - 1],
                    anchor=("tiny-faded-photo", "torn-paper-clipping", "flat-silhouette", "old-printed-illustration")[page - 1],
                ),
                candidate(
                    page=page,
                    candidate_index=3,
                    subject=backup_subjects[page - 1],
                    layout=LAYOUT_FAMILIES[page + 2],
                    anchor="translucent-geometric-overlay",
                ),
            ]
        )

    selected, report = VisualDistinctnessService().select(candidate_sets)

    assert report.passed is True
    assert len({item.brief.concrete_subject for item in selected}) == 4
    assert len(report.layout_families) >= 3
    assert not all(item.anchor_family == "object-specimen" for item in selected)


def test_cliche_and_compound_abstraction_are_blocking() -> None:
    selected = [
        candidate(
            page=1,
            candidate_index=1,
            subject="黑暗中的一束光承载焦虑压力成长希望",
            layout="center-fragment",
            anchor="object-specimen",
        ),
        candidate(
            page=2,
            candidate_index=1,
            subject="第二组证据票据",
            layout="dual-panel",
            anchor="object-specimen",
        ),
        candidate(
            page=3,
            candidate_index=1,
            subject="第三段流程纸带",
            layout="upper-right-block",
            anchor="object-specimen",
        ),
        candidate(
            page=4,
            candidate_index=1,
            subject="第四份核对封套",
            layout="edge-counterweight",
            anchor="object-specimen",
        ),
    ]

    report = VisualDistinctnessService().evaluate(selected)

    assert report.passed is False
    assert {issue.code for issue in report.issues if issue.blocking} >= {
        "visual_cliche",
        "compound_abstraction",
        "repeated_anchor",
    }


@pytest.mark.asyncio
async def test_model_build_runs_bible_before_three_page_candidates(
    tmp_path: Path,
) -> None:
    seed_service = VisualBriefService(settings(tmp_path), FakeEditorial([]))  # type: ignore[arg-type]
    bible = seed_service.default_bible(
        visual_style="minimal_zine",
        content_recipe="comfort",
    )
    sets = seed_service._fallback_candidate_sets(  # noqa: SLF001
        article_thesis="不确定性让下班后的大脑继续值班",
        posters=posters(),
        bible=bible,
        prefer_structured=True,
    )
    editorial = FakeEditorial(
        [
            {"visual_bible": bible.model_dump(mode="json")},
            {
                "pages": [
                    {
                        "page": page,
                        "candidates": [item.model_dump(mode="json") for item in values],
                    }
                    for page, values in enumerate(sets, start=1)
                ]
            },
        ]
    )
    service = VisualBriefService(settings(tmp_path), editorial)  # type: ignore[arg-type]

    bundle = await service.build(
        article_thesis="不确定性让下班后的大脑继续值班",
        posters=posters(),
        audience="高压职场读者",
        visual_style="minimal_zine",
        content_recipe="comfort",
        model_name="test-model",
        reasoning_effort="high",
        use_model=True,
    )

    assert bundle.mode == "production"
    assert len(editorial.calls) == 2
    assert "文章级视觉系统总监" in editorial.calls[0]["system_prompt"]
    assert "逐页视觉主编" in editorial.calls[1]["system_prompt"]
    assert all(len(page.candidates) == 3 for page in bundle.pages)


@pytest.mark.asyncio
async def test_invalid_model_candidates_fall_back_with_explicit_warning(
    tmp_path: Path,
) -> None:
    service_seed = VisualBriefService(settings(tmp_path), FakeEditorial([]))  # type: ignore[arg-type]
    bible = service_seed.default_bible(
        visual_style="minimal_zine",
        content_recipe="comfort",
    )
    editorial = FakeEditorial(
        [
            {"visual_bible": bible.model_dump(mode="json")},
            {"pages": [{"page": 1, "candidates": []}]},
        ]
    )
    service = VisualBriefService(settings(tmp_path), editorial)  # type: ignore[arg-type]

    bundle = await service.build(
        article_thesis="不确定性让下班后的大脑继续值班",
        posters=posters(),
        audience="",
        visual_style="minimal_zine",
        content_recipe="comfort",
        model_name="test-model",
        reasoning_effort="high",
        use_model=True,
    )

    assert bundle.mode == "deterministic"
    assert any(value.startswith(VISUAL_BRIEF_DEGRADED) for value in bundle.warnings)
    assert bundle.distinctness.passed is True


def test_human_refreeze_rejects_repeated_subject_and_preserves_bible(
    tmp_path: Path,
) -> None:
    service = VisualBriefService(settings(tmp_path), FakeEditorial([]))  # type: ignore[arg-type]
    bundle = service.build_deterministic(
        article_thesis="不确定性让下班后的大脑继续值班",
        posters=posters(),
        visual_style="minimal_zine",
        content_recipe="comfort",
    )
    applied = service.apply_bundle(posters(), bundle)
    applied[1]["page_visual_brief"]["concrete_subject"] = applied[0][
        "page_visual_brief"
    ]["concrete_subject"]

    with pytest.raises(VisualBriefError, match="distinctness"):
        service.refreeze_after_human_edit(
            previous_bundle=bundle.model_dump(mode="json"),
            posters=applied,
            article_thesis="不确定性让下班后的大脑继续值班",
        )

    applied = service.apply_bundle(posters(), bundle)
    applied[1]["page_visual_brief"]["action_or_relation"] = "把两段证据改成左右对照关系"
    revised, specs = service.refreeze_after_human_edit(
        previous_bundle=bundle.model_dump(mode="json"),
        posters=applied,
        article_thesis="不确定性让下班后的大脑继续值班",
    )

    assert revised.source_fingerprint != bundle.source_fingerprint
    assert revised.visual_bible == bundle.visual_bible
    assert specs[1]["visual_brief_source_fingerprint"] == revised.source_fingerprint
    assert "HUMAN_EDITED_VISUAL_BRIEF" in revised.warnings


def test_prompt_context_uses_frozen_page_brief_as_visual_authority(
    tmp_path: Path,
) -> None:
    visual_service = VisualBriefService(settings(tmp_path), FakeEditorial([]))  # type: ignore[arg-type]
    bundle = visual_service.build_deterministic(
        article_thesis="不确定性让下班后的大脑继续值班",
        posters=posters(),
        visual_style="minimal_zine",
        content_recipe="comfort",
    )
    specs = visual_service.apply_bundle(posters(), bundle)
    specs[0]["visual_metaphor"] = "应被忽略的泛化希望灯塔"
    specs[0]["phrase"] = "这句本地排版文案不得进入画面推导"
    specs[0]["note"] = "这段本地说明也不得进入画面推导"
    variant = PlatformVariant(
        id="variant-brief-authority",
        source_id="source-brief-authority",
        platform="wechat",
        format="light_series",
        version=1,
        title="下班后的隐形值班",
        subtitle="",
        summary="大脑仍在预演不确定性",
        body_markdown="正文",
        tags="",
        theme="zen",
    )
    metadata = {
        "visual_brief_mode": "production",
        "visual_bible": bundle.visual_bible.model_dump(mode="json"),
        "strategy": {"content_thesis": "不确定性让下班后的大脑继续值班"},
        "poster_specs": specs,
    }
    native = MinimalZineNativeService(settings(tmp_path))

    context = native._visual_prompt_context(  # noqa: SLF001
        variant=variant,
        metadata=metadata,
        specs=specs,
        page=1,
    )

    selected = bundle.selected_candidates()[0].brief
    assert context.page_visual_brief == selected
    assert context.current_page_concept.startswith(selected.concrete_subject)
    assert "希望灯塔" not in context.current_page_concept
    assert context.layout_hint == selected.layout_family

    model_payload = native.prompt_compiler._model_context_payload(context)  # noqa: SLF001
    compiler_request = native.prompt_compiler._compiler_request(  # noqa: SLF001
        bundle="# pinned skill",
        context=context,
        feature_mode="production",
    )
    assert "phrase" not in model_payload
    assert "note" not in model_payload
    assert specs[0]["phrase"] not in compiler_request
    assert specs[0]["note"] not in compiler_request
    recipe = native.prompt_compiler._coerce_recipe(  # noqa: SLF001
        {
            "layout_family": "dual-panel",
            "typography_mode": "model-chosen-type",
            "main_hue": "#ffffff",
            "mood": "model-chosen-mood",
        },
        context,
    )
    assert recipe.layout_family == selected.layout_family
    assert recipe.typography_mode == selected.typography_mode
    assert recipe.main_hue == selected.palette_delta[0]
    assert recipe.mood == selected.reader_emotion

    missing = [dict(item) for item in specs]
    missing[0].pop("page_visual_brief")
    with pytest.raises(NativeSkillError, match="PageVisualBrief"):
        native._visual_prompt_context(  # noqa: SLF001
            variant=variant,
            metadata=metadata,
            specs=missing,
            page=1,
        )


def test_page_brief_change_invalidates_prompt_semantics(tmp_path: Path) -> None:
    service = VisualBriefService(settings(tmp_path), FakeEditorial([]))  # type: ignore[arg-type]
    bundle = service.build_deterministic(
        article_thesis="不确定性让下班后的大脑继续值班",
        posters=posters(),
        visual_style="minimal_zine",
        content_recipe="comfort",
    )
    previous = service.apply_bundle(posters(), bundle)[0]
    revised = json.loads(json.dumps(previous, ensure_ascii=False))
    revised["page_visual_brief"]["concrete_subject"] = "一条被分成四段的夜间值班记录带"

    assert storyboard_model_input_changed(previous, revised) is True

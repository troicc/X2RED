from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.domain.platforms import PlatformVariant
from app.domain.visual_prompt_schemas import VisualPromptContext
from app.services.minimal_zine_native import MinimalZineNativeService
from app.services.model_client import ModelClientError
from app.services.visual_prompt_compiler import DEGRADED_FALLBACK, VisualPromptCompiler


def settings(tmp_path: Path, *, mode: str = "production") -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'visual-prompt.db'}",
        media_dir=tmp_path / "assets",
        raw_dir=tmp_path / "raw",
        export_dir=tmp_path / "exports",
        browser_profile_dir=tmp_path / "profile",
        native_skill_dir=tmp_path / "native-skills",
        scheduler_enabled=False,
        model_base_url="https://model.invalid/v1",
        model_name="test-text-model",
        minimal_zine_prompt_mode=mode,
    )


def context(**overrides: object) -> VisualPromptContext:
    values: dict[str, object] = {
        "variant_id": "variant_prompt_v1",
        "page": 2,
        "total_pages": 4,
        "article_thesis": "疲惫不只来自体力消耗，也来自持续切换注意力",
        "section_title": "被切碎的一天",
        "page_visual_role": "evidence",
        "phrase": "真正累人的，是不停切换",
        "note": "消息、会议和琐事把完整时间切成碎片",
        "evidence_summary": "详细来源 2 记录了一天内十七次任务切换",
        "audience": "长期处理知识工作、下班后仍然疲惫的读者",
        "emotion": "克制、清醒，带一点被理解的松弛",
        "current_page_concept": "一张被多次裁断又重新拼接的工作便笺",
        "visual_bible": {
            "paper": "warm aged stock",
            "series_hue": "vermilion",
            "forbidden": ["repeated centered photo"],
        },
        "previous_page_concept": "一把没有搬动重物却弯下的椅背",
        "next_page_concept": "桌面上只剩一格完整的安静时间",
        "content_recipe": "short_commentary",
        "source_fit": "来源包含可核对的任务切换记录",
        "layout_hint": "center-fragment",
        "anchor_hint": "object-specimen",
        "texture_hint": "xerox-softness",
        "main_hue_hint": "cobalt",
        "mood_hint": "quiet",
    }
    values.update(overrides)
    return VisualPromptContext.model_validate(values)


def model_result() -> dict[str, object]:
    return {
        "positive_prompt": (
            "Tall 3:5 warm aged-paper plate with eighty percent open paper and an upper-right-block rhythm.\n\n"
            "One torn vermilion work memo is cut into seventeen narrow strips, offset like interrupted time while its original silhouette remains readable.\n\n"
            "Dry letterpress fibers, pale graphite registration marks and a single saturated vermilion hinge create a tactile editorial focal event.\n\n"
            "Diffuse window light, matte absorbent stock and quiet documentary tension connect the neighboring chair and empty-time concepts."
        ),
        "recipe": {
            "layout_family": "upper-right-block",
            "anchor_form": "torn-paper-clipping",
            "typography_mode": "local-cjk",
            "texture_mode": "letterpress-ink-bleed",
            "decorative_system": ["graphite registration ticks"],
            "main_hue": "vermilion",
            "mood": "quiet documentary tension",
        },
        "invariants": ["Keep the memo silhouette singular."],
        "exclusions": ["readable text or UI"],
        "warnings": [],
    }


def fallback_recipe() -> dict[str, object]:
    return {
        "layout": "center-fragment",
        "anchor": "object-specimen",
        "typography": "local-cjk",
        "texture": "xerox-softness",
        "accent": "cobalt",
        "mood": "quiet",
    }


def variant() -> PlatformVariant:
    specs = [
        {
            "page": page,
            "phrase": f"第 {page} 页短句",
            "note": f"第 {page} 页说明",
            "visual_metaphor": f"第 {page} 页可画物件",
            "layout": "center-fragment",
            "anchor": "object-specimen",
            "accent": "cobalt",
            "texture": "xerox-softness",
            "mood": "quiet",
            "focus_x": 0.5,
            "focus_y": 0.42,
            "zoom": 1.0,
            "page_visual_role": "cover" if page == 1 else "scene",
            "evidence_summary": f"详细来源 {page} 的证据摘要",
        }
        for page in range(1, 4)
    ]
    return PlatformVariant(
        id="variant_prompt_web",
        source_id="source_prompt_web",
        platform="wechat",
        format="light_series",
        version=1,
        title="视觉 Prompt 编译测试",
        subtitle="",
        summary="用逐页语义上下文编译不同视觉锚点。",
        body_markdown="测试正文",
        tags="测试",
        theme="zen",
        metadata_json=json.dumps(
            {
                "poster_specs": specs,
                "recipe": "short_commentary",
                "audience": "普通中文读者",
                "strategy": {
                    "content_thesis": "每一页都要承担不同的视觉职责",
                    "emotional_job": "让证据被看见",
                },
                "visual_bible": {"series_hue": "vermilion"},
                "visual_prompt_mode": "production",
            },
            ensure_ascii=False,
        ),
        output_paths_json="{}",
    )


def test_web_handoff_calls_text_compiler_but_never_image_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MinimalZineNativeService(settings(tmp_path))
    current = variant()
    calls = {"text": 0, "image": 0}

    def text_compile(**_: object) -> dict[str, object]:
        calls["text"] += 1
        return model_result()

    monkeypatch.setattr(service.prompt_compiler.model, "chat_json", text_compile)
    monkeypatch.setattr(
        service,
        "_generate_image",
        lambda _: calls.__setitem__("image", calls["image"] + 1),
    )

    handoff = service.prepare_web_handoff(current, pages=[2])

    assert calls == {"text": 1, "image": 0}
    assert handoff["api_used"] is False
    assert handoff["text_compiler"] is True
    assert handoff["pages"][0]["visual_prompt_spec"]["mode"] == "production_text_safe"


def test_web_and_api_entry_share_the_same_structured_recipe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MinimalZineNativeService(settings(tmp_path))
    current = variant()
    monkeypatch.setattr(service.prompt_compiler.model, "chat_json", lambda **_: model_result())

    web = service.prepare_web_handoff(current, pages=[2])["pages"][0]
    metadata = json.loads(current.metadata_json)
    specs = metadata["poster_specs"]
    api_spec = service._compile_visual_prompt_spec(
        variant=current,
        metadata=metadata,
        specs=specs,
        page=2,
        feature_mode="production",
        force_recompile=False,
    )

    assert web["visual_prompt_spec"] == api_spec.model_dump(mode="json")
    assert api_spec.recipe.layout_family == "upper-right-block"
    assert api_spec.recipe.anchor_form == "torn-paper-clipping"
    assert service._recipe_for(specs[1])["layout"] == "center-fragment"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phrase", "改变后的短句"),
        ("note", "改变后的说明"),
        ("evidence_summary", "详细来源 4 提供了另一条可核对证据"),
    ],
)
def test_semantic_input_changes_source_fingerprint(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    compiler = VisualPromptCompiler(settings(tmp_path))
    before = compiler.source_fingerprint(context(), feature_mode="production")
    after = compiler.source_fingerprint(
        context(**{field: value}),
        feature_mode="production",
    )
    assert before != after


def test_compiler_failure_is_explicitly_degraded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiler = VisualPromptCompiler(settings(tmp_path))
    called = {"fallback": 0}
    monkeypatch.setattr(
        compiler.model,
        "chat_json",
        lambda **_: (_ for _ in ()).throw(ModelClientError("simulated outage")),
    )

    def fallback() -> dict[str, object]:
        called["fallback"] += 1
        return fallback_recipe()

    result = compiler.compile(
        context(),
        feature_mode="production",
        fallback_recipe_factory=fallback,
    )

    assert called["fallback"] == 1
    assert any(value.startswith(DEGRADED_FALLBACK) for value in result.warnings)
    assert result.recipe.layout_family == "center-fragment"


def test_text_safe_transform_preserves_selected_theme_and_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MinimalZineNativeService(settings(tmp_path))
    monkeypatch.setattr(service.prompt_compiler.model, "chat_json", lambda **_: model_result())
    visual_spec = service.prompt_compiler.compile(
        context(),
        feature_mode="production",
        fallback_recipe_factory=fallback_recipe,
    )
    final_prompt = service._four_paragraph_prompt(visual_spec)

    assert final_prompt.startswith(visual_spec.positive_prompt)
    assert "upper-right-block" in final_prompt
    assert "torn vermilion work memo" in final_prompt
    assert "center-fragment" not in final_prompt
    assert "NO TEXT" in final_prompt
    assert len(visual_spec.positive_prompt.split()) > 3 * len(
        " ".join(visual_spec.exclusions).split()
    )


def test_v03_eval_requests_are_installed_and_routed(tmp_path: Path) -> None:
    compiler = VisualPromptCompiler(settings(tmp_path))
    prompt_only = compiler.route_eval_request(4)
    reference = compiler.route_eval_request(3)

    assert prompt_only["route"] == "prompt_only"
    assert reference["route"] == "reference_analysis"
    assert prompt_only["skill_commit"] == "342b5c11d6fa9be261841ec722c12a683a9fa5e9"
    assert len(compiler.eval_requests()) == 7


def test_legacy_flag_rolls_back_without_calling_text_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MinimalZineNativeService(settings(tmp_path, mode="legacy"))
    current = variant()
    metadata = json.loads(current.metadata_json)
    metadata.pop("visual_prompt_mode")
    current.metadata_json = json.dumps(metadata, ensure_ascii=False)
    monkeypatch.setattr(
        service.prompt_compiler.model,
        "chat_json",
        lambda **_: (_ for _ in ()).throw(AssertionError("legacy must not call text model")),
    )

    page = service.prepare_web_handoff(current, pages=[1])["pages"][0]

    assert page["visual_prompt_spec"]["mode"] == "legacy"
    assert page["visual_prompt_spec"]["skill_name"] == "gc-minimal-zine-poster-v0-1"
    assert "LEGACY_COMPILER_ACTIVE" in page["warnings"]
